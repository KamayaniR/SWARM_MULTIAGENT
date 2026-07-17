import asyncio
import uuid
from typing import Literal, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel

from orchestrator import artifacts
from orchestrator.agent_mode import get_agent_run, run_agent_mode
from orchestrator.events import emitter
from orchestrator.graph import _initial_state, graph, run_to_completion
from orchestrator.loop import PREFERENCE_TIMEOUT_SECONDS, resolve_comparison
from scheduler import router as router_module
from scheduler import similarity as similarity_module
from scheduler.cost_tracker import CostTracker
from scheduler.trace_logger import TraceLogger

app = FastAPI(title="Swarm Control")

# CostTracker/TraceLogger need no API credentials — read from the same
# SQLite/JSONL files the (separately, lazily constructed) TrackedLLMClient
# writes to during a run, without requiring live keys just to read data.
_cost_tracker = CostTracker()
_trace_logger = TraceLogger()

# run_id -> final SwarmState once the background run completes; None while running.
_runs: dict[str, dict | None] = {}

# run_ids whose awaiting_preference pause has already been resolved (by an
# explicit commit-preference call or the timeout watchdog) — guards against
# both firing for the same pause in a race.
_preference_resolved: set[str] = set()


class RunRequest(BaseModel):
    spec: str
    debate_mode: bool = False
    # "task" = existing flow unchanged; "agent" = per-run deliberation flow
    # (similarity check -> deliberation -> dual-candidate sandbox comparison).
    mode: Literal["task", "agent"] = "task"
    # Agent-mode winner selection: None -> default rule (highest accuracy,
    # tie broken by lowest cost).
    preference: Optional[Literal["cost", "latency", "accuracy"]] = None


class AgentRunRequest(BaseModel):
    spec: str


class InterveneRequest(BaseModel):
    run_id: str
    step_id: str
    correction_text: str


class CommitPreferenceRequest(BaseModel):
    dimension: Literal["cost", "accuracy", "latency"]


@app.on_event("startup")
async def _bind_emitter_loop():
    emitter.bind_loop(asyncio.get_running_loop())


def _config_for(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 100}


def _run_loop_sync(
    spec: str, run_id: str, baseline_mode: bool, debate_mode: bool = False,
    mode: str = "task", preference: str | None = None,
) -> None:
    state = _initial_state(
        spec, run_id=run_id, baseline_mode=baseline_mode, debate_mode=debate_mode,
        mode=mode, model_preference=preference,
    )
    try:
        _runs[run_id] = run_to_completion(state, _config_for(run_id))
    except Exception as e:
        # Without this, a mid-run crash (e.g. BudgetGuard tripping) leaves
        # _runs[run_id] at None forever, and /api/runs/{run_id} reports
        # "running" indefinitely instead of surfacing the failure.
        _runs[run_id] = {"status": "error", "detail": str(e), "events": []}


def _resume_loop_sync(run_id: str) -> None:
    try:
        _runs[run_id] = run_to_completion(None, _config_for(run_id))
    except Exception as e:
        _runs[run_id] = {"status": "error", "detail": str(e), "events": []}


async def _run_and_watch(run_id: str, blocking_fn, *args) -> None:
    """Run a blocking loop function in a thread, then check whether it
    stopped because it's awaiting a preference — if so, arm the timeout
    watchdog. Every background-task launch in this file goes through this
    (not raw asyncio.to_thread) so a comparison pause is never missed,
    however the run got to that point (fresh start, /intervene resume, or a
    previous preference commit continuing into a later step's comparison)."""
    await asyncio.to_thread(blocking_fn, *args)
    final_state = _runs.get(run_id)
    # Persist the generated code so it's fetchable/zippable even after the run
    # leaves memory. Safe to call every completion — save_run_code upserts and
    # no-ops on an empty file set.
    if final_state and final_state.get("spec"):
        files = final_state.get("workspace_files") or {}
        status = final_state.get("status", "done")
        if files:
            artifacts.save_run_code(run_id, files, status)
        # Accuracy = the latest critic verdict's overall score (0-10).
        history = final_state.get("critique_history") or []
        accuracy = history[-1]["overall"] if history else 0.0
        # One-row run history: prompt + plan + code + selected + cost/latency/accuracy.
        artifacts.save_run_history(
            run_id,
            prompt=final_state.get("spec", ""),
            plan=final_state.get("plan", []),
            files=files,
            selected=final_state.get("current_model") or "",
            status=status,
            total_cost=_cost_tracker.total_cost(run_id),
            latency_ms=_cost_tracker.total_latency(run_id),
            accuracy=accuracy,
        )
    if final_state and final_state.get("status") == "awaiting_preference":
        asyncio.create_task(_preference_timeout_watchdog(run_id))


def _bakeoff_winners(result: dict) -> list[dict]:
    """The chosen candidate per role (recommended model, or first if none)."""
    winners = []
    for role_result in result.get("roles", []):
        candidates = role_result.get("candidates", [])
        if not candidates:
            continue
        rec = role_result.get("recommended_model")
        winners.append(next((c for c in candidates if c["model"] == rec), candidates[0]))
    return winners


def _bakeoff_files(result: dict) -> dict[str, str]:
    """Merge each role's chosen candidate's files into one set — the bake-off's
    effective final output."""
    merged: dict[str, str] = {}
    for chosen in _bakeoff_winners(result):
        merged.update(chosen.get("files", {}))
    return merged


async def _agent_run_and_store(spec: str, run_id: str) -> None:
    """Run the team bake-off in a thread, then persist its code on completion."""
    await asyncio.to_thread(run_agent_mode, spec, run_id)
    result = get_agent_run(run_id)
    if result:
        files = _bakeoff_files(result)
        status = result.get("status", "done")
        artifacts.save_run_code(run_id, files, status)
        # Selected solution = the recommended model per role.
        selected = ", ".join(
            f"{r['role']['name']}={r.get('recommended_model')}"
            for r in result.get("roles", []) if r.get("recommended_model")
        )
        winners = _bakeoff_winners(result)
        # Latency = total across chosen candidates; accuracy = their mean critic score.
        latency_ms = sum(w.get("latency_ms", 0.0) for w in winners)
        accuracy = (
            sum(w.get("critic_score", 0.0) for w in winners) / len(winners)
            if winners else 0.0
        )
        artifacts.save_run_history(
            run_id,
            prompt=result.get("spec", ""),
            plan=[r["role"] for r in result.get("roles", [])],
            files=files,
            selected=selected,
            status=status,
            total_cost=result.get("total_cost", 0.0),
            latency_ms=latency_ms,
            accuracy=accuracy,
        )


def _collect_run_files(run_id: str) -> tuple[dict[str, str], str] | None:
    """Best-effort fetch of a run's code: SQL store first, then live memory
    (task/deliberation state, then bake-off result). Back-fills the store on a
    memory hit so later fetches are served from SQL."""
    stored = artifacts.get_run_code(run_id)
    if stored:
        return stored["files"], stored["status"]
    final_state = _runs.get(run_id)
    if final_state and final_state.get("workspace_files"):
        files, status = final_state["workspace_files"], final_state.get("status", "")
        artifacts.save_run_code(run_id, files, status)
        return files, status
    result = get_agent_run(run_id)
    if result:
        files = _bakeoff_files(result)
        if files:
            artifacts.save_run_code(run_id, files, result.get("status", ""))
            return files, result.get("status", "")
    return None


async def _preference_timeout_watchdog(run_id: str) -> None:
    await asyncio.sleep(PREFERENCE_TIMEOUT_SECONDS)
    _apply_preference_and_resume(run_id, dimension=None, auto=True)


def _apply_preference_and_resume(run_id: str, dimension: str | None, auto: bool = False) -> bool:
    """Resolve a paused comparison and resume the run. Returns False (no-op)
    if the run isn't actually paused awaiting a preference right now — either
    it already got resolved (explicit commit raced the timeout, or vice
    versa) or the run_id doesn't exist. Guarded by _preference_resolved so
    only one of {explicit commit, timeout} ever actually resumes a given
    pause."""
    if run_id in _preference_resolved:
        return False
    config = _config_for(run_id)
    snapshot = graph.get_state(config)
    if not snapshot.values or snapshot.values.get("status") != "awaiting_preference":
        return False

    _preference_resolved.add(run_id)
    updates = resolve_comparison(snapshot.values, dimension, auto=auto)
    graph.update_state(config, updates)
    _runs[run_id] = None
    asyncio.create_task(_run_and_watch(run_id, _resume_loop_sync, run_id))
    return True


@app.post("/run")
async def start_run(req: RunRequest):
    run_id = str(uuid.uuid4())
    _runs[run_id] = None
    asyncio.create_task(_run_and_watch(
        run_id, _run_loop_sync, req.spec, run_id, False, req.debate_mode, req.mode, req.preference,
    ))
    return {"run_id": run_id}


@app.post("/run/baseline")
async def start_baseline_run(req: RunRequest):
    run_id = str(uuid.uuid4())
    _runs[run_id] = None
    asyncio.create_task(_run_and_watch(run_id, _run_loop_sync, req.spec, run_id, True, req.debate_mode))
    return {"run_id": run_id}


@app.post("/run/{run_id}/commit-preference")
async def commit_preference(run_id: str, req: CommitPreferenceRequest):
    ok = _apply_preference_and_resume(run_id, req.dimension)
    if not ok:
        return {
            "status": "error",
            "detail": "run is not currently awaiting a preference "
                      "(already resolved, wrong run_id, or not paused there yet)",
        }
    return {"status": "resuming", "run_id": run_id, "dimension": req.dimension}


@app.post("/agent/run")
async def start_agent_run(req: AgentRunRequest):
    run_id = str(uuid.uuid4())
    # run_agent_mode registers itself in _agent_runs (status "running") before
    # doing any work, so GET /api/agent/{run_id} reports progress immediately.
    # The wrapper persists the produced code once the bake-off finishes.
    asyncio.create_task(_agent_run_and_store(req.spec, run_id))
    return {"run_id": run_id}


@app.get("/api/agent/{run_id}")
async def get_agent_result(run_id: str):
    result = get_agent_run(run_id)
    if result is None:
        return {"run_id": run_id, "status": "not_found", "result": None}
    return {"run_id": run_id, "status": result["status"], "result": result}


@app.post("/scheduler/reset")
async def reset_scheduler():
    # Clears both learned layers: routing pass-rate history AND the
    # similarity cache — after a reset every mode starts cold again.
    router_module.reset()
    similarity_module.reset()
    return {"status": "reset"}


@app.get("/api/costs/{run_id}")
async def get_costs(run_id: str):
    return {
        "run_id": run_id,
        "total_usd": _cost_tracker.total_cost(run_id),
        "breakdown": _cost_tracker.breakdown(run_id),
    }


@app.get("/api/costs/compare/{baseline_id}/{scheduler_id}")
async def compare_costs(baseline_id: str, scheduler_id: str):
    baseline_cost = _cost_tracker.total_cost(baseline_id)
    scheduler_cost = _cost_tracker.total_cost(scheduler_id)
    savings_pct = 0.0 if baseline_cost == 0 else (1 - scheduler_cost / baseline_cost) * 100
    return {
        "baseline_usd": baseline_cost,
        "scheduler_usd": scheduler_cost,
        "savings_pct": savings_pct,
    }


@app.get("/api/traces/{run_id}")
async def get_traces(run_id: str):
    return {"run_id": run_id, "entries": _trace_logger.read(run_id)}


@app.get("/api/runs/{run_id}")
async def get_run_status(run_id: str):
    if run_id not in _runs:
        return {"run_id": run_id, "status": "not_found"}
    final_state = _runs[run_id]
    if final_state is None:
        return {"run_id": run_id, "status": "running"}
    return {"run_id": run_id, "status": final_state["status"], "events": final_state["events"]}


@app.get("/api/runs")
async def list_run_history():
    """Index of all stored runs (prompt + selected + status + cost), newest first."""
    return {"runs": artifacts.list_runs()}


@app.get("/api/runs/{run_id}/history")
async def get_run_history(run_id: str):
    """The full record for a run: prompt, plan, generated code, and selected solution."""
    hist = artifacts.get_run_history(run_id)
    if hist is None:
        return {"run_id": run_id, "status": "not_found"}
    return {"run_id": run_id, **hist}


@app.get("/api/runs/{run_id}/code")
async def get_run_code(run_id: str):
    """Return the generated code ({path: content}) for a run, from SQL or memory."""
    collected = _collect_run_files(run_id)
    if collected is None:
        return {"run_id": run_id, "status": "not_found", "file_count": 0, "files": {}}
    files, status = collected
    return {"run_id": run_id, "status": status, "file_count": len(files), "files": files}


@app.get("/api/runs/{run_id}/code.zip")
async def download_run_code_zip(run_id: str):
    """Download the generated code for a run as a single .zip."""
    collected = _collect_run_files(run_id)
    if collected is None or not collected[0]:
        return Response(status_code=404, content=f"no code stored for run {run_id}")
    files, _status = collected
    return Response(
        content=artifacts.zip_bytes(files),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.zip"'},
    )


@app.post("/intervene")
async def intervene(req: InterveneRequest):
    config = _config_for(req.run_id)
    snapshot = graph.get_state(config)
    if not snapshot.values:
        return {"status": "error", "detail": f"no checkpoint found for run_id {req.run_id}"}

    # Injects the correction and routes back to the Planner; picked up on
    # the next resume since the graph pauses after every critic verdict
    # (interrupt_after=["critic"]).
    graph.update_state(config, {
        "pending_correction": f"[step {req.step_id}] {req.correction_text}",
        "status": "planning",
    })
    _runs[req.run_id] = None
    asyncio.create_task(_run_and_watch(req.run_id, _resume_loop_sync, req.run_id))
    return {"status": "resuming", "run_id": req.run_id}


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await emitter.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        emitter.disconnect(websocket)
