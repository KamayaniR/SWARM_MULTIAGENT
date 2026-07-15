from pathlib import Path

from orchestrator.state import CriticVerdict

_PROMPT_PATH = Path(__file__).parent / "prompts" / "critic_system.md"
SYSTEM_PROMPT = _PROMPT_PATH.read_text()

VERDICT_TOOL = {
    "name": "submit_verdict",
    "description": "Submit the scored verdict for this step's implementation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "correctness": {"type": "number"},
            "spec_fidelity": {"type": "number"},
            "code_quality": {"type": "number"},
            "coverage": {"type": "number"},
            "overall": {"type": "number"},
            "feedback": {"type": "array", "items": {"type": "string"}},
            "failure_type": {"type": "string", "enum": ["step_level", "plan_level", "none"]},
        },
        "required": [
            "correctness",
            "spec_fidelity",
            "code_quality",
            "coverage",
            "overall",
            "feedback",
            "failure_type",
        ],
    },
}

PASS_THRESHOLD = 8.5


def _build_user_message(spec: str, code: dict[str, str], test_results: dict) -> str:
    files_block = "\n\n".join(
        f"### {path}\n```\n{content}\n```" for path, content in code.items()
    )
    return (
        f"Spec:\n{spec}\n\n"
        f"Code:\n\n{files_block}\n\n"
        f"Test results:\n"
        f"exit_code={test_results.get('exit_code')} "
        f"tests_passed={test_results.get('tests_passed')} "
        f"tests_total={test_results.get('tests_total')}\n\n"
        f"stdout:\n{test_results.get('stdout', '')}"
    )


def run_critic(
    client,
    spec: str,
    code: dict[str, str],
    test_results: dict,
    run_id: str,
    step_id: str,
    iteration: int,
) -> CriticVerdict:
    """Call the Critic LLM and return a structured verdict."""
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        tools=[VERDICT_TOOL],
        tool_choice={"type": "tool", "name": "submit_verdict"},
        messages=[{"role": "user", "content": _build_user_message(spec, code, test_results)}],
    )

    tool_call = next(b for b in response.content if b.type == "tool_use")
    v = tool_call.input

    return CriticVerdict(
        correctness=v["correctness"],
        spec_fidelity=v["spec_fidelity"],
        code_quality=v["code_quality"],
        coverage=v["coverage"],
        overall=v["overall"],
        feedback=v["feedback"],
        failure_type=v["failure_type"],
    )


def passed(verdict: CriticVerdict, test_results: dict) -> bool:
    tests_green = (
        test_results.get("exit_code") == 0
        and test_results.get("tests_passed") == test_results.get("tests_total")
        and test_results.get("tests_total", 0) > 0
    )
    return verdict["overall"] >= PASS_THRESHOLD and tests_green


if __name__ == "__main__":
    import os
    import sys

    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY before running this test.")

    client = anthropic.Anthropic()
    spec = "Build a CSV deduplication CLI with --input, --output, --key flags."

    print("--- Bad code (should reject, score < 8.5) ---")
    bad_code = {"cli.py": "import sys\nprint('todo')\n"}
    bad_results = {"exit_code": 1, "tests_passed": 0, "tests_total": 3, "stdout": "3 failed"}
    bad_verdict = run_critic(client, spec, bad_code, bad_results, "test-run", "s1", 0)
    print(bad_verdict)
    print("passed:", passed(bad_verdict, bad_results))

    print("\n--- Good code (should approve, score >= 8.5) ---")
    good_code = {
        "cli.py": (
            "import argparse\n\n"
            "def main():\n"
            "    parser = argparse.ArgumentParser()\n"
            "    parser.add_argument('--input', required=True)\n"
            "    parser.add_argument('--output', required=True)\n"
            "    parser.add_argument('--key', required=True)\n"
            "    args = parser.parse_args()\n"
            "    print(args.input, args.output, args.key)\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        "test_cli.py": (
            "import subprocess\n\n"
            "def test_cli_accepts_flags():\n"
            "    result = subprocess.run(\n"
            "        ['python', 'cli.py', '--input', 'a.csv', '--output', 'b.csv', '--key', 'id'],\n"
            "        capture_output=True, text=True,\n"
            "    )\n"
            "    assert result.returncode == 0\n"
        ),
    }
    good_results = {"exit_code": 0, "tests_passed": 1, "tests_total": 1, "stdout": "1 passed"}
    good_verdict = run_critic(client, spec, good_code, good_results, "test-run", "s1", 0)
    print(good_verdict)
    print("passed:", passed(good_verdict, good_results))
