"""Node implementations for the support-copilot agent graph.

Each function takes the current AgentState and returns a dict of the fields
it updates — the standard LangGraph node contract.
"""

import os

import litellm
from slack_sdk import WebClient

from agent.state import AgentState
from knowledge_base.retriever import add_to_index, search as kb_search

LLM_MODEL = os.getenv("SUPPORT_COPILOT_LLM_MODEL", "mistral/mistral-small-latest")

DRAFT_SYSTEM_PROMPT = (
    "You are a support-answer assistant. You are given a customer question and a set "
    "of passages retrieved from the team's knowledge base. Answer using ONLY the "
    "information in those passages. If the passages don't cover the question, say so "
    "explicitly — reply with \"I don't have enough information in the knowledge base "
    "to answer this confidently\" rather than inventing an answer. Keep the answer "
    "concise and reply in the same language as the question."
)

I_DONT_KNOW_FALLBACK = (
    "I don't have enough information in the knowledge base to answer this "
    "confidently — could you check with the team?"
)


def retrieve(state: AgentState) -> dict:
    """Pull the top-k most relevant passages for state.question from the knowledge base."""
    passages = kb_search(state.question, top_k=5)
    return {"passages": passages}


def draft(state: AgentState) -> dict:
    """Ask the LLM (via LiteLLM) to draft an answer grounded only in state.passages.

    No retrieved passages means no grounding to answer from, so the fallback
    "I don't know" message is returned directly without calling the LLM —
    cheaper, and it removes any chance of the model inventing an answer from
    its own training data instead of the knowledge base.
    """
    if not state.passages:
        return {"draft_answer": I_DONT_KNOW_FALLBACK, "confidence": 0.0}

    context = "\n\n".join(f"[{p.source}] {p.text}" for p in state.passages)
    messages = [
        {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {state.question}\n\nKnowledge base passages:\n{context}"},
    ]
    response = litellm.completion(model=LLM_MODEL, messages=messages, temperature=0.2)
    answer = response["choices"][0]["message"]["content"].strip()

    said_dont_know = "don't have enough information" in answer.lower() or "i don't know" in answer.lower()
    if said_dont_know:
        confidence = 0.0
    else:
        avg_passage_score = sum(p.score for p in state.passages) / len(state.passages)
        confidence = round(max(0.0, min(avg_passage_score, 1.0)), 2)

    return {"draft_answer": answer, "confidence": confidence}


def human_gate(state: AgentState) -> dict:
    """The interrupt_before checkpoint: nothing downstream runs until a human
    clicks Approve / Edit / Reject on the Slack message posted to
    TEAM_REVIEW_CHANNEL_ID (see slack_app.py for the Block Kit payload).

    By the time this function body actually executes, a Slack action handler
    has already resumed the graph with review_status set via
    graph.update_state() — this just turns that decision into final_answer.
    """
    if state.review_status == "approved":
        return {"final_answer": state.draft_answer}
    if state.review_status == "edited":
        return {"final_answer": state.final_answer}
    return {}


def post(state: AgentState) -> dict:
    """Post state.final_answer to the original Slack thread, only if
    review_status is "approved" or "edited" — graph.py's route_after_review
    sends "rejected" straight to END, so this never runs on a rejection.
    """
    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    client.chat_postMessage(
        channel=state.slack_channel_id,
        thread_ts=state.slack_thread_ts,
        text=state.final_answer,
    )
    return {}


def log(state: AgentState) -> dict:
    """Append the question + final_answer to the knowledge base so future
    retrieve() calls can surface it for similar questions.
    """
    add_to_index(
        source=f"slack-thread:{state.slack_channel_id}:{state.slack_thread_ts}",
        text=f"Q: {state.question}\nA: {state.final_answer}",
    )
    return {"logged": True}
