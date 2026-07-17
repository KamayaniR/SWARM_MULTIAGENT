"""In-container sandbox agent.

Runs INSIDE the sandbox container (on Akash or anywhere reachable over HTTP)
and exposes the operations the orchestrator used to perform through the local
Docker socket. On Akash there is no Docker API to `put_archive` / `exec_run`
against, so the container serves these over HTTP instead:

    GET  /health              -> {"ok": true}
    POST /inject   {files}     -> write files into the workspace
    POST /run_tests            -> run pytest, return pass/fail counts + stdout
    POST /reset                -> wipe the workspace (for sandbox reuse)

Deliberately stdlib-only (http.server) so the sandbox image stays tiny and
needs no web framework. All mutating endpoints require a bearer token
(SANDBOX_AGENT_TOKEN) because the service is exposed to the public internet.
"""

import json
import os
import re
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORKSPACE_DIR = Path(os.environ.get("SANDBOX_WORKSPACE", "/workspace"))
PORT = int(os.environ.get("SANDBOX_AGENT_PORT", "8080"))
AUTH_TOKEN = os.environ.get("SANDBOX_AGENT_TOKEN", "")
PYTEST_TIMEOUT = int(os.environ.get("SANDBOX_PYTEST_TIMEOUT", "120"))


def _parse_pytest(stdout: str) -> tuple[int, int]:
    """Pull (passed, failed) off pytest's summary line. Mirrors the parsing the
    old Docker-based SandboxManager.run_tests did, so callers see the same shape."""
    passed = failed = 0
    for line in stdout.splitlines():
        if " passed" in line or " failed" in line or " error" in line:
            m = re.search(r"(\d+) passed", line)
            if m:
                passed = int(m.group(1))
            m = re.search(r"(\d+) failed", line)
            if m:
                failed = int(m.group(1))
    return passed, failed


def _run_tests() -> dict:
    proc = subprocess.run(
        ["pytest", "-v", "--tb=short"],
        cwd=str(WORKSPACE_DIR),
        capture_output=True,
        text=True,
        timeout=PYTEST_TIMEOUT,
    )
    stdout = proc.stdout + proc.stderr
    passed, failed = _parse_pytest(stdout)
    return {
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": "",
        "tests_passed": passed,
        "tests_total": passed + failed,
    }


def _write_files(files: dict[str, str]) -> int:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        # Keep writes inside the workspace — reject absolute paths / traversal.
        target = (WORKSPACE_DIR / rel_path).resolve()
        if not str(target).startswith(str(WORKSPACE_DIR.resolve())):
            raise ValueError(f"path escapes workspace: {rel_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return len(files)


def _reset() -> None:
    """Wipe the workspace so a reused sandbox starts clean for the next task."""
    if WORKSPACE_DIR.exists():
        for child in WORKSPACE_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    else:
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self) -> bool:
        if not AUTH_TOKEN:
            return True  # no token configured -> open (dev only)
        return self.headers.get("Authorization") == f"Bearer {AUTH_TOKEN}"

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def log_message(self, *args):  # quiet the default noisy logging
        pass

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "workspace": str(WORKSPACE_DIR)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authed():
            self._send(401, {"error": "unauthorized"})
            return
        try:
            if self.path == "/inject":
                data = self._read_json()
                n = _write_files(data.get("files", {}))
                self._send(200, {"ok": True, "written": n})
            elif self.path == "/run_tests":
                self._send(200, _run_tests())
            elif self.path == "/reset":
                _reset()
                self._send(200, {"ok": True})
            else:
                self._send(404, {"error": "not found"})
        except subprocess.TimeoutExpired:
            self._send(200, {
                "exit_code": -1, "stdout": "pytest timed out", "stderr": "",
                "tests_passed": 0, "tests_total": 0,
            })
        except Exception as e:  # noqa: BLE001 - report any failure to the caller
            self._send(500, {"error": str(e)})


def main():
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"sandbox-agent listening on :{PORT} (workspace={WORKSPACE_DIR}, "
          f"auth={'on' if AUTH_TOKEN else 'off'})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
