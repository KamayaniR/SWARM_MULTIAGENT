"""Agent mode — team composition + per-role model bake-off.

Given a task, this:
  1. Asks the Team Planner how many agents (roles) are needed and what each does.
  2. For each role, runs the routing debate to pick two candidate models to
     bake off against each other (a deliberate cheap-vs-quality matchup).
  3. Actually builds each candidate in its OWN isolated sandbox — real Coder
     call, real pytest run, real Critic verdict, real measured cost/latency.
  4. Recommends, per role, the cheapest candidate that passed (or, if none
     passed, the highest-scoring one).
  5. Assembles a TeamResult the dashboard renders as a side-by-side comparison,
     including the generated code so the user can take any candidate's output.

This is a separate orchestration from the sequential LangGraph loop in
orchestrator/loop.py — it fans out across roles x candidates rather than
walking a plan step by step — but it reuses the same client, sandbox, agents,
cost tracking, and event emitter.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional, TypedDict

from agents.coder import run_coder
from agents.critic import passed, run_critic
from agents.team_planner import AgentRole, run_team_planner
from orchestrator.events import emitter
from orchestrator.loop import _get_client, _get_sandbox
from scheduler import plan_cache, team
from scheduler.models import MODEL_PRICES, resolve_model


class CandidateResult(TypedDict):
    model: str
    provider: str
    files: dict[str, str]
    critic_score: float
    tests_passed: int
    tests_total: int
    cost_usd: float
    latency_ms: float
    passed: bool
    error: Optional[str]


class Recommendations(TypedDict):
    accuracy: Optional[str]   # highest critic_score
    latency: Optional[str]    # fastest (among passers)
    cost: Optional[str]       # cheapest (among passers)
    fits_all: Optional[str]   # set when one model wins all three objectives


class RoleResult(TypedDict):
    role: AgentRole
    candidates: list[CandidateResult]
    recommended_model: Optional[str]     # cheapest passer (kept for back-compat)
    recommendations: Recommendations     # best model per objective


class TeamResult(TypedDict):
    run_id: str
    status: str                 # running | done | error
    spec: str
    roles: list[RoleResult]
    total_cost: float
    detail: str


# run_id -> TeamResult. status flips running -> done/error when the run finishes.
_agent_runs: dict[str, TeamResult] = {}


def get_agent_run(run_id: str) -> Optional[TeamResult]:
    return _agent_runs.get(run_id)


def _emit(run_id: str, agent: str, action: str, **fields) -> None:
    """Emit an event in the same schema shape as orchestrator/loop.py::_event,
    so the dashboard's existing WebSocket/DecisionLog handle it unchanged."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
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
        "iteration": 0,
        "outcome": None,
        "critic_score": None,
        "tests_passed": None,
        "tests_total": None,
        "detail": "",
        **fields,
    }
    emitter.emit(event)


def _role_as_step(role: AgentRole) -> dict:
    """Adapt an AgentRole into the PlanStep shape run_coder/run_critic expect."""
    return {
        "id": role["id"],
        "description": role["probe_description"],
        "step_class": role["step_class"],
        "est_loc": 0,
        "deps": [],
        "acceptance": role["acceptance"],
        "status": "pending",
    }


def _bake_candidate(run_id: str, role: AgentRole, model: str) -> CandidateResult:
    """Build one candidate model for one role in its own fresh sandbox and
    score it. Cost/latency are isolated by giving this candidate its own
    sub-run-id for tracked calls, so overlapping models (e.g. a Sonnet
    candidate vs. the always-Sonnet Critic) never pollute each other's cost."""
    client = _get_client()
    sandbox = _get_sandbox()
    model = resolve_model(model)
    provider = MODEL_PRICES[model]["provider"]
    step = _role_as_step(role)
    sub_run_id = f"{run_id}::{role['id']}::{model}"

    start = datetime.now(timezone.utc)
    container_id: Optional[str] = None
    try:
        _emit(run_id, "coder", "implement", step_id=role["id"],
              step_class=role["step_class"], model=model,
              detail=f"[{role['name']}] {model} building…")

        files = run_coder(client, step, {}, None, model, sub_run_id, iteration=0)

        container_id = sandbox.create()
        sandbox.inject_files(container_id, files)
        results = sandbox.run_tests(container_id)

        _emit(run_id, "tester", "run_tests", step_id=role["id"],
              step_class=role["step_class"], model=model,
              tests_passed=results["tests_passed"], tests_total=results["tests_total"],
              detail=f"[{role['name']}] {model}: {results['tests_passed']}/{results['tests_total']} passed")

        verdict = run_critic(
            client, role["probe_description"], files, results,
            sub_run_id, role["id"], iteration=0,
        )
        candidate_passed = passed(verdict, results)
        cost = client.cost_tracker.total_cost(sub_run_id)
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        _emit(run_id, "evaluator", "bakeoff_result", step_id=role["id"],
              step_class=role["step_class"], model=model,
              critic_score=verdict["overall"],
              outcome="pass" if candidate_passed else "fail",
              tests_passed=results["tests_passed"], tests_total=results["tests_total"],
              cost_usd=cost, latency_ms=latency_ms,
              detail=f"[{role['name']}] {model}: score {verdict['overall']:.1f}, "
                     f"${cost:.4f} -> {'PASS' if candidate_passed else 'FAIL'}")

        return CandidateResult(
            model=model, provider=provider, files=files,
            critic_score=verdict["overall"],
            tests_passed=results["tests_passed"], tests_total=results["tests_total"],
            cost_usd=cost, latency_ms=latency_ms, passed=candidate_passed, error=None,
        )
    except Exception as e:
        cost = client.cost_tracker.total_cost(sub_run_id)
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        _emit(run_id, "evaluator", "bakeoff_result", step_id=role["id"],
              step_class=role["step_class"], model=model, outcome="error",
              cost_usd=cost, detail=f"[{role['name']}] {model}: error — {e}")
        return CandidateResult(
            model=model, provider=provider, files={}, critic_score=0.0,
            tests_passed=0, tests_total=0, cost_usd=cost, latency_ms=latency_ms,
            passed=False, error=str(e),
        )
    finally:
        if container_id is not None:
            try:
                sandbox.cleanup(container_id)
            except Exception:
                pass


def _recommend(candidates: list[CandidateResult]) -> Optional[str]:
    """Cheapest candidate that passed; if none passed, the highest-scoring one."""
    winners = [c for c in candidates if c["passed"]]
    if winners:
        return min(winners, key=lambda c: c["cost_usd"])["model"]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["critic_score"])["model"]


def _recommendations(candidates: list[CandidateResult]) -> Recommendations:
    """Best model per objective. There's no single 'best' model — it depends on
    what you optimise for, so we surface the winner for accuracy, latency, and
    cost separately, and flag when one model happens to win all three.

    Accuracy ranks over all candidates (even a failing model can be the most
    accurate attempt). Latency and cost rank only over passers — a fast/cheap
    model that doesn't actually work isn't a real option."""
    if not candidates:
        return Recommendations(accuracy=None, latency=None, cost=None, fits_all=None)

    passers = [c for c in candidates if c["passed"]] or candidates
    accuracy = max(candidates, key=lambda c: c["critic_score"])["model"]
    latency = min(passers, key=lambda c: c["latency_ms"])["model"]
    cost = min(passers, key=lambda c: c["cost_usd"])["model"]
    fits_all = accuracy if accuracy == latency == cost else None
    return Recommendations(accuracy=accuracy, latency=latency, cost=cost, fits_all=fits_all)


def run_agent_mode(spec: str, run_id: str) -> TeamResult:
    """Drive the full agent-mode orchestration to completion. Synchronous —
    intended to run in a background thread (see server.py), like the loop."""
    result: TeamResult = {
        "run_id": run_id, "status": "running", "spec": spec,
        "roles": [], "total_cost": 0.0, "detail": "",
    }
    # Register before constructing the client so a misconfigured environment
    # (e.g. missing API key) reports status "error" via GET /api/agent/{run_id}
    # rather than leaving the run stuck at "not_found".
    _agent_runs[run_id] = result

    try:
        client = _get_client()
        roles = run_team_planner(client, spec, run_id)
        _emit(run_id, "team_planner", "team_planned",
              detail=f"team of {len(roles)} agent(s): "
                     + ", ".join(r["name"] for r in roles))

        # If a prior run's team plan is structurally similar, reuse its cached
        # bake-off comparison instead of re-running every candidate model.
        signature = plan_cache.signature_from_roles(roles)
        hit = plan_cache.lookup("team", signature)
        if hit is not None:
            cached: TeamResult = hit["payload"]
            cached["run_id"] = run_id
            cached["status"] = "done"
            cached["detail"] = (
                f"reused prior bake-off ({hit['score'] * 100:.0f}% team match "
                f"to run {hit['run_id'][:8]})"
            )
            _emit(run_id, "cache", "cache_hit", cost_usd=0.0,
                  detail=f"reused team from run {hit['run_id'][:8]} "
                         f"({hit['score'] * 100:.0f}% match) — skipped "
                         f"{len(roles)} bake-off(s)")
            _agent_runs[run_id] = cached
            return cached
        _emit(run_id, "cache", "cache_miss",
              detail="no prior team matched — running bake-off")

        for role in roles:
            candidates_models, reason, transcript = team.select_candidates(
                client, role["probe_description"], role["step_class"], run_id
            )
            # Surface the debate turns so the decision log shows the reasoning.
            for turn in transcript:
                verb = "accepts" if turn["accepted"] else "proposes"
                _emit(run_id, "router", "debate_turn", step_id=role["id"],
                      step_class=role["step_class"], model=turn["proposal"],
                      detail=f"[{role['name']}] {turn['speaker']} {verb} "
                             f"{turn['proposal']}: {turn['rationale']}")
            _emit(run_id, "router", "candidate_selected", step_id=role["id"],
                  step_class=role["step_class"], routing_reason=reason,
                  detail=f"[{role['name']}] bake off {candidates_models[0]} vs "
                         f"{candidates_models[1]} — {reason}")

            # Two candidates race in their own sandboxes ("two VMs spinning out").
            with ThreadPoolExecutor(max_workers=len(candidates_models)) as pool:
                candidates = list(pool.map(
                    lambda m: _bake_candidate(run_id, role, m), candidates_models
                ))

            recommended = _recommend(candidates)
            recommendations = _recommendations(candidates)
            _emit(run_id, "evaluator", "recommendation", step_id=role["id"],
                  step_class=role["step_class"], model=recommended,
                  detail=f"[{role['name']}] best — accuracy: {recommendations['accuracy']}, "
                         f"latency: {recommendations['latency']}, cost: {recommendations['cost']}"
                         + (f" (fits all: {recommendations['fits_all']})" if recommendations["fits_all"] else ""))
            result["roles"].append({
                "role": role, "candidates": candidates,
                "recommended_model": recommended,
                "recommendations": recommendations,
            })

        # Grand total: team-planning + debates (under run_id) + every candidate.
        total = client.cost_tracker.total_cost(run_id) + sum(
            c["cost_usd"] for r in result["roles"] for c in r["candidates"]
        )
        result["total_cost"] = total
        result["status"] = "done"
        result["detail"] = f"composed {len(result['roles'])} agent(s)"
        _emit(run_id, "evaluator", "team_complete", cost_usd=total,
              detail=f"team ready — {len(result['roles'])} agent(s), ${total:.4f} total")

        # Cache the finished bake-off so a future structurally-similar team plan
        # can skip it. Representative score = mean of each role's best candidate.
        role_bests = [
            max((c["critic_score"] for c in r["candidates"]), default=0.0)
            for r in result["roles"]
        ]
        avg_score = sum(role_bests) / len(role_bests) if role_bests else None
        plan_cache.store("team", run_id, spec, signature, result, avg_score)
    except Exception as e:
        result["status"] = "error"
        result["detail"] = str(e)
        _emit(run_id, "evaluator", "error", detail=f"agent mode failed: {e}")

    return result
