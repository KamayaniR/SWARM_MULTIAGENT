"""Manual smoke test: streams every node's output as the loop runs.

Adapted to match this repo's actual graph.py API (graph.stream(), not
build_graph()/astream() — those don't exist here), and to handle the
interrupt_after=["critic"] checkpoint pauses: the graph yields control
after every critic verdict, so we resume with stream(None, config) until
graph.get_state(config).next is empty.
"""

import os
import sys
import uuid

from orchestrator.graph import _initial_state, graph

if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("OPENAI_API_KEY"):
    sys.exit("Set ANTHROPIC_API_KEY and OPENAI_API_KEY in .env before running this.")

DEMO_SPEC = """Build a CSV deduplication CLI that:
- Takes --input, --output, and --key flags
- Reads CSV handling quoted fields
- Deduplicates rows by configurable key columns
- Writes deduplicated output"""


def print_update(node_name: str, state_update: dict) -> None:
    status = state_update.get("status", "")
    print(f"\n{'=' * 60}")
    print(f"NODE: {node_name} | STATUS: {status}")

    if node_name == "planner":
        for s in state_update.get("plan", []):
            print(f"  Step {s['id']}: {s['step_class']} — {s['description'][:60]}")

    if node_name == "router":
        print(f"  Model: {state_update.get('current_model')}")
        print(f"  Reason: {state_update.get('routing_reason')}")

    if node_name == "coder":
        for f, content in state_update.get("workspace_files", {}).items():
            print(f"  Wrote: {f} ({len(content)} chars)")

    if node_name == "tester":
        results = state_update.get("test_results") or {}
        print(f"  Tests: {results.get('tests_passed', 0)}/{results.get('tests_total', 0)}")

    if node_name == "critic":
        history = state_update.get("critique_history", [])
        if history:
            v = history[-1]
            print(f"  Score: {v['overall']}/10")
            print(f"  Verdict: {'PASS' if v['overall'] >= 8.5 else 'FAIL'}")
            if v["feedback"]:
                print(f"  Feedback: {v['feedback'][0][:80]}")


def main() -> None:
    run_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 100}
    state = _initial_state(DEMO_SPEC, run_id=run_id)

    resume_input = state
    while True:
        for update in graph.stream(resume_input, config=config):
            for node_name, state_update in update.items():
                if node_name == "__interrupt__" or not isinstance(state_update, dict):
                    continue  # LangGraph's pause marker from interrupt_after=["critic"], not a node update
                print_update(node_name, state_update)

        if not graph.get_state(config).next:
            break
        resume_input = None  # resume from checkpoint past the interrupt

    final_state = graph.get_state(config).values
    print(f"\n{'=' * 60}")
    print("LOOP COMPLETE")
    print(f"final status: {final_state['status']}")
    print(f"run_id: {run_id}")


if __name__ == "__main__":
    main()
