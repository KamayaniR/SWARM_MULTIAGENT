import json
from pathlib import Path
from typing import TypedDict

_PROMPT_PATH = Path(__file__).parent / "prompts" / "team_planner_system.md"
SYSTEM_PROMPT = _PROMPT_PATH.read_text()

MAX_ROLES = 3


class AgentRole(TypedDict):
    id: str                    # "r1", "r2"
    name: str                  # "CSV Parser Agent"
    responsibility: str        # one-sentence description
    step_class: str            # "io_parsing", "algorithm", etc — same vocabulary as PlanStep
    probe_description: str      # self-contained coding instruction the bake-off runs
    acceptance: list[str]       # checkable criteria for the Critic


TEAM_TOOL = {
    "name": "submit_team",
    "description": "Submit the team of agent roles needed to accomplish the task.",
    "input_schema": {
        "type": "object",
        "properties": {
            "roles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "responsibility": {"type": "string"},
                        "step_class": {"type": "string"},
                        "probe_description": {"type": "string"},
                        "acceptance": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "id", "name", "responsibility", "step_class",
                        "probe_description", "acceptance",
                    ],
                },
            }
        },
        "required": ["roles"],
    },
}


def run_team_planner(client, spec: str, run_id: str) -> list[AgentRole]:
    """Call the Team Planner LLM and return a validated list of AgentRoles.

    Capped at MAX_ROLES to bound bake-off spend and time — each role is baked
    off across two candidate models in isolated sandboxes downstream.
    """
    result, _metrics = client.call(
        model="claude-sonnet-4-6",
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Task:\n\n{spec}"}],
        tool=TEAM_TOOL,
        run_id=run_id,
        agent="team_planner",
        max_tokens=4096,
    )

    roles: list[AgentRole] = []
    for raw in result["roles"][:MAX_ROLES]:
        roles.append(
            AgentRole(
                id=raw["id"],
                name=raw["name"],
                responsibility=raw["responsibility"],
                step_class=raw["step_class"],
                probe_description=raw["probe_description"],
                acceptance=raw["acceptance"],
            )
        )
    return roles


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
    roles = run_team_planner(client, demo_spec, run_id="test-run")
    print(json.dumps(roles, indent=2))
