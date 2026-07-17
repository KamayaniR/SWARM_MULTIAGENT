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
    timestamp TEXT NOT NULL,
    outcome TEXT
);
"""


class CostTracker:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute(_SCHEMA)
        # Older DBs created before `outcome` existed won't pick it up from
        # CREATE TABLE IF NOT EXISTS -- add it if missing so accuracy_per_model
        # works against pre-existing data too.
        existing_cols = {row[1] for row in self.conn.execute("PRAGMA table_info(calls)")}
        if "outcome" not in existing_cols:
            self.conn.execute("ALTER TABLE calls ADD COLUMN outcome TEXT")
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

    def total_latency(self, run_id: str) -> float:
        """Sum of per-call latency (ms) for a run — the wall time spent in LLM calls."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(latency_ms), 0) FROM calls WHERE run_id = ?", (run_id,)
        ).fetchone()
        return row[0]

    def update_outcome(self, step_id: str, outcome: str, run_id: str | None = None) -> None:
        """Set `outcome` ('pass'/'fail') on every call already recorded for
        this step_id -- the outcome is only known once the Critic verdicts,
        by which point the calls that produced this step's code are already
        persisted with outcome=NULL."""
        query = "UPDATE calls SET outcome = ? WHERE step_id = ?"
        params: tuple = (outcome, step_id)
        if run_id is not None:
            query += " AND run_id = ?"
            params = (outcome, step_id, run_id)
        self.conn.execute(query, params)
        self.conn.commit()

    def total_cost(self, run_id: str | None = None) -> float:
        """run_id=None -> collective total across every run ever recorded."""
        query = "SELECT COALESCE(SUM(cost_usd), 0) FROM calls"
        params: tuple = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            params = (run_id,)
        row = self.conn.execute(query, params).fetchone()
        return row[0]

    def total_cost_today(self, today: str) -> float:
        """today: 'YYYY-MM-DD' — matched against the date prefix of ISO timestamps."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE timestamp LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return row[0]

    def breakdown(self, run_id: str | None = None) -> list[dict]:
        """run_id=None -> collective breakdown across every run ever recorded."""
        query = (
            "SELECT model, provider, COUNT(*), SUM(cost_usd), SUM(input_tokens), SUM(output_tokens) "
            "FROM calls"
        )
        params: tuple = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            params = (run_id,)
        query += " GROUP BY model, provider"
        rows = self.conn.execute(query, params).fetchall()
        return [
            {
                "model": r[0], "provider": r[1], "calls": r[2],
                "cost_usd": r[3], "input_tokens": r[4], "output_tokens": r[5],
            }
            for r in rows
        ]

    def accuracy_per_model(self, run_id: str | None = None) -> dict[str, float]:
        """Pass rate per model across every recorded, resolved outcome --
        calls still awaiting a verdict have outcome=NULL and are excluded,
        not counted as failures."""
        query = (
            "SELECT model, "
            "SUM(CASE WHEN outcome = 'pass' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN outcome IN ('pass', 'fail') THEN 1 ELSE 0 END) "
            "FROM calls WHERE outcome IN ('pass', 'fail')"
        )
        params: tuple = ()
        if run_id is not None:
            query += " AND run_id = ?"
            params = (run_id,)
        query += " GROUP BY model"
        rows = self.conn.execute(query, params).fetchall()
        return {model: (passed / total) if total else 0.0 for model, passed, total in rows}

    def latency_per_model(self, run_id: str | None = None) -> dict[str, float]:
        """Average latency_ms per model -- the latency_ms column has always
        been persisted per-call, it just never had an aggregation exposed
        before this."""
        query = "SELECT model, AVG(latency_ms) FROM calls"
        params: tuple = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            params = (run_id,)
        query += " GROUP BY model"
        return dict(self.conn.execute(query, params).fetchall())

    def cost_per_step_class(self, run_id: str | None = None) -> dict[str, float]:
        query = "SELECT step_class, SUM(cost_usd) FROM calls"
        params: tuple = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            params = (run_id,)
        query += " GROUP BY step_class"
        return dict(self.conn.execute(query, params).fetchall())

    def cost_per_converged_task(self, run_id: str | None = None) -> float:
        """Total cost / number of distinct steps that reached a 'pass'
        outcome -- inf if calls exist but nothing has passed yet, 0.0 if no
        calls at all."""
        query = "SELECT DISTINCT step_id FROM calls WHERE outcome = 'pass'"
        params: tuple = ()
        if run_id is not None:
            query += " AND run_id = ?"
            params = (run_id,)
        converged = self.conn.execute(query, params).fetchall()
        if not converged:
            return float("inf") if self.total_cost(run_id) > 0 else 0.0
        return self.total_cost(run_id) / len(converged)


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
