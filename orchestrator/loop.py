from datetime import datetime, timezone

import anthropic

from agents.coder import run_coder
from agents.critic import passed, run_critic
from agents.planner import run_planner
from orchestrator.state import SwarmState
from sandbox.manager import SandboxManager

_client = anthropic.Anthropic()
_sandbox = SandboxManager()

# container_id per run_id, kept outside SwarmState since it's not serializable
_containers: dict[str, str] = {}


def _event(agent: str, action: str, state: SwarmState, **fields) -> dict:
    return {
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


def _current_step(state: SwarmState):
    return state["plan"][state["current_step_index"]]


def planner_node(state: SwarmState) -> dict:
    plan = run_planner(_client, state["spec"], state["run_id"])
    event = _event(
        "planner", "plan_created", state,
        detail=f"created plan with {len(plan)} steps",
    )
    return {
        "plan": plan,
        "current_step_index": 0,
        "status": "routing",
        "iteration": 0,
        "events": state["events"] + [event],
    }


def router_node(state: SwarmState) -> dict:
    # Hardcoded for now — replaced by scheduler.router.route() in step 10.
    model = "claude-sonnet-5"
    reason = "hardcoded to sonnet (router not wired yet)"
    step = _current_step(state)
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
        "events": state["events"] + [event],
    }


def coder_node(state: SwarmState) -> dict:
    step = _current_step(state)
    run_id = state["run_id"]

    if run_id not in _containers:
        _containers[run_id] = _sandbox.create()

    last_feedback = None
    if state["critique_history"]:
        last = state["critique_history"][-1]
        if last["failure_type"] == "step_level":
            last_feedback = "\n".join(last["feedback"])

    new_files = run_coder(
        _client, step, state["workspace_files"], last_feedback,
        state["current_model"], run_id, state["iteration"],
    )
    workspace_files = {**state["workspace_files"], **new_files}
    _sandbox.inject_files(_containers[run_id], workspace_files)

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
    results = _sandbox.run_tests(_containers[run_id])
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
        _client, state["spec"], state["workspace_files"], state["test_results"],
        state["run_id"], step["id"], state["iteration"],
    )
    step_passed = passed(verdict, state["test_results"])

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


def decide_next(state: SwarmState) -> str:
    status = state["status"]
    if status == "done":
        return "done"
    if status == "escalated":
        return "escalate"
    if status == "planning":
        return "replan"
    return "next_step"  # covers both pass-and-advance and retry; both route through router_node
