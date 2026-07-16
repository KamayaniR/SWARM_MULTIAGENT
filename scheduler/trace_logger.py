import json
from pathlib import Path

TRACES_DIR = Path(__file__).parent.parent / "data" / "traces"


class TraceLogger:
    def __init__(self, traces_dir: Path = TRACES_DIR):
        self.traces_dir = traces_dir
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.traces_dir / f"{run_id}.jsonl"

    def log(self, run_id: str, entry: dict) -> None:
        with open(self._path(run_id), "a") as f:
            f.write(json.dumps(entry) + "\n")

    def read(self, run_id: str) -> list[dict]:
        path = self._path(run_id)
        if not path.exists():
            return []
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    import os

    run_id = "test-run-trace"
    logger = TraceLogger()
    path = logger._path(run_id)
    if path.exists():
        os.remove(path)

    logger.log(run_id, {
        "agent": "coder", "step_id": "s1", "model": "gpt-4.1-mini",
        "prompt": "implement s1", "response": "def main(): ...",
        "input_tokens": 1000, "output_tokens": 500, "cost_usd": 0.0012, "latency_ms": 890,
    })
    logger.log(run_id, {
        "agent": "critic", "step_id": "s1", "model": "claude-sonnet-5",
        "prompt": "judge s1", "response": '{"overall": 9.1}',
        "input_tokens": 1500, "output_tokens": 200, "cost_usd": 0.005, "latency_ms": 1200,
    })

    entries = logger.read(run_id)
    print(json.dumps(entries, indent=2))
    assert len(entries) == 2
    assert entries[0]["agent"] == "coder"

    os.remove(path)
    print("ok")
