"""Structural workflow cache.

A second savings tier on top of the router. The router matches each *step* to
the cheapest capable model; this layer matches a *whole workflow* to a prior
successful run and, on a strong structural match, reuses that run's result
instead of re-running the work.

Two kinds of workflow are cached, both keyed the same way — by the ordered
sequence of `step_class` values, which is the workflow's structural signature:

  - "loop": the sequential LangGraph loop (orchestrator/loop.py). Signature =
    the plan's step_class sequence. Payload = the verified workspace_files. On a
    hit the loop is skipped and the files are reused (after re-verification).

  - "team": the Agent-mode bake-off (orchestrator/agent_mode.py). Signature =
    the team plan's role step_class sequence. Payload = the whole TeamResult
    (the per-model accuracy/latency/cost comparison + recommendations). On a hit
    the debates and candidate bake-offs are skipped and the cached comparison is
    served.

Matching is structural (v1): similarity is difflib's sequence ratio over the
step_class sequences. Two differently-worded specs that distil into the same
shape match here even though their raw prompts wouldn't. No embeddings, no API
call, fully deterministic and explainable on the dashboard. Only runs that
reached status "done" are stored, so the cache holds verified workflows only.
"""

import difflib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "cache.db"

# Default 0.70 per the design; override with PLAN_CACHE_THRESHOLD. Note 0.70 is
# intentionally loose — verify/reuse-of-verified-work is what makes that safe.
DEFAULT_THRESHOLD = 0.70

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,            -- "loop" | "team"
    run_id TEXT NOT NULL,
    spec TEXT NOT NULL,
    signature TEXT NOT NULL,       -- json list of step_class, in workflow order
    payload TEXT NOT NULL,         -- json; shape depends on kind
    score REAL,                    -- representative quality score, for tie-breaks
    created_at TEXT NOT NULL
);
"""


def threshold() -> float:
    return float(os.environ.get("PLAN_CACHE_THRESHOLD", DEFAULT_THRESHOLD))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def signature_from_plan(plan: list[dict]) -> list[str]:
    """Structural signature of a sequential plan: its steps' step_class, in order."""
    return [step["step_class"] for step in plan]


def signature_from_roles(roles: list[dict]) -> list[str]:
    """Structural signature of a team plan: its roles' step_class, in order."""
    return [role["step_class"] for role in roles]


def similarity(a: list[str], b: list[str]) -> float:
    """Order-aware structural similarity in [0, 1] between two signatures.

    difflib handles inserted/deleted/reordered steps gracefully, so a workflow
    with one extra step still scores high against its near-twin."""
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def reset() -> None:
    conn = _connect()
    conn.execute("DELETE FROM workflow_cache")
    conn.commit()
    conn.close()


def store(
    kind: str,
    run_id: str,
    spec: str,
    signature: list[str],
    payload: dict,
    score: float | None,
) -> None:
    """Record a completed workflow's result, keyed by its structural signature."""
    conn = _connect()
    conn.execute(
        "INSERT INTO workflow_cache (kind, run_id, spec, signature, payload, score, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            kind,
            run_id,
            spec,
            json.dumps(signature),
            json.dumps(payload),
            score,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def lookup(kind: str, signature: list[str], min_score: float | None = None) -> dict | None:
    """Return the best cached workflow of `kind` whose signature structurally
    matches `signature` at or above the threshold, else None.

    Result: {"run_id", "score", "spec", "payload", "stored_score"}. Ties break on
    the higher structural score, then the higher stored quality score.
    """
    if min_score is None:
        min_score = threshold()

    conn = _connect()
    rows = conn.execute(
        "SELECT run_id, spec, signature, payload, score FROM workflow_cache WHERE kind = ?",
        (kind,),
    ).fetchall()
    conn.close()

    best: dict | None = None
    for run_id, spec, sig_json, payload_json, stored_score in rows:
        score = similarity(signature, json.loads(sig_json))
        if score < min_score:
            continue
        if best is None or (score, stored_score or 0) > (best["score"], best["stored_score"] or 0):
            best = {
                "run_id": run_id,
                "score": score,
                "spec": spec,
                "payload": json.loads(payload_json),
                "stored_score": stored_score,
            }
    return best
