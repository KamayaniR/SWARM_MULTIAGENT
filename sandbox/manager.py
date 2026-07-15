import io
import re
import tarfile
from pathlib import PurePosixPath

import docker

SANDBOX_IMAGE = "swarm-sandbox"
WORKSPACE_DIR = "/workspace"

_SUMMARY_RE = re.compile(
    r"(?:(?P<failed>\d+) failed)?(?:,?\s*)?(?:(?P<passed>\d+) passed)?"
)


class SandboxManager:
    def __init__(self):
        self.client = docker.from_env()

    def create(self) -> str:
        container = self.client.containers.run(
            SANDBOX_IMAGE,
            command="sleep 3600",
            detach=True,
        )
        return container.id

    def inject_files(self, container_id: str, files: dict[str, str]) -> None:
        container = self.client.containers.get(container_id)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            for path, content in files.items():
                data = content.encode("utf-8")
                info = tarfile.TarInfo(name=PurePosixPath(path).as_posix())
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        tar_stream.seek(0)

        container.put_archive(WORKSPACE_DIR, tar_stream.getvalue())

    def run_tests(self, container_id: str) -> dict:
        container = self.client.containers.get(container_id)
        exit_code, output = container.exec_run(
            "pytest -v --tb=short",
            workdir=WORKSPACE_DIR,
        )
        stdout = output.decode("utf-8", errors="replace")

        passed = 0
        failed = 0
        for line in stdout.splitlines():
            if " passed" in line or " failed" in line or " error" in line:
                m = re.search(r"(\d+) passed", line)
                if m:
                    passed = int(m.group(1))
                m = re.search(r"(\d+) failed", line)
                if m:
                    failed = int(m.group(1))

        return {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": "",
            "tests_passed": passed,
            "tests_total": passed + failed,
        }

    def cleanup(self, container_id: str) -> None:
        container = self.client.containers.get(container_id)
        container.stop()
        container.remove()


if __name__ == "__main__":
    mgr = SandboxManager()
    cid = mgr.create()
    print(f"container: {cid}")

    try:
        mgr.inject_files(
            cid,
            {
                "add.py": "def add(a, b):\n    return a + b\n",
                "test_add.py": "from add import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
            },
        )
        result = mgr.run_tests(cid)
        print(result["stdout"])
        print(f"passed={result['tests_passed']} total={result['tests_total']} exit_code={result['exit_code']}")
    finally:
        mgr.cleanup(cid)
        print("cleaned up")
