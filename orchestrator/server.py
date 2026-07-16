import asyncio
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from orchestrator.events import emitter
from orchestrator.graph import _initial_state, graph, run_to_completion
from scheduler import router as router_module
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


class RunRequest(BaseModel):
    spec: str


class InterveneRequest(BaseModel):
    run_id: str
    step_id: str
    correction_text: str


@app.on_event("startup")
async def _bind_emitter_loop():
    emitter.bind_loop(asyncio.get_running_loop())


def _config_for(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 100}


def _run_loop_sync(spec: str, run_id: str, baseline_mode: bool) -> None:
    state = _initial_state(spec, run_id=run_id, baseline_mode=baseline_mode)
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


@app.post("/run")
async def start_run(req: RunRequest):
    run_id = str(uuid.uuid4())
    _runs[run_id] = None
    asyncio.create_task(asyncio.to_thread(_run_loop_sync, req.spec, run_id, False))
    return {"run_id": run_id}


@app.post("/run/baseline")
async def start_baseline_run(req: RunRequest):
    run_id = str(uuid.uuid4())
    _runs[run_id] = None
    asyncio.create_task(asyncio.to_thread(_run_loop_sync, req.spec, run_id, True))
    return {"run_id": run_id}


@app.post("/scheduler/reset")
async def reset_scheduler():
    router_module.reset()
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
    asyncio.create_task(asyncio.to_thread(_resume_loop_sync, req.run_id))
    return {"status": "resuming", "run_id": req.run_id}


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await emitter.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        emitter.disconnect(websocket)
