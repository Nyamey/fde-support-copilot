"""Node implementations for the support-copilot agent graph.

Each function takes the current AgentState and returns a dict of the fields
it updates, the standard LangGraph node contract.
"""

import os

import litellm
from slack_sdk import WebClient

from agent.state import AgentState
from knowledge_base.retriever import add_to_index, search as kb_search

# Model names change (Groq no longer offers llama-3.3-70b-versatile), which is
# one reason for the backup list below.
LLM_MODEL = os.getenv("SUPPORT_COPILOT_LLM_MODEL", "groq/openai/gpt-oss-120b")

# Backup models, tried in order when the main model fails: provider down,
# quota reached, timeout. Comma-separated LiteLLM model names, none by default.
LLM_FALLBACK_MODELS = [
    model.strip() for model in os.getenv("SUPPORT_COPILOT_LLM_FALLBACKS", "").split(",") if model.strip()
]
LLM_TIMEOUT_SECONDS = float(os.getenv("SUPPORT_COPILOT_LLM_TIMEOUT", "30"))

# Passages whose cosine similarity with the question is below this score are
# dropped before drafting. If none is left, draft() returns the fixed refusal
# without calling the model. Chosen with the evaluation set in evaluation/
# for the default EMBEDDING_MODEL: the off-topic questions scored at most
# 0.28 and the answerable ones at least 0.39, and 0.33 sits in the middle of
# that gap. Similarity scales differ between embedding models, so re-run the
# evaluation after changing EMBEDDING_MODEL.
MIN_RELEVANCE = float(os.getenv("SUPPORT_COPILOT_MIN_RELEVANCE", "0.33"))

# The model replies with this marker when the passages don't cover the
# question. A fixed marker is easier to detect than a sentence the model may
# rephrase, translate or write with a curly apostrophe.
NO_ANSWER_MARKER = "NO_ANSWER"

DRAFT_SYSTEM_PROMPT = (
    "You are a support-answer assistant. You are given a customer question and a set "
    "of passages retrieved from the team's knowledge base. Answer using ONLY the "
    "information in those passages. If the passages don't cover the question, reply "
    f"with exactly {NO_ANSWER_MARKER} and nothing else, rather than inventing an answer. "
    "Keep the answer concise, write plain sentences without Markdown formatting, and "
    "reply in the same language as the question."
)

I_DONT_KNOW_FALLBACK = (
    "I don't have enough information in the knowledge base to answer this "
    "confidently. Could you check with the team?"
)

# Characters some models write that look like a space or a hyphen but are
# not one. Found in the evaluation drafts: they break a command or a model
# name that a reviewer or a user copies from the answer.
_LOOKALIKE_CHARACTERS = str.maketrans(
    {"\u00a0": " ", "\u2007": " ", "\u202f": " ", "\u2010": "-", "\u2011": "-"}
)


def retrieve(state: AgentState) -> dict:
    """Pull the top-k passages for state.question and keep only those at or
    above MIN_RELEVANCE. An empty result makes draft() return the fixed
    refusal without calling the model.
    """
    passages = [p for p in kb_search(state.question, top_k=5) if p.score >= MIN_RELEVANCE]
    return {"passages": passages}


def _complete(messages: list[dict]) -> dict:
    """Call the main drafting model, then each backup model in order if a call
    fails. Raises the last error when every model fails, so a failure stays
    visible instead of producing an empty draft.
    """
    last_error: Exception | None = None
    for model in [LLM_MODEL, *LLM_FALLBACK_MODELS]:
        try:
            return litellm.completion(
                model=model, messages=messages, temperature=0.2, timeout=LLM_TIMEOUT_SECONDS
            )
        except Exception as error:  # provider down, quota reached, timeout
            last_error = error
    raise last_error


def draft(state: AgentState) -> dict:
    """Ask the LLM (via LiteLLM) to draft an answer grounded only in state.passages.

    No passage above the relevance threshold means no grounding to answer
    from, so the fixed "I don't know" message is returned without calling
    the LLM. It is cheaper, and the model cannot invent an answer from its
    own training data instead of the knowledge base.
    """
    if not state.passages:
        return {"draft_answer": I_DONT_KNOW_FALLBACK, "confidence": 0.0}

    context = "\n\n".join(f"[{p.source}] {p.text}" for p in state.passages)
    messages = [
        {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {state.question}\n\nKnowledge base passages:\n{context}"},
    ]
    response = _complete(messages)
    answer = response["choices"][0]["message"]["content"].strip().translate(_LOOKALIKE_CHARACTERS)

    if _is_refusal(answer):
        return {"draft_answer": I_DONT_KNOW_FALLBACK, "confidence": 0.0}

    # The best similarity score among the passages used: how close the
    # closest passage is to the question, not the probability that the
    # answer is right. An average would be pulled down by the weaker
    # passages that only just pass the threshold.
    best_score = max(p.score for p in state.passages)
    confidence = round(max(0.0, min(best_score, 1.0)), 2)
    return {"draft_answer": answer, "confidence": confidence}


def _is_refusal(answer: str) -> bool:
    """The marker anywhere, or an answer that opens with a refusal. Only the
    opening counts for the sentences, so an answer that explains the refusal
    rule ("...it replies that it doesn't have enough information") is kept.
    """
    normalized = answer.lower().replace("\u2019", "'")  # curly apostrophe
    return (
        NO_ANSWER_MARKER.lower() in normalized
        or normalized.startswith("i don't have enough information")
        or normalized.startswith("i don't know")
    )


def human_gate(state: AgentState) -> dict:
    """The interrupt_before checkpoint: nothing downstream runs until a human
    clicks Approve / Edit / Reject on the Slack message posted to
    TEAM_REVIEW_CHANNEL_ID (see slack_app.py for the Block Kit payload).

    By the time this function body actually executes, a Slack action handler
    has already resumed the graph with review_status set via
    graph.update_state(); this just turns that decision into final_answer.
    """
    if state.review_status == "approved":
        return {"final_answer": state.draft_answer}
    if state.review_status == "edited":
        return {"final_answer": state.final_answer}
    return {}


def post(state: AgentState) -> dict:
    """Post state.final_answer to the original Slack thread, only if
    review_status is "approved" or "edited": graph.py's route_after_review
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
