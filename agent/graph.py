"""Wires the support-copilot agent nodes into a LangGraph state machine.

retrieve -> draft -> human_gate -> post -> log

human_gate is a real interrupt (interrupt_before), the same pattern used in
ai-data-agent: execution pauses and persists to a SQLite checkpoint until an
external event (a Slack button click, handled in slack_app.py) resumes it
with review_status set. This is what makes the human approval a genuine
checkpoint rather than a confirmation dialog the agent could route around.
"""

import sqlite3

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

from agent.state import AgentState
from agent.nodes import retrieve, draft, human_gate, post, log


def route_after_review(state: AgentState) -> str:
    """A rejection skips post/log entirely and ends the run — nothing about a
    rejected draft is ever sent to the customer or written to the knowledge
    base. Module-level (not a closure) so it has a direct unit test.
    """
    return END if state.review_status == "rejected" else "post"


def build_graph(checkpoint_path: str = "agent_checkpoints.sqlite"):
    graph = StateGraph(AgentState)

    graph.add_node("retrieve", retrieve)
    graph.add_node("draft", draft)
    graph.add_node("human_gate", human_gate)
    graph.add_node("post", post)
    graph.add_node("log", log)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", "human_gate")
    graph.add_conditional_edges("human_gate", route_after_review, {"post": "post", END: END})
    graph.add_edge("post", "log")
    graph.add_edge("log", END)

    # SqliteSaver.from_conn_string() is a context manager meant for a `with`
    # block that closes on exit — wrong shape for a long-lived Slack app
    # (the connection needs to outlive this function). Building the
    # sqlite3.Connection directly and handing it to the plain constructor
    # avoids that mismatch; check_same_thread=False is safe here because
    # SqliteSaver guards access with its own internal lock (see its docstring).
    conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return graph.compile(checkpointer=checkpointer, interrupt_before=["human_gate"])
