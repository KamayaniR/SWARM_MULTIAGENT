from datetime import datetime, timezone

from agents.coder import run_coder
from agents.critic import passed, run_critic
from agents.planner import run_planner
from orchestrator.events import emitter
from orchestrator.state import SwarmState
from sandbox.manager import SandboxManager
from scheduler import debate, plan_cache, router
from scheduler.models import resolve_model
from scheduler.tracked_client import TrackedLLMClient

# Constructed lazily so importing this module (e.g. for tests or graph
# inspection) doesn't require live API keys or a running Docker daemon.
_client: TrackedLLMClient | None = None
_sandbox: SandboxManager | None = None

# container_id per run_id, kept outside SwarmState since it's not serializable
_containers: dict[str, str] = {}


def _get_client() -> TrackedLLMClient:
    global _client
    if _client is None:
        _client = TrackedLLMClient()
    return _client


def _get_sandbox() -> SandboxManager:
    global _sandbox
    if _sandbox is None:
        _sandbox = SandboxManager()
    return _sandbox


def cleanup_run(run_id: str) -> None:
    """Stop and remove the sandbox container for a run, if one was created.
    Safe to call even if no container exists yet (e.g. the run failed
    during planning) or cleanup already happened."""
    container_id = _containers.pop(run_id, None)
    if container_id is not None:
        _get_sandbox().cleanup(container_id)


def _event(agent: str, action: str, state: SwarmState, **fields) -> dict:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": state["run_id"],
        "agent": agent,
        "action": action,
        "step_id": "",
        "step_class": "",
        "model": None,
        "provider": None,
        "routing_reason": "",
        "difficulty": None,
        "input_tokens": None,
        "output_tokens": None,
        "cost_usd": 0.0,
        "latency_ms": 0.0,
        "iteration": state.get("iteration", 0),
        "outcome": None,
        "critic_score": None,
        "tests_passed": None,
        "tests_total": None,
        "detail": "",
        **fields,
    }
    emitter.emit(event)
    return event


def _current_step(state: SwarmState):
    return state["plan"][state["current_step_index"]]


def planner_node(state: SwarmState) -> dict:
    spec = state["spec"]
    correction = state.get("pending_correction")
    if correction:
        spec = f"{spec}\n\nHuman correction — apply this to the plan:\n{correction}"

    plan = run_planner(_get_client(), spec, state["run_id"])
    event = _event(
        "planner", "plan_created", state,
        detail=f"created plan with {len(plan)} steps"
        + (" (re-planned from human correction)" if correction else ""),
    )
    return {
        "plan": plan,
        "current_step_index": 0,
        "status": "routing",
        "iteration": 0,
        "pending_correction": None,
        "events": state["events"] + [event],
    }


def cache_gate_node(state: SwarmState) -> dict:
    """After planning, look for a past successful run whose plan is structurally
    similar (>= threshold) to this one. On a hit we hand off to cache_verify to
    reuse that run's solution and skip the per-step debate + coder loop."""
    if not state.get("cache_enabled", True):
        return {"cache_hit": None}

    signature = plan_cache.signature_from_plan(state["plan"])
    match = plan_cache.lookup("loop", signature)
    if match is None:
        event = _event(
            "cache", "cache_miss", state,
            detail="no prior plan matched — running full loop",
        )
        return {"cache_hit": None, "events": state["events"] + [event]}

    event = _event(
        "cache", "cache_lookup", state,
        detail=f"plan matches run {match['run_id'][:8]} "
               f"({match['score'] * 100:.0f}%) — verifying before reuse",
    )
    return {"cache_hit": match, "events": state["events"] + [event]}


def cache_verify_node(state: SwarmState) -> dict:
    """Replay the matched run's files through the sandbox + Critic against the
    NEW spec. Pass -> serve instantly (debate + coder + retries all skipped).
    Fail -> keep the files as a warm start and fall through to the normal loop."""
    run_id = state["run_id"]
    match = state["cache_hit"]
    cached_files = match["payload"]["files"]
    sandbox = _get_sandbox()

    if run_id not in _containers:
        _containers[run_id] = sandbox.create()
    sandbox.inject_files(_containers[run_id], cached_files)
    results = sandbox.run_tests(_containers[run_id])

    verdict = run_critic(
        _get_client(), state["spec"], cached_files, results, run_id, "cache", 0
    )
    ok = passed(verdict, results)

    if ok:
        event = _event(
            "cache", "cache_hit", state,
            critic_score=verdict["overall"], outcome="pass",
            tests_passed=results["tests_passed"], tests_total=results["tests_total"],
            detail=f"reused run {match['run_id'][:8]} "
                   f"({match['score'] * 100:.0f}% plan match) — verified, "
                   f"skipped debate + coder",
        )
        return {
            "workspace_files": cached_files,
            "test_results": results,
            "critique_history": state["critique_history"] + [verdict],
            "status": "done",
            "served_from_cache": True,
            "events": state["events"] + [event],
        }

    event = _event(
        "cache", "cache_verify_fail", state,
        critic_score=verdict["overall"], outcome="fail",
        tests_passed=results["tests_passed"], tests_total=results["tests_total"],
        detail=f"cached solution from run {match['run_id'][:8]} failed on new "
               f"spec — warm-starting the full loop",
    )
    return {
        "workspace_files": cached_files,
        "test_results": None,
        "status": "routing",
        "current_step_index": 0,
        "iteration": 0,
        "events": state["events"] + [event],
    }


def router_node(state: SwarmState) -> dict:
    step = _current_step(state)
    new_events: list[dict] = []

    if state.get("baseline_mode"):
        model = resolve_model("gpt-5.5")
        reason = "baseline mode: always gpt-5.5"
    elif state.get("debate_mode", True):
        model, reason, transcript = debate.route_debate(
            _get_client(), step["description"], step["step_class"], state["run_id"]
        )
        # Surface each turn of the debate so the decision log shows the
        # back-and-forth, not just the final pick.
        for turn in transcript:
            verb = "accepts" if turn["accepted"] else "proposes"
            new_events.append(_event(
                "router", "debate_turn", state,
                step_id=step["id"], step_class=step["step_class"],
                model=turn["proposal"],
                detail=f"{turn['speaker']} {verb} {turn['proposal']}: {turn['rationale']}",
            ))
    else:
        model, reason = router.route(_get_client(), step["description"], step["step_class"], state["run_id"])

    event = _event(
        "router", "classify", state,
        step_id=step["id"], step_class=step["step_class"],
        model=model, routing_reason=reason,
        detail=reason,
    )
    return {
        "current_model": model,
        "routing_reason": reason,
        "status": "coding",
        "events": state["events"] + new_events + [event],
    }


def coder_node(state: SwarmState) -> dict:
    step = _current_step(state)
    run_id = state["run_id"]
    sandbox = _get_sandbox()

    if run_id not in _containers:
        _containers[run_id] = sandbox.create()

    last_feedback = None
    if state["critique_history"]:
        last = state["critique_history"][-1]
        if last["failure_type"] == "step_level":
            last_feedback = "\n".join(last["feedback"])

    new_files = run_coder(
        _get_client(), step, state["workspace_files"], last_feedback,
        state["current_model"], run_id, state["iteration"],
    )
    workspace_files = {**state["workspace_files"], **new_files}
    sandbox.inject_files(_containers[run_id], workspace_files)

    event = _event(
        "coder", "implement", state,
        step_id=step["id"], step_class=step["step_class"],
        model=state["current_model"],
        detail=f"wrote {len(new_files)} file(s)",
    )
    return {
        "workspace_files": workspace_files,
        "status": "testing",
        "events": state["events"] + [event],
    }


def tester_node(state: SwarmState) -> dict:
    run_id = state["run_id"]
    results = _get_sandbox().run_tests(_containers[run_id])
    step = _current_step(state)

    event = _event(
        "tester", "run_tests", state,
        step_id=step["id"], step_class=step["step_class"],
        tests_passed=results["tests_passed"], tests_total=results["tests_total"],
        detail=f"{results['tests_passed']}/{results['tests_total']} passed",
    )
    return {
        "test_results": results,
        "status": "judging",
        "events": state["events"] + [event],
    }


def critic_node(state: SwarmState) -> dict:
    step = _current_step(state)
    verdict = run_critic(
        _get_client(), state["spec"], state["workspace_files"], state["test_results"],
        state["run_id"], step["id"], state["iteration"],
    )
    step_passed = passed(verdict, state["test_results"])
    router.record_outcome(step["step_class"], state["current_model"], step_passed, verdict["overall"])

    outcome = "pass" if step_passed else "fail"
    event = _event(
        "critic", "verdict", state,
        step_id=step["id"], step_class=step["step_class"],
        critic_score=verdict["overall"], outcome=outcome,
        detail=f"score {verdict['overall']:.1f} -> {outcome.upper()}",
    )

    updates: dict = {
        "critique_history": state["critique_history"] + [verdict],
        "events": state["events"] + [event],
    }

    if step_passed:
        plan = list(state["plan"])
        plan[state["current_step_index"]] = {**step, "status": "passed"}
        next_index = state["current_step_index"] + 1
        if next_index >= len(plan):
            updates["status"] = "done"
        else:
            updates["current_step_index"] = next_index
            updates["status"] = "routing"
            updates["iteration"] = 0
        updates["plan"] = plan
        return updates

    if verdict["failure_type"] == "plan_level":
        updates["status"] = "planning"
        return updates

    # step_level failure
    next_iteration = state["iteration"] + 1
    if next_iteration >= state["max_iterations"]:
        updates["status"] = "escalated"
    else:
        updates["iteration"] = next_iteration
        updates["status"] = "routing"
    return updates


def decide_after_cache(state: SwarmState) -> str:
    return "verify" if state.get("cache_hit") else "no_match"


def decide_after_verify(state: SwarmState) -> str:
    # cache_verify sets status="done" on a verified hit, else "routing" to fall
    # through into the normal loop warm-started with the cached files.
    return "done" if state["status"] == "done" else "fallthrough"


def decide_next(state: SwarmState) -> str:
    status = state["status"]
    if status == "done":
        return "done"
    if status == "escalated":
        return "escalate"
    if status == "planning":
        return "replan"
    return "next_step"  # covers both pass-and-advance and retry; both route through router_node
