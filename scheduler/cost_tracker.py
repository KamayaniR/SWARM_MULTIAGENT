import sqlite3
from pathlib import Path

from scheduler.models import CallRecord

DB_PATH = Path(__file__).parent.parent / "data" / "costs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    step_class TEXT NOT NULL,
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_ms REAL NOT NULL,
    iteration INTEGER NOT NULL,
    timestamp TEXT NOT NULL
);
"""


class CostTracker:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    def record(self, call: CallRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO calls
                (run_id, step_id, step_class, agent, model, provider,
                 input_tokens, output_tokens, cost_usd, latency_ms,
                 iteration, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                call.run_id, call.step_id, call.step_class, call.agent,
                call.model, call.provider, call.input_tokens, call.output_tokens,
                call.cost_usd, call.latency_ms, call.iteration, call.timestamp,
            ),
        )
        self.conn.commit()

    def total_cost(self, run_id: str) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE run_id = ?", (run_id,)
        ).fetchone()
        return row[0]

    def total_cost_today(self, today: str) -> float:
        """today: 'YYYY-MM-DD' — matched against the date prefix of ISO timestamps."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE timestamp LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return row[0]

    def breakdown(self, run_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT model, provider, COUNT(*), SUM(cost_usd), SUM(input_tokens), SUM(output_tokens)
            FROM calls WHERE run_id = ? GROUP BY model, provider
            """,
            (run_id,),
        ).fetchall()
        return [
            {
                "model": r[0], "provider": r[1], "calls": r[2],
                "cost_usd": r[3], "input_tokens": r[4], "output_tokens": r[5],
            }
            for r in rows
        ]


if __name__ == "__main__":
    import os

    tmp_db = Path(__file__).parent.parent / "data" / "costs_test.db"
    if tmp_db.exists():
        os.remove(tmp_db)

    tracker = CostTracker(tmp_db)
    tracker.record(CallRecord(
        run_id="test-run", step_id="s1", step_class="cli_wiring", agent="coder",
        model="gpt-4.1-mini", provider="openai", input_tokens=1000, output_tokens=500,
        cost_usd=0.0012, latency_ms=890, iteration=0,
    ))
    tracker.record(CallRecord(
        run_id="test-run", step_id="s2", step_class="algorithm", agent="coder",
        model="claude-sonnet-5", provider="anthropic", input_tokens=2000, output_tokens=1000,
        cost_usd=0.014, latency_ms=1500, iteration=0,
    ))

    total = tracker.total_cost("test-run")
    print(f"total_cost: {total}")
    assert abs(total - 0.0152) < 1e-9, f"unexpected total {total}"

    breakdown = tracker.breakdown("test-run")
    print(f"breakdown: {breakdown}")
    assert len(breakdown) == 2

    os.remove(tmp_db)
    print("ok")
