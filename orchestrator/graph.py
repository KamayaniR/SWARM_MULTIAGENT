import uuid

from langgraph.graph import END, StateGraph

from orchestrator.loop import (
    coder_node,
    critic_node,
    decide_next,
    planner_node,
    router_node,
    tester_node,
)
from orchestrator.state import SwarmState

graph_builder = StateGraph(SwarmState)
graph_builder.add_node("planner", planner_node)
graph_builder.add_node("router", router_node)
graph_builder.add_node("coder", coder_node)
graph_builder.add_node("tester", tester_node)
graph_builder.add_node("critic", critic_node)

graph_builder.set_entry_point("planner")
graph_builder.add_edge("planner", "router")
graph_builder.add_edge("router", "coder")
graph_builder.add_edge("coder", "tester")
graph_builder.add_edge("tester", "critic")

graph_builder.add_conditional_edges(
    "critic",
    decide_next,
    {
        "next_step": "router",
        "retry": "router",
        "replan": "planner",
        "done": END,
        "escalate": END,
    },
)

graph = graph_builder.compile()


def _initial_state(spec: str) -> SwarmState:
    return SwarmState(
        spec=spec,
        plan=[],
        current_step_index=0,
        workspace_files={},
        test_results=None,
        critique_history=[],
        iteration=0,
        max_iterations=8,
        events=[],
        status="planning",
        current_model=None,
        routing_reason=None,
        run_id=str(uuid.uuid4()),
    )


if __name__ == "__main__":
    import os
    import sys

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY before running the loop.")

    demo_spec = """Build a CSV deduplication CLI that:
- Takes --input, --output, and --key flags
- Reads CSV handling quoted fields and mixed encodings
- Deduplicates rows by configurable key columns
- Writes deduplicated output"""

    final_state = graph.invoke(_initial_state(demo_spec), config={"recursion_limit": 100})

    for event in final_state["events"]:
        print(
            f"{event['timestamp']} {event['agent']:<8} {event['step_id']:<4} "
            f"{event['action']:<14} {event['detail']}"
        )

    print(f"\nfinal status: {final_state['status']}")
