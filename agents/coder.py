import json
from pathlib import Path

from orchestrator.state import PlanStep

_PROMPT_PATH = Path(__file__).parent / "prompts" / "coder_system.md"
SYSTEM_PROMPT = _PROMPT_PATH.read_text()

FILES_TOOL = {
    "name": "submit_files",
    "description": "Submit the full contents of every file created or modified for this step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            }
        },
        "required": ["files"],
    },
}


def _build_user_message(step: PlanStep, workspace_files: dict, feedback: str | None) -> str:
    parts = [
        f"Step {step['id']}: {step['description']}",
        f"step_class: {step['step_class']}",
        "Acceptance criteria:\n" + "\n".join(f"- {a}" for a in step["acceptance"]),
    ]

    if workspace_files:
        files_block = "\n\n".join(
            f"### {path}\n```\n{content}\n```" for path, content in workspace_files.items()
        )
        parts.append(f"Current workspace files:\n\n{files_block}")
    else:
        parts.append("Current workspace files: (empty)")

    if feedback:
        parts.append(f"Critic feedback from the previous attempt (address all of it):\n{feedback}")

    return "\n\n".join(parts)


def run_coder(
    client,
    step: PlanStep,
    workspace_files: dict,
    feedback: str | None,
    model: str,
    run_id: str,
    iteration: int,
) -> dict[str, str]:
    """Call the Coder LLM and return {filepath: content} for this step."""
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        tools=[FILES_TOOL],
        tool_choice={"type": "tool", "name": "submit_files"},
        messages=[{"role": "user", "content": _build_user_message(step, workspace_files, feedback)}],
    )

    tool_call = next(b for b in response.content if b.type == "tool_use")
    return {f["path"]: f["content"] for f in tool_call.input["files"]}


if __name__ == "__main__":
    import os
    import sys

    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY before running this test.")

    demo_step = PlanStep(
        id="s1",
        description="set up argparse with --input, --output, and --key flags",
        step_class="cli_wiring",
        est_loc=25,
        deps=[],
        acceptance=["--input flag reads CSV path", "--key flag accepts column names"],
        status="pending",
    )

    client = anthropic.Anthropic()
    files = run_coder(client, demo_step, {}, None, "claude-sonnet-5", run_id="test-run", iteration=0)
    print(json.dumps(files, indent=2))
