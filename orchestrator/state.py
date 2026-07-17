from typing import Optional, TypedDict


class PlanStep(TypedDict):
    id: str                    # "s1", "s2"
    description: str           # "set up argparse with input/output flags"
    step_class: str            # "cli_wiring", "algorithm", etc
    est_loc: int                # rough lines estimate
    deps: list[str]             # ["s1"] — which steps must finish first
    acceptance: list[str]       # ["--input flag reads CSV path"]
    status: str                 # pending | active | passed | failed


class CriticVerdict(TypedDict):
    correctness: float
    spec_fidelity: float
    code_quality: float
    coverage: float
    overall: float
    feedback: list[str]
    failure_type: str          # step_level | plan_level | none


class SwarmState(TypedDict):
    spec: str
    plan: list[PlanStep]
    current_step_index: int
    workspace_files: dict[str, str]   # filename → content
    test_results: Optional[dict]
    critique_history: list[CriticVerdict]
    iteration: int
    max_iterations: int
    events: list[dict]
    status: str                # planning | routing | coding | testing | judging | done | escalated
    current_model: Optional[str]
    routing_reason: Optional[str]
    run_id: str
    baseline_mode: bool         # True: bypass the router, always use gpt-5.5
    debate_mode: bool           # (Task mode) True: pick each step's model via the two-agent debate router; False: single-shot nano classifier
    pending_correction: Optional[str]   # human correction injected via /intervene, consumed by the Planner

    # --- Agent mode (per-run deliberation flow) ---
    mode: str                           # "task" (existing flow, unchanged) | "agent" (deliberation flow)
    model_preference: Optional[str]     # "cost" | "latency" | "accuracy" | None (None -> default rule: highest accuracy, tie -> lowest cost)
    debate_transcript: list[dict]       # every deliberation turn across the run, for the dashboard's transcript panel
    candidate_models: list[str]         # the 2 candidates the deliberation picked for the current step ([] once consumed)
    candidate_results: list[dict]       # per-candidate cost/latency/critic-score from the last dual-sandbox comparison
    similarity_match: Optional[dict]    # {"id", "step_description", "step_class", "winning_model", "score"} when the current step skipped deliberation
    pending_verdict: Optional[dict]     # winner's CriticVerdict from the comparison — consumed by critic_node instead of re-judging
