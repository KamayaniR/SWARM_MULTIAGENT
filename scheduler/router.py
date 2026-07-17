import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scheduler.models import DIFFICULTY_TO_MODEL, TIER_LADDER, resolve_model

DB_PATH = Path(__file__).parent.parent / "data" / "scheduler.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS routing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    step_class TEXT NOT NULL,
    model TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    critic_score REAL,
    timestamp TEXT NOT NULL
);
"""

ROLLING_WINDOW = 10
MIN_ATTEMPTS = 3
MIN_PASS_RATE = 0.7

CLASSIFY_SYSTEM_PROMPT = """You are a task difficulty classifier for code generation.

Given a task description, classify it as exactly one of:
- EASY: boilerplate, config, CLI wiring, simple file I/O, test scaffolding,
  string formatting, logging setup, basic CRUD
- MEDIUM: file parsing with edge cases, data transformation, API integration,
  error handling, input validation, database queries
- HARD: complex algorithms, multi-step logic, performance optimization,
  concurrency, state machines, mathematical computation
"""

CLASSIFY_TOOL = {
    "name": "submit_difficulty",
    "description": "Classify the difficulty of a code-generation task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "difficulty": {"type": "string", "enum": ["EASY", "MEDIUM", "HARD"]},
        },
        "required": ["difficulty"],
    },
}


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def reset() -> None:
    """Clear all routing history. The LLM classifier keeps working independently."""
    conn = _connect()
    conn.execute("DELETE FROM routing_history")
    conn.commit()
    conn.close()


def record_outcome(step_class: str, model: str, passed: bool, critic_score: float | None = None) -> None:
    model = resolve_model(model)
    conn = _connect()
    conn.execute(
        "INSERT INTO routing_history (step_class, model, passed, critic_score, timestamp) VALUES (?, ?, ?, ?, ?)",
        (step_class, model, passed, critic_score, datetime.now(timezone.utc).isoformat()),
    )
    # Rolling window: keep only the last ROLLING_WINDOW rows per (step_class, model)
    conn.execute(
        """
        DELETE FROM routing_history
        WHERE step_class = ? AND model = ? AND id NOT IN (
            SELECT id FROM routing_history
            WHERE step_class = ? AND model = ?
            ORDER BY id DESC LIMIT ?
        )
        """,
        (step_class, model, step_class, model, ROLLING_WINDOW),
    )
    conn.commit()
    conn.close()


def _stats(step_class: str, model: str) -> dict:
    conn = _connect()
    rows = conn.execute(
        "SELECT passed FROM routing_history WHERE step_class = ? AND model = ? ORDER BY id DESC LIMIT ?",
        (step_class, model, ROLLING_WINDOW),
    ).fetchall()
    conn.close()
    total = len(rows)
    passed_count = sum(1 for (p,) in rows if p)
    return {
        "total_attempts": total,
        "pass_rate": (passed_count / total) if total else 0.0,
    }


def find_cheapest_passing_tier(step_class: str, upto_model: str) -> tuple[str, dict] | tuple[None, None]:
    """Search TIER_LADDER for the cheapest model strictly below upto_model's tier
    that has enough history and a good enough pass rate for this step_class."""
    upto_model = resolve_model(upto_model)
    limit_idx = TIER_LADDER.index(upto_model)
    for candidate in TIER_LADDER[:limit_idx]:
        stats = _stats(step_class, candidate)
        if stats["total_attempts"] >= MIN_ATTEMPTS and stats["pass_rate"] >= MIN_PASS_RATE:
            return candidate, stats
    return None, None


def classify_with_nano(client, step_description: str, run_id: str) -> str:
    result, _metrics = client.call(
        model="gpt-4.1-nano",
        system=CLASSIFY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f'Task: "{step_description}"'}],
        tool=CLASSIFY_TOOL,
        run_id=run_id,
        agent="router",
        max_tokens=16,
    )
    return result["difficulty"]


def route(client, step_description: str, step_class: str, run_id: str) -> tuple[str, str]:
    """Returns (model_name, routing_reason)."""
    difficulty = classify_with_nano(client, step_description, run_id)
    llm_model = resolve_model(DIFFICULTY_TO_MODEL[difficulty])

    candidate, stats = find_cheapest_passing_tier(step_class, llm_model)
    if candidate:
        return candidate, (
            f"nano said {difficulty}, but history shows {candidate} passes "
            f"{step_class} at {stats['pass_rate']:.0%}"
        )

    return llm_model, f"nano classified as {difficulty}"


if __name__ == "__main__":
    import os

    # Point at a scratch DB so this test never touches real history.
    # (Reassigning the module-global DB_PATH here works because _connect()
    # looks it up by name in this same module's namespace at call time.)
    DB_PATH = Path(__file__).parent.parent / "data" / "router_test.db"
    if DB_PATH.exists():
        os.remove(DB_PATH)

    class FakeClient:
        def __init__(self, difficulty):
            self.difficulty = difficulty

        def call(self, **kwargs):
            return {"difficulty": self.difficulty}, {}

    print("--- cold start: no history, trust nano ---")
    client = FakeClient("HARD")
    model, reason = route(client, "implement dedup algorithm", "algorithm", "test-run")
    print(model, "|", reason)
    assert model == "claude-opus-4-6"
    assert "nano classified as HARD" in reason

    print("\n--- history override: base model proven to pass this step_class ---")
    for _ in range(5):
        record_outcome("algorithm", "claude-sonnet-4-6", passed=True, critic_score=9.0)
    model, reason = route(client, "implement dedup algorithm", "algorithm", "test-run")
    print(model, "|", reason)
    assert model == "claude-sonnet-4-6"
    assert "history shows" in reason

    print("\n--- reset: history cleared, nano trusted again ---")
    reset()
    model, reason = route(client, "implement dedup algorithm", "algorithm", "test-run")
    print(model, "|", reason)
    assert model == "claude-opus-4-6"
    assert "nano classified as HARD" in reason

    os.remove(DB_PATH)
    print("\nok")
