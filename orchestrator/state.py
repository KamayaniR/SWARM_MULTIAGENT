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
    debate_mode: bool           # True: pick each step's model via the two-agent debate router; False: single-shot nano classifier
    pending_correction: Optional[str]   # human correction injected via /intervene, consumed by the Planner
    cache_enabled: bool         # True: consult the structural plan cache after planning; False (e.g. baseline) bypasses it
    cache_hit: Optional[dict]   # best matching cached run set by cache_gate: {run_id, score, spec, files, critic_score} — else None
    served_from_cache: bool     # True once a cache hit is verified and served, so the run isn't re-stored as a duplicate
