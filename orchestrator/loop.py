from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from agents.coder import run_coder
from agents.critic import passed, run_critic
from agents.planner import run_planner
from orchestrator.events import emitter
from orchestrator.state import SwarmState
from sandbox.factory import get_sandbox as _make_sandbox
from scheduler import debate, deliberation, router, similarity
from scheduler.models import MODEL_PRICES, resolve_model
from scheduler.tracked_client import TrackedLLMClient

# Constructed lazily so importing this module (e.g. for tests or graph
# inspection) doesn't require live API keys or a running Docker daemon.
_client: TrackedLLMClient | None = None
# SandboxManager (local Docker) or AkashSandbox (pooled Akash), chosen at
# runtime by SANDBOX_BACKEND via sandbox.factory.
_sandbox = None

# container_id per run_id, kept outside SwarmState since it's not serializable
_containers: dict[str, str] = {}


def _get_client() -> TrackedLLMClient:
    global _client
    if _client is None:
        _client = TrackedLLMClient()
    return _client


def _get_sandbox():
    """Process-wide sandbox backend (local Docker or Akash pool), selected by
    SANDBOX_BACKEND. Constructed lazily and reused across runs; both backends
    expose the same create/inject_files/run_tests/cleanup surface."""
    global _sandbox
    if _sandbox is None:
        _sandbox = _make_sandbox()
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
        "candidates": None,
        "similarity_score": None,
        "matched_step_id": None,
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


def router_node(state: SwarmState) -> dict:
    step = _current_step(state)
    new_events: list[dict] = []
    updates: dict = {
        "candidate_models": [],
        "similarity_match": None,
        "status": "coding",
    }

    if state.get("baseline_mode"):
        model = resolve_model("gpt-5.5")
        reason = "baseline mode: always gpt-5.5"
    elif state.get("mode", "task") == "agent":
        model, reason = _agent_mode_route(state, step, new_events, updates)
    elif state.get("debate_mode", False):
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
        candidates=updates.get("candidate_models") or None,
        detail=reason,
    )
    updates.update({
        "current_model": model,
        "routing_reason": reason,
        "events": state["events"] + new_events + [event],
    })
    return updates


def _agent_mode_route(state: SwarmState, step: dict, new_events: list[dict], updates: dict) -> tuple[str, str]:
    """Agent-mode routing: similarity check first; on a strong match reuse the
    historical winner and skip the deliberation; otherwise deliberate to get 2
    candidates for the dual-sandbox comparison.

    Retries (iteration > 0) always re-deliberate: the previous winner just
    failed the Critic, so replaying history would lock the failure in.
    Returns (model, reason) — model is provisional (candidates[0]) when a
    comparison is pending; coder_node resolves the final winner."""
    client = _get_client()

    if state["iteration"] == 0:
        match, score = similarity.check_similarity(
            client, step["description"], step["step_class"], state["run_id"]
        )
        if match is not None and score >= similarity.SIMILARITY_THRESHOLD:
            model = resolve_model(match["winning_model"])
            reason = (
                f"matched historical step (similarity {score:.2f}) -> "
                f"reusing {model}, skipped debate"
            )
            new_events.append(_event(
                "router", "similarity_skip", state,
                step_id=step["id"], step_class=step["step_class"],
                model=model, similarity_score=score,
                matched_step_id=str(match["id"]),
                detail=reason,
            ))
            updates["similarity_match"] = {**match, "score": score}
            return model, reason

    candidates, rationales, transcript, reason = deliberation.deliberate(
        client, step["description"], step["step_class"], state["run_id"]
    )
    for turn in transcript:
        pair = " + ".join(turn["candidates"])
        new_events.append(_event(
            "debate", "deliberation_turn", state,
            step_id=step["id"], step_class=step["step_class"],
            model=turn["voice_model"], candidates=turn["candidates"],
            detail=f"[round {turn['round']}] {turn['speaker']} proposes {pair}: {turn['rationale']}",
        ))
    updates["candidate_models"] = candidates
    updates["debate_transcript"] = state["debate_transcript"] + transcript
    return candidates[0], reason


def _last_feedback(state: SwarmState) -> str | None:
    if state["critique_history"]:
        last = state["critique_history"][-1]
        if last["failure_type"] == "step_level":
            return "\n".join(last["feedback"])
    return None


def _build_candidate(state: SwarmState, step: dict, model: str, feedback: str | None) -> dict:
    """Build one candidate model for the current step in its own fresh sandbox
    and fully judge it: real Coder call, real pytest, real Critic verdict.
    Cost is isolated under a per-candidate sub-run-id so the comparison table
    shows each candidate's true spend."""
    client = _get_client()
    sandbox = _get_sandbox()
    model = resolve_model(model)
    sub_run_id = f"{state['run_id']}::{step['id']}::{model}::{state['iteration']}"

    start = datetime.now(timezone.utc)
    container_id = None
    try:
        files = run_coder(
            client, step, state["workspace_files"], feedback,
            model, sub_run_id, state["iteration"],
        )
        merged = {**state["workspace_files"], **files}

        container_id = sandbox.create()
        sandbox.inject_files(container_id, merged)
        results = sandbox.run_tests(container_id)

        verdict = run_critic(
            client, state["spec"], merged, results,
            sub_run_id, step["id"], state["iteration"],
        )
        candidate_passed = passed(verdict, results)
        return {
            "model": model,
            "provider": MODEL_PRICES[model]["provider"],
            "files": files,
            "test_results": results,
            "verdict": verdict,
            "critic_score": verdict["overall"],
            "tests_passed": results["tests_passed"],
            "tests_total": results["tests_total"],
            "cost_usd": client.cost_tracker.total_cost(sub_run_id),
            "latency_ms": (datetime.now(timezone.utc) - start).total_seconds() * 1000,
            "passed": candidate_passed,
            "error": None,
        }
    except Exception as e:
        return {
            "model": model,
            "provider": MODEL_PRICES[model]["provider"],
            "files": {},
            "test_results": {"exit_code": 1, "stdout": "", "stderr": str(e), "tests_passed": 0, "tests_total": 0},
            "verdict": None,
            "critic_score": 0.0,
            "tests_passed": 0,
            "tests_total": 0,
            "cost_usd": client.cost_tracker.total_cost(sub_run_id),
            "latency_ms": (datetime.now(timezone.utc) - start).total_seconds() * 1000,
            "passed": False,
            "error": str(e),
        }
    finally:
        if container_id is not None:
            try:
                sandbox.cleanup(container_id)
            except Exception:
                pass


def _select_winner(results: list[dict], preference: str | None) -> dict:
    """Resolve the comparison to one candidate.

    Passing candidates are always preferred over failing ones; the preference
    then ranks within that group. Default (no preference / "accuracy"):
    highest accuracy wins, ties broken by lowest cost."""
    pool = [r for r in results if r["passed"]] or results
    if preference == "cost":
        return min(pool, key=lambda r: r["cost_usd"])
    if preference == "latency":
        return min(pool, key=lambda r: r["latency_ms"])
    return min(pool, key=lambda r: (-r["critic_score"], r["cost_usd"]))


def coder_node(state: SwarmState) -> dict:
    step = _current_step(state)
    run_id = state["run_id"]
    sandbox = _get_sandbox()
    last_feedback = _last_feedback(state)

    candidates = state.get("candidate_models") or []
    if len(candidates) == 2:
        return _comparison_coder(state, step, candidates, last_feedback)

    if run_id not in _containers:
        _containers[run_id] = sandbox.create()

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


def _comparison_coder(state: SwarmState, step: dict, candidates: list[str], feedback: str | None) -> dict:
    """Agent-mode dual-candidate path: build the step with BOTH candidate
    models concurrently in isolated sandboxes, fully judge both, then PAUSE —
    winner selection is deferred to whoever answers the preference (a person
    via POST /run/{run_id}/commit-preference, or the timeout watchdog applying
    the default rule). The graph is routed to comparison_gate next, which is
    the interrupt point (see graph.py); resolve_comparison() in this module is
    what actually picks the winner once an answer arrives."""
    new_events: list[dict] = []

    new_events.append(_event(
        "coder", "comparison_start", state,
        step_id=step["id"], step_class=step["step_class"],
        candidates=candidates,
        detail=f"building {candidates[0]} vs {candidates[1]} in parallel sandboxes",
    ))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda m: _build_candidate(state, step, m, feedback), candidates
        ))

    for r in results:
        # Feed each candidate's outcome into the routing history so future
        # deliberations argue from real evidence about both models.
        if r["error"] is None:
            router.record_outcome(step["step_class"], r["model"], r["passed"], r["critic_score"])
        outcome = "error" if r["error"] else ("pass" if r["passed"] else "fail")
        new_events.append(_event(
            "evaluator", "candidate_result", state,
            step_id=step["id"], step_class=step["step_class"],
            model=r["model"], outcome=outcome,
            critic_score=r["critic_score"],
            tests_passed=r["tests_passed"], tests_total=r["tests_total"],
            cost_usd=r["cost_usd"], latency_ms=r["latency_ms"],
            detail=f"{r['model']}: score {r['critic_score']:.1f}, "
                   f"${r['cost_usd']:.4f}, {r['latency_ms'] / 1000:.1f}s"
                   + (f" — error: {r['error']}" if r["error"] else ""),
        ))

    new_events.append(_event(
        "evaluator", "awaiting_preference", state,
        step_id=step["id"], step_class=step["step_class"], candidates=candidates,
        detail=f"both candidates finished — awaiting preference (cost/accuracy/latency) "
               f"or auto-default after {PREFERENCE_TIMEOUT_SECONDS}s",
    ))

    # Kept in full (not stripped) — resolve_comparison() needs each
    # candidate's test_results + verdict to hand the winner forward without
    # re-running or re-judging.
    return {
        "candidate_models": [],
        "candidate_results": results,
        "status": "awaiting_preference",
        "events": state["events"] + new_events,
    }


PREFERENCE_TIMEOUT_SECONDS = 120


def comparison_gate_node(state: SwarmState) -> dict:
    """No-op node. Its only purpose is to be the interrupt_after target for
    the awaiting_preference pause (see graph.py) — pausing here, rather than
    adding "coder" itself to interrupt_after, keeps Task mode's coder_node
    calls from ever being affected: Task mode never routes through this node."""
    return {}


def resolve_comparison(state: SwarmState, dimension: str | None, auto: bool = False) -> dict:
    """Resolve a paused agent-mode comparison: pick the winner by `dimension`
    (None -> default rule), inject its files into the run's sandbox container,
    and return the update that resumes the loop into tester_node's
    pass-through branch. Called by POST /run/{run_id}/commit-preference and by
    the timeout watchdog (auto=True) when nobody answers in time."""
    step = _current_step(state)
    results = state["candidate_results"]
    winner = _select_winner(results, dimension)

    workspace_files = {**state["workspace_files"], **winner["files"]}
    sandbox = _get_sandbox()
    run_id = state["run_id"]
    if run_id not in _containers:
        _containers[run_id] = sandbox.create()
    sandbox.inject_files(_containers[run_id], workspace_files)

    rule = dimension or "default (highest accuracy, tie -> lowest cost)"
    if auto:
        rule += f" — auto-applied after {PREFERENCE_TIMEOUT_SECONDS}s with no response"
    event = _event(
        "evaluator", "winner_selected", state,
        step_id=step["id"], step_class=step["step_class"],
        model=winner["model"], candidates=[r["model"] for r in results],
        critic_score=winner["critic_score"],
        detail=f"selected {winner['model']} by {rule}",
    )

    return {
        "workspace_files": workspace_files,
        "current_model": winner["model"],
        "test_results": winner["test_results"],
        "pending_verdict": winner["verdict"],
        "status": "testing",
        "events": state["events"] + [event],
    }


def tester_node(state: SwarmState) -> dict:
    step = _current_step(state)

    if state.get("pending_verdict") is not None:
        # Dual-candidate comparison already ran the winner's tests in its own
        # sandbox — pass those results through instead of re-running.
        results = state["test_results"]
        event = _event(
            "tester", "run_tests", state,
            step_id=step["id"], step_class=step["step_class"],
            tests_passed=results["tests_passed"], tests_total=results["tests_total"],
            detail=f"{results['tests_passed']}/{results['tests_total']} passed (from comparison winner)",
        )
        return {"status": "judging", "events": state["events"] + [event]}

    run_id = state["run_id"]
    results = _get_sandbox().run_tests(_containers[run_id])

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

    pending = state.get("pending_verdict")
    if pending is not None:
        # The comparison already fully judged the winner — consume that
        # verdict instead of paying for a second Critic call. Its outcome was
        # also already recorded to routing history in the comparison.
        verdict = pending
        step_passed = passed(verdict, state["test_results"])
    else:
        verdict = run_critic(
            _get_client(), state["spec"], state["workspace_files"], state["test_results"],
            state["run_id"], step["id"], state["iteration"],
        )
        step_passed = passed(verdict, state["test_results"])
        router.record_outcome(step["step_class"], state["current_model"], step_passed, verdict["overall"])

    # Cache the deliberation outcome for future similarity matching — only on
    # a pass (caching a model that just failed would lock the failure in), and
    # only when this step actually deliberated (a similarity-skip step is
    # already in history; re-recording would pile up near-duplicate entries).
    if (
        state.get("mode", "task") == "agent"
        and step_passed
        and state.get("similarity_match") is None
    ):
        similarity.record_step(
            _get_client(), state["spec"], step["description"], step["step_class"],
            state["current_model"], state["run_id"],
        )

    outcome = "pass" if step_passed else "fail"
    # Every call already persisted for this step (Coder's, this Critic call
    # included) had outcome=NULL when it was written -- the pass/fail is
    # only known now. Rewrite them so accuracy_per_model() has real data.
    _get_client().cost_tracker.update_outcome(step["id"], outcome, state["run_id"])
    event = _event(
        "critic", "verdict", state,
        step_id=step["id"], step_class=step["step_class"],
        critic_score=verdict["overall"], outcome=outcome,
        detail=f"score {verdict['overall']:.1f} -> {outcome.upper()}"
        + (" (from comparison winner)" if pending is not None else ""),
    )

    updates: dict = {
        "critique_history": state["critique_history"] + [verdict],
        "pending_verdict": None,
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
