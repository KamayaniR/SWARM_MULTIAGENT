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
