"""Manual smoke test for Agent mode: runs the full team-composition + per-role
model bake-off and prints the comparison so you can eyeball the results without
the dashboard.

Requires:
  - ANTHROPIC_API_KEY and OPENAI_API_KEY in .env (real LLM calls, real spend)
  - Docker running with the `swarm-sandbox` image built:
        docker build -t swarm-sandbox sandbox/

Usage:
  python test_agent_mode.py                 # runs the default demo task
  python test_agent_mode.py "your task…"    # runs your own task
  SHOW_CODE=1 python test_agent_mode.py     # also dump each candidate's code

Heads-up on cost: up to 3 roles x 2 candidates, each a real coder+tests+critic
cycle. That can exceed BUDGET_PER_RUN (default 0.50) — bump it in .env if a
candidate trips the budget guard (it fails just that candidate, not the run).
"""

import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("OPENAI_API_KEY"):
    sys.exit("Set ANTHROPIC_API_KEY and OPENAI_API_KEY in .env before running this.")

from orchestrator.agent_mode import run_agent_mode

DEFAULT_SPEC = """Build a small string-utils Python library with:
- slugify(text): lowercased, spaces and punctuation collapsed to single hyphens
- titlecase(text): capitalizes each word, leaving small words (a, an, the, of...) lowercase unless first
Include pytest tests covering the edge cases."""

BAR = "=" * 68
SHOW_CODE = os.environ.get("SHOW_CODE") == "1"


def _fmt_candidate(c: dict, recommended: bool) -> str:
    tag = "  <-- RECOMMENDED" if recommended else ""
    if c["error"]:
        return f"    {c['model']:<20} ERROR: {c['error'][:60]}{tag}"
    verdict = "PASS" if c["passed"] else "FAIL"
    return (
        f"    {c['model']:<20} "
        f"${c['cost_usd']:.4f}  "
        f"quality {c['critic_score']:>4.1f}  "
        f"tests {c['tests_passed']}/{c['tests_total']}  "
        f"{c['latency_ms'] / 1000:>5.1f}s  "
        f"{verdict}{tag}"
    )


def main() -> None:
    spec = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SPEC
    run_id = str(uuid.uuid4())

    print(BAR)
    print("AGENT MODE — team composition + per-role model bake-off")
    print(BAR)
    print(f"run_id: {run_id}")
    print(f"\nTask:\n{spec}\n")
    print("Running… (this makes real LLM calls and spins real sandboxes)\n")

    result = run_agent_mode(spec, run_id)

    print(BAR)
    print(f"RESULT: {result['status'].upper()}  ({result['detail']})")
    print(f"Team size: {len(result['roles'])} agent(s)")
    print(f"Total bake-off cost: ${result['total_cost']:.4f}")
    print(BAR)

    if result["status"] == "error" and not result["roles"]:
        print(f"\nFailed before any role completed: {result['detail']}")
        return

    for i, role_result in enumerate(result["roles"]):
        role = role_result["role"]
        rec = role_result["recommended_model"]
        print(f"\nAgent {i + 1}: {role['name']}  [{role['step_class']}]")
        print(f"  {role['responsibility']}")
        print("  Candidates:")
        for c in role_result["candidates"]:
            print(_fmt_candidate(c, recommended=c["model"] == rec))

        if SHOW_CODE:
            chosen = next((c for c in role_result["candidates"] if c["model"] == rec), None)
            if chosen and chosen["files"]:
                print(f"\n  --- code from {rec} ---")
                for path, content in chosen["files"].items():
                    print(f"  ### {path}")
                    for line in content.splitlines():
                        print(f"      {line}")
                print()

    print(f"\n{BAR}")
    print("Recommendations:")
    for i, role_result in enumerate(result["roles"]):
        print(f"  Agent {i + 1} ({role_result['role']['name']}): "
              f"{role_result['recommended_model']}")
    print(BAR)


if __name__ == "__main__":
    main()
