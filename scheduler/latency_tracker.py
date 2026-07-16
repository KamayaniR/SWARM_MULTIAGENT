from collections import defaultdict


class LatencyTracker:
    """In-memory per-run latency stats. Not persisted — rebuilt each process."""

    def __init__(self):
        self._records: dict[str, list[dict]] = defaultdict(list)

    def record(self, run_id: str, agent: str, model: str, latency_ms: float,
               time_to_first_token_ms: float | None = None) -> None:
        self._records[run_id].append({
            "agent": agent,
            "model": model,
            "latency_ms": latency_ms,
            "time_to_first_token_ms": time_to_first_token_ms,
        })

    def summary(self, run_id: str) -> dict:
        records = self._records.get(run_id, [])
        by_agent: dict[str, list[float]] = defaultdict(list)
        for r in records:
            by_agent[r["agent"]].append(r["latency_ms"])

        return {
            agent: {
                "count": len(latencies),
                "avg_ms": sum(latencies) / len(latencies),
                "total_ms": sum(latencies),
            }
            for agent, latencies in by_agent.items()
        }


if __name__ == "__main__":
    tracker = LatencyTracker()
    tracker.record("test-run", "coder", "gpt-4.1-mini", 890)
    tracker.record("test-run", "coder", "claude-sonnet-5", 1500)
    tracker.record("test-run", "critic", "claude-sonnet-5", 2200)

    summary = tracker.summary("test-run")
    print(summary)
    assert summary["coder"]["count"] == 2
    assert summary["coder"]["avg_ms"] == 1195
    assert summary["critic"]["total_ms"] == 2200
    print("ok")
