"""Akash-backed sandbox pool.

Drop-in replacement for the local-Docker `SandboxManager`: exposes the same
create / inject_files / run_tests / cleanup surface, but instead of spinning up
a Docker container it hands out one of a fixed pool of pre-deployed Akash
containers (each running sandbox/agent_server.py) and talks to it over HTTP.

We deliberately *reuse* the leases rather than deploying per task (opening an
Akash lease takes tens of seconds and costs escrow). "create" leases a free
sandbox from the pool and wipes its workspace; "cleanup" wipes it again and
returns it to the pool. The Akash deployments themselves are created once, out
of band, via Akash Console (see akash/deploy-sandbox.yaml).
"""

import queue
import threading

import requests


class NoSandboxAvailable(RuntimeError):
    """Raised when every pooled sandbox is busy and none frees up in time."""


class AkashSandbox:
    def __init__(
        self,
        urls: list[str],
        token: str = "",
        acquire_timeout: float = 300.0,
        request_timeout: float = 180.0,
    ):
        if not urls:
            raise ValueError("AkashSandbox needs at least one sandbox URL")
        self._token = token
        self._acquire_timeout = acquire_timeout
        self._request_timeout = request_timeout
        # Pool of free sandbox base URLs. queue.Queue makes borrow/return
        # thread-safe, which matters because Agent Mode races candidates in
        # parallel threads, each grabbing its own sandbox.
        self._free: "queue.Queue[str]" = queue.Queue()
        self._in_use: set[str] = set()
        self._lock = threading.Lock()
        for u in urls:
            self._free.put(self._normalize(u))

    @staticmethod
    def _normalize(url: str) -> str:
        url = url.strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        return url

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    # --- SandboxManager-compatible surface -------------------------------

    def create(self) -> str:
        """Borrow a free sandbox from the pool, wipe it clean, and return its
        URL as the handle (the rest of the orchestrator treats this like a
        container id)."""
        try:
            url = self._free.get(timeout=self._acquire_timeout)
        except queue.Empty:
            raise NoSandboxAvailable(
                f"no free Akash sandbox within {self._acquire_timeout}s"
            )
        with self._lock:
            self._in_use.add(url)
        try:
            self._reset(url)
        except Exception:
            # Couldn't reset — hand it back and re-raise so the caller fails
            # loudly rather than running tests in a dirty workspace.
            self._release(url)
            raise
        return url

    def inject_files(self, container_id: str, files: dict[str, str]) -> None:
        r = requests.post(
            f"{container_id}/inject",
            json={"files": files},
            headers=self._headers(),
            timeout=self._request_timeout,
        )
        r.raise_for_status()

    def run_tests(self, container_id: str) -> dict:
        r = requests.post(
            f"{container_id}/run_tests",
            headers=self._headers(),
            timeout=self._request_timeout,
        )
        r.raise_for_status()
        return r.json()

    def cleanup(self, container_id: str) -> None:
        """Wipe the workspace and return the sandbox to the pool for reuse.
        Does NOT close the Akash lease — the pool is long-lived."""
        try:
            self._reset(container_id)
        finally:
            self._release(container_id)

    # --- helpers ---------------------------------------------------------

    def _reset(self, url: str) -> None:
        r = requests.post(
            f"{url}/reset", headers=self._headers(), timeout=self._request_timeout
        )
        r.raise_for_status()

    def _release(self, url: str) -> None:
        with self._lock:
            if url not in self._in_use:
                return  # already returned; avoid double-adding to the pool
            self._in_use.discard(url)
        self._free.put(url)

    def health(self) -> dict[str, bool]:
        """Ping /health on every pooled sandbox. Handy for a startup check."""
        status: dict[str, bool] = {}
        # snapshot all known urls (free + in use)
        with self._lock:
            urls = set(self._in_use) | set(self._free.queue)
        for u in urls:
            try:
                r = requests.get(f"{u}/health", timeout=10)
                status[u] = r.ok and r.json().get("ok", False)
            except Exception:
                status[u] = False
        return status
