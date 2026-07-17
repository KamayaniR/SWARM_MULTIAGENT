"""Similarity-based deliberation skip (the caching layer for Agent mode).

Every time Agent mode's deliberation picks a winning model for a step, the
step is recorded here: its description + step_class, an embedding of the two
concatenated, the spec it came from, and the model that won. Before running a
new deliberation, Agent mode first embeds the incoming step and cosine-compares
it against this history:

  - score >= SIMILARITY_THRESHOLD  ->  skip the deliberation entirely and reuse
    the historical winning model. Execution (Coder -> Tester -> Critic) still
    runs in full — only the deliberation is skipped, never the actual work.
  - score <  SIMILARITY_THRESHOLD  ->  deliberate as normal.

The embedding text is "{step_class}: {step_description}" — including the class
acts as a coarse pre-filter so superficially similar descriptions from
unrelated step types (shared vocabulary, different work) don't false-match.

SIMILARITY_THRESHOLD is a placeholder pending a calibration pass (hand-build
~15-20 true-rephrasing vs similar-but-different step pairs, embed them, and set
the threshold where the score gap actually falls) — do not treat 0.60 as tuned.
"""

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "similarity.db"

# Placeholder — calibrate against real step pairs before trusting it (see module docstring).
SIMILARITY_THRESHOLD = 0.60

EMBED_MODEL = "text-embedding-3-small"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS step_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spec TEXT NOT NULL,
    step_description TEXT NOT NULL,
    step_class TEXT NOT NULL,
    embedding TEXT NOT NULL,
    winning_model TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def _embed_text(step_description: str, step_class: str) -> str:
    return f"{step_class}: {step_description}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def reset() -> None:
    """Clear all step history. The next Agent-mode run deliberates from scratch."""
    conn = _connect()
    conn.execute("DELETE FROM step_history")
    conn.commit()
    conn.close()


def record_step(
    client, spec: str, step_description: str, step_class: str,
    winning_model: str, run_id: str,
) -> None:
    """Store a deliberation outcome for future similarity matching."""
    vector = client.embed(
        text=_embed_text(step_description, step_class),
        run_id=run_id, step_class=step_class, model=EMBED_MODEL,
    )
    conn = _connect()
    conn.execute(
        "INSERT INTO step_history (spec, step_description, step_class, embedding, winning_model, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            spec, step_description, step_class, json.dumps(vector),
            winning_model, datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def check_similarity(
    client, step_description: str, step_class: str, run_id: str,
) -> tuple[Optional[dict], float]:
    """Return (best_match, score) for the incoming step against all history.

    best_match is {"id", "step_description", "step_class", "winning_model"}
    for the highest-scoring stored step, or None when history is empty.
    The caller decides what to do with the score (compare to
    SIMILARITY_THRESHOLD); this function never skips anything itself.
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT id, step_description, step_class, embedding, winning_model FROM step_history"
    ).fetchall()
    conn.close()
    if not rows:
        return None, 0.0

    vector = client.embed(
        text=_embed_text(step_description, step_class),
        run_id=run_id, step_class=step_class, model=EMBED_MODEL,
    )

    best_row, best_score = None, -1.0
    for row in rows:
        score = _cosine(vector, json.loads(row[3]))
        if score > best_score:
            best_row, best_score = row, score

    match = {
        "id": best_row[0],
        "step_description": best_row[1],
        "step_class": best_row[2],
        "winning_model": best_row[4],
    }
    return match, best_score


if __name__ == "__main__":
    # Exercises the storage + matching flow with a fake embedder — no API, no spend.
    import os

    DB_PATH = Path(__file__).parent.parent / "data" / "similarity_test.db"
    if DB_PATH.exists():
        os.remove(DB_PATH)

    class FakeClient:
        """Deterministic 3-dim embeddings keyed by exact text."""
        VECTORS = {
            "io_parsing: parse CSV rows handling quoted fields": [1.0, 0.0, 0.1],
            "io_parsing: read CSV input coping with quoted values": [0.98, 0.05, 0.12],
            "algorithm: deduplicate rows by key columns": [0.0, 1.0, 0.0],
        }

        def embed(self, *, text, run_id, agent="router", step_id="", step_class="", model=""):
            return self.VECTORS[text]

    client = FakeClient()

    print("--- empty history: no match ---")
    match, score = check_similarity(client, "parse CSV rows handling quoted fields", "io_parsing", "test")
    print(match, score)
    assert match is None and score == 0.0

    record_step(client, "spec", "parse CSV rows handling quoted fields", "io_parsing", "gpt-4.1-mini", "test")
    record_step(client, "spec", "deduplicate rows by key columns", "algorithm", "claude-opus-4-8", "test")

    print("\n--- rephrased step: high score, matches the right entry ---")
    match, score = check_similarity(client, "read CSV input coping with quoted values", "io_parsing", "test")
    print(match["winning_model"], f"{score:.3f}")
    assert match["winning_model"] == "gpt-4.1-mini"
    assert score >= SIMILARITY_THRESHOLD, score

    print("\n--- unrelated step: low score against everything ---")
    match, score = check_similarity(client, "deduplicate rows by key columns", "algorithm", "test")
    assert match["winning_model"] == "claude-opus-4-8" and score > 0.99  # exact self-match

    # cross-check: the io_parsing vector vs the algorithm entry scores near zero
    v_io = FakeClient.VECTORS["io_parsing: parse CSV rows handling quoted fields"]
    v_alg = FakeClient.VECTORS["algorithm: deduplicate rows by key columns"]
    assert _cosine(v_io, v_alg) < 0.1

    print("\n--- reset clears history ---")
    reset()
    match, score = check_similarity(client, "parse CSV rows handling quoted fields", "io_parsing", "test")
    assert match is None

    os.remove(DB_PATH)
    print("\nok")
