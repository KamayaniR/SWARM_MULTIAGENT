"""Select the sandbox backend from environment config.

    SANDBOX_BACKEND=docker   (default) -> local Docker (sandbox/manager.py)
    SANDBOX_BACKEND=akash              -> pooled Akash containers (sandbox/akash.py)

Akash config:
    SANDBOX_AKASH_URLS   comma-separated sandbox URIs (the Console lease URIs)
    SANDBOX_AGENT_TOKEN  bearer token the agents were deployed with
"""

import os


def get_sandbox():
    backend = os.environ.get("SANDBOX_BACKEND", "docker").strip().lower()

    if backend == "akash":
        from sandbox.akash import AkashSandbox

        raw = os.environ.get("SANDBOX_AKASH_URLS", "")
        urls = [u for u in (p.strip() for p in raw.split(",")) if u]
        if not urls:
            raise RuntimeError(
                "SANDBOX_BACKEND=akash but SANDBOX_AKASH_URLS is empty; "
                "set it to the comma-separated Akash sandbox URIs"
            )
        token = os.environ.get("SANDBOX_AGENT_TOKEN", "")
        return AkashSandbox(urls, token=token)

    if backend == "docker":
        from sandbox.manager import SandboxManager

        return SandboxManager()

    raise RuntimeError(f"unknown SANDBOX_BACKEND={backend!r} (use 'docker' or 'akash')")
