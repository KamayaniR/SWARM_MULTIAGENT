"""Persistent store for the code a run produces.

The generated code otherwise lives only in memory (SwarmState.workspace_files)
and inside LangGraph's checkpoint blobs — neither is convenient to fetch or
hand to a user. This module writes the final `{path: content}` file set to a
small SQLite table keyed by run_id (plus an optional label, so a bake-off can
store per-role code alongside the merged "final"), and can zip any file set for
download.
"""

import io
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "artifacts.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_code (
    run_id     TEXT NOT NULL,
    label      TEXT NOT NULL DEFAULT 'final',
    status     TEXT NOT NULL,
    files_json TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, label)
);

CREATE TABLE IF NOT EXISTS run_history (
    run_id     TEXT PRIMARY KEY,
    prompt     TEXT NOT NULL,   -- the spec / user prompt
    plan_json  TEXT NOT NULL,   -- the plan steps (task mode) or team roles (agent mode)
    files_json TEXT NOT NULL,   -- the generated code {path: content}
    selected   TEXT NOT NULL,   -- selected solution: winning model(s)
    status     TEXT NOT NULL,
    total_cost REAL NOT NULL,   -- cost, USD
    latency_ms REAL NOT NULL DEFAULT 0,  -- total wall latency, ms
    accuracy   REAL NOT NULL DEFAULT 0,  -- critic score (0-10) of the selected solution
    created_at TEXT NOT NULL
);
"""

# Columns added after the table first shipped — applied to existing DBs on connect.
_MIGRATIONS = [
    ("run_history", "latency_ms", "REAL NOT NULL DEFAULT 0"),
    ("run_history", "accuracy", "REAL NOT NULL DEFAULT 0"),
]


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    for table, column, decl in _MIGRATIONS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.commit()
    return conn


def save_run_code(
    run_id: str, files: dict[str, str], status: str, label: str = "final",
) -> None:
    """Upsert the code for a run (idempotent — re-running a run replaces it).
    No-op on an empty file set so we never store a placeholder empty artifact."""
    if not files:
        return
    conn = _connect()
    conn.execute(
        "INSERT INTO run_code (run_id, label, status, files_json, file_count, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(run_id, label) DO UPDATE SET "
        "status=excluded.status, files_json=excluded.files_json, "
        "file_count=excluded.file_count, updated_at=excluded.updated_at",
        (
            run_id, label, status, json.dumps(files), len(files),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_run_code(run_id: str, label: str = "final") -> dict | None:
    """Return {"status", "files", "updated_at"} for a run, or None if not stored."""
    conn = _connect()
    row = conn.execute(
        "SELECT status, files_json, updated_at FROM run_code WHERE run_id = ? AND label = ?",
        (run_id, label),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {"status": row[0], "files": json.loads(row[1]), "updated_at": row[2]}


def list_labels(run_id: str) -> list[str]:
    conn = _connect()
    rows = conn.execute(
        "SELECT label FROM run_code WHERE run_id = ? ORDER BY label", (run_id,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def save_run_history(
    run_id: str,
    prompt: str,
    plan: list,
    files: dict[str, str],
    selected: str,
    status: str,
    total_cost: float = 0.0,
    latency_ms: float = 0.0,
    accuracy: float = 0.0,
) -> None:
    """Upsert the full story of a run — prompt, plan, generated code, the
    selected solution, and its cost / latency / accuracy — as one row, so it
    can be fetched from a single place."""
    conn = _connect()
    conn.execute(
        "INSERT INTO run_history "
        "(run_id, prompt, plan_json, files_json, selected, status, "
        " total_cost, latency_ms, accuracy, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(run_id) DO UPDATE SET "
        "prompt=excluded.prompt, plan_json=excluded.plan_json, "
        "files_json=excluded.files_json, selected=excluded.selected, "
        "status=excluded.status, total_cost=excluded.total_cost, "
        "latency_ms=excluded.latency_ms, accuracy=excluded.accuracy, "
        "created_at=excluded.created_at",
        (
            run_id, prompt, json.dumps(plan), json.dumps(files),
            selected, status, total_cost, latency_ms, accuracy,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_run_history(run_id: str) -> dict | None:
    """Return the full run record (prompt, plan, files, selected, ...) or None."""
    conn = _connect()
    row = conn.execute(
        "SELECT prompt, plan_json, files_json, selected, status, "
        "total_cost, latency_ms, accuracy, created_at "
        "FROM run_history WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "prompt": row[0],
        "plan": json.loads(row[1]),
        "files": json.loads(row[2]),
        "selected": row[3],
        "status": row[4],
        "total_cost": row[5],
        "latency_ms": row[6],
        "accuracy": row[7],
        "created_at": row[8],
    }


def list_runs() -> list[dict]:
    """Lightweight index of all stored runs (no code/plan blobs) for a history list."""
    conn = _connect()
    rows = conn.execute(
        "SELECT run_id, prompt, selected, status, total_cost, latency_ms, accuracy, created_at "
        "FROM run_history ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [
        {
            "run_id": r[0], "prompt": r[1], "selected": r[2], "status": r[3],
            "total_cost": r[4], "latency_ms": r[5], "accuracy": r[6], "created_at": r[7],
        }
        for r in rows
    ]


def zip_bytes(files: dict[str, str]) -> bytes:
    """Pack a {path: content} map into an in-memory zip archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


if __name__ == "__main__":
    # Round-trip smoke test against a throwaway DB — no server needed.
    import os

    DB_PATH = Path(__file__).parent.parent / "data" / "artifacts_test.db"
    if DB_PATH.exists():
        os.remove(DB_PATH)

    files = {"cli.py": "print('hi')\n", "test_cli.py": "def test(): assert True\n"}
    save_run_code("run-1", files, status="done")
    got = get_run_code("run-1")
    assert got is not None and got["files"] == files, got
    assert got["status"] == "done"

    # per-label storage
    save_run_code("run-1", {"a.py": "1\n"}, status="done", label="planner::gpt-5")
    assert set(list_labels("run-1")) == {"final", "planner::gpt-5"}

    # empty file set is a no-op
    save_run_code("run-2", {}, status="done")
    assert get_run_code("run-2") is None

    # zip contains both files
    data = zip_bytes(files)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert set(zf.namelist()) == {"cli.py", "test_cli.py"}
        assert zf.read("cli.py").decode() == "print('hi')\n"

    # run_history: full story round-trips, and upsert replaces
    plan = [{"id": "s1", "description": "parse csv", "step_class": "io_parsing"}]
    save_run_history("run-1", "Build a CSV deduper", plan, files,
                     selected="claude-sonnet-4-6", status="done",
                     total_cost=0.0123, latency_ms=4200.0, accuracy=9.1)
    hist = get_run_history("run-1")
    assert hist is not None
    assert hist["prompt"] == "Build a CSV deduper"
    assert hist["plan"] == plan
    assert hist["files"] == files
    assert hist["selected"] == "claude-sonnet-4-6"
    assert round(hist["total_cost"], 4) == 0.0123
    assert hist["latency_ms"] == 4200.0
    assert hist["accuracy"] == 9.1
    assert list_runs()[0]["accuracy"] == 9.1
    save_run_history("run-1", "Build a CSV deduper v2", plan, files,
                     selected="gpt-5", status="done", total_cost=0.02)
    assert get_run_history("run-1")["selected"] == "gpt-5"  # upserted
    assert len(list_runs()) == 1
    assert get_run_history("nope") is None

    os.remove(DB_PATH)
    print("ok")
