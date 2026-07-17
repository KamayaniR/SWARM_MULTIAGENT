import sqlite3
import uuid
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from orchestrator.loop import (
    cleanup_run,
    coder_node,
    comparison_gate_node,
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
graph_builder.add_node("comparison_gate", comparison_gate_node)
graph_builder.add_node("tester", tester_node)
graph_builder.add_node("critic", critic_node)

graph_builder.set_entry_point("planner")
graph_builder.add_edge("planner", "router")
graph_builder.add_edge("router", "coder")


def _decide_after_coder(state: SwarmState) -> str:
    # Task mode's coder_node never sets this status, so it never routes
    # through comparison_gate — only an agent-mode dual-candidate comparison
    # (which just finished building both candidates and needs a preference
    # before picking a winner) does.
    return "await" if state["status"] == "awaiting_preference" else "continue"


graph_builder.add_conditional_edges(
    "coder", _decide_after_coder, {"await": "comparison_gate", "continue": "tester"},
)
graph_builder.add_edge("comparison_gate", "tester")
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

CHECKPOINT_DB = Path(__file__).parent.parent / "data" / "checkpoints.db"
CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
_checkpoint_conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
checkpointer = SqliteSaver(_checkpoint_conn)

# Pausing after every critic verdict gives /intervene a real point to inject
# a correction via update_state() before the loop resumes to the next step.
# Pausing after comparison_gate is the awaiting_preference pause — Agent
# mode's dual-candidate comparison stops there until POST
# /run/{run_id}/commit-preference answers, or the server's timeout watchdog
# auto-applies the default rule.
graph = graph_builder.compile(checkpointer=checkpointer, interrupt_after=["critic", "comparison_gate"])


def _initial_state(
    spec: str,
    run_id: str | None = None,
    baseline_mode: bool = False,
    debate_mode: bool = False,
    mode: str = "task",
    model_preference: str | None = None,
) -> SwarmState:
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
        run_id=run_id or str(uuid.uuid4()),
        baseline_mode=baseline_mode,
        debate_mode=debate_mode,
        pending_correction=None,
        mode=mode,
        model_preference=model_preference,
        debate_transcript=[],
        candidate_models=[],
        candidate_results=[],
        similarity_match=None,
        pending_verdict=None,
    )


def run_to_completion(state: SwarmState | None, config: dict) -> SwarmState:
    """Drive the graph through its interrupt_after=["critic"] pause points
    until it actually finishes (done/escalated), not just the next pause.
    Pass state=None to resume an already-started thread from its checkpoint
    (e.g. after /intervene) instead of starting a fresh run.

    Always cleans up the run's sandbox container on the way out, whether
    the run finishes normally or raises (e.g. BudgetExceeded) — this is the
    only exit path from a run, so it's the right place for that cleanup.
    """
    run_id = config["configurable"]["thread_id"]
    try:
        result = graph.invoke(state, config=config)
        while graph.get_state(config).next:
            result = graph.invoke(None, config=config)
        return result
    finally:
        cleanup_run(run_id)


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

    run_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 100}
    final_state = run_to_completion(_initial_state(demo_spec, run_id=run_id), config)

    for event in final_state["events"]:
        print(
            f"{event['timestamp']} {event['agent']:<8} {event['step_id']:<4} "
            f"{event['action']:<14} {event['detail']}"
        )

    print(f"\nfinal status: {final_state['status']}")
