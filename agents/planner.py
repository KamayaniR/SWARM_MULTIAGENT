import json
from pathlib import Path

from orchestrator.state import PlanStep

_PROMPT_PATH = Path(__file__).parent / "prompts" / "planner_system.md"
SYSTEM_PROMPT = _PROMPT_PATH.read_text()

PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the ordered list of implementation steps for the spec.",
    "input_schema": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                        "step_class": {"type": "string"},
                        "est_loc": {"type": "integer"},
                        "deps": {"type": "array", "items": {"type": "string"}},
                        "acceptance": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "description", "step_class", "est_loc", "deps", "acceptance"],
                },
            }
        },
        "required": ["steps"],
    },
}


def run_planner(client, spec: str, run_id: str) -> list[PlanStep]:
    """Call the Planner LLM and return a validated list of PlanSteps."""
    result, _metrics = client.call(
        model="claude-sonnet-4-6",
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Spec:\n\n{spec}"}],
        tool=PLAN_TOOL,
        run_id=run_id,
        agent="planner",
        max_tokens=4096,
    )
    raw_steps = result["steps"]

    steps: list[PlanStep] = []
    for raw in raw_steps:
        steps.append(
            PlanStep(
                id=raw["id"],
                description=raw["description"],
                step_class=raw["step_class"],
                est_loc=raw["est_loc"],
                deps=raw["deps"],
                acceptance=raw["acceptance"],
                status="pending",
            )
        )
    return steps


if __name__ == "__main__":
    import os
    import sys

    from scheduler.tracked_client import TrackedLLMClient

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY before running this test.")

    demo_spec = """Build a CSV deduplication CLI that:
- Takes --input, --output, and --key flags
- Reads CSV handling quoted fields and mixed encodings
- Deduplicates rows by configurable key columns
- Writes deduplicated output"""

    client = TrackedLLMClient()
    plan = run_planner(client, demo_spec, run_id="test-run")
    print(json.dumps(plan, indent=2))
