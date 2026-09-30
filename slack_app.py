"""Slack entry point: listens for questions in SUPPORT_INBOX_CHANNEL_ID,
runs them through the agent graph, and posts the human-approval message
(with Approve / Edit / Reject buttons) to TEAM_REVIEW_CHANNEL_ID.

Supports two transports, chosen by SLACK_MODE:

- "socket" (default): Socket Mode, an outbound WebSocket connection, so no
  public URL or signing secret is needed. The simplest path for local dev.
- "http": Flask + slack_bolt's request handler, for platforms whose free
  tier is a Web Service rather than a background worker (e.g. Render).
  Needs SLACK_SIGNING_SECRET, Socket Mode turned off in the Slack app, and
  a public Request URL for Event Subscriptions and Interactivity, both
  pointed at POST /slack/events (slack-app-manifest.http.yml sets all
  three). Served by gunicorn in the Dockerfile
  (`gunicorn slack_app:flask_app`), which imports flask_app directly and
  never runs the __main__ block below.
"""

import json
import logging
import os
import threading

from dotenv import load_dotenv
from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_bolt.adapter.socket_mode import SocketModeHandler

from agent.graph import build_graph
from agent.state import AgentState, RetrievedPassage

load_dotenv()

logger = logging.getLogger(__name__)

app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
    # Skips Slack's auth.test call at startup when unset/false, so importing
    # this module in tests (a fake token) doesn't hit the network.
    # Real deployments should leave SLACK_TOKEN_VERIFICATION unset (defaults on).
    token_verification_enabled=os.getenv("SLACK_TOKEN_VERIFICATION", "true").lower() == "true",
)
agent_graph = build_graph(checkpoint_path=os.getenv("AGENT_CHECKPOINT_PATH", "agent_checkpoints.sqlite"))

SUPPORT_INBOX_CHANNEL_ID = os.environ.get("SUPPORT_INBOX_CHANNEL_ID")
TEAM_REVIEW_CHANNEL_ID = os.environ.get("TEAM_REVIEW_CHANNEL_ID")

# Slack delivers an event again when the first delivery got no 2xx within
# 3 seconds, which happens while a sleeping free-tier instance boots. A
# redelivered event carries the same channel + ts, so it maps to the same
# graph thread: handle_support_question skips it when that run is still in
# progress or already produced a draft. The same lock makes a review
# decision count once, even if two reviewers click at the same time.
_runs_in_progress: set[str] = set()
_runs_lock = threading.Lock()

# Best passage score from which the review message says "high". Chosen with
# the evaluation set (evaluation/results/summary.md) for the default
# embedding model: it measures how close the closest passage is to the
# question, not whether the draft is right.
HIGH_CONFIDENCE = 0.5

NOT_WAITING_NOTE = (
    "This question is no longer waiting for review: it was already decided, or the service "
    "restarted and lost the paused run. If nothing was posted in the support thread, please "
    "answer there by hand."
)


def _thread_key(channel: str, ts: str) -> str:
    """LangGraph checkpoint thread_id: the original Slack channel+ts, so an
    action handler can find the right paused graph to resume.
    """
    return f"{channel}:{ts}"


def _already_drafted(config: dict) -> bool:
    return agent_graph.get_state(config).values.get("draft_answer") is not None


def _sources_text(passages: list) -> str:
    """One line naming each knowledge-base file behind the draft, with its
    best similarity score, so the reviewer knows what to check before
    approving.
    """
    best_scores: dict[str, float] = {}
    for passage in map(RetrievedPassage.model_validate, passages):
        best_scores[passage.source] = max(passage.score, best_scores.get(passage.source, passage.score))
    if not best_scores:
        return "*Sources:* none above the relevance threshold, so the draft is the standard refusal."
    ranked = sorted(best_scores.items(), key=lambda item: item[1], reverse=True)
    return "*Sources:* " + ", ".join(f"{source} ({score:.2f})" for source, score in ranked)


def _review_blocks(
    question: str, draft_answer: str, confidence: float, thread_key: str, passages: list | None = None
) -> list[dict]:
    confidence_label = "high" if confidence >= HIGH_CONFIDENCE else "low" if confidence > 0 else "none"
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*New question:*\n>{question}"}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Draft answer* (confidence: {confidence_label}):\n{draft_answer}"},
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": _sources_text(passages or [])}]},
        {
            "type": "actions",
            "block_id": "review_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "action_id": "approve_answer",
                    "value": thread_key,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Edit"},
                    "action_id": "edit_answer",
                    "value": thread_key,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "action_id": "reject_answer",
                    "value": thread_key,
                },
            ],
        },
    ]


def _waiting_for_review(config: dict) -> bool:
    snapshot = agent_graph.get_state(config)
    return snapshot.next == ("human_gate",) and snapshot.values.get("review_status") == "pending"


def _resume_after_review(config: dict, decision: dict) -> bool:
    """Record the reviewer's decision and resume the paused run. Returns
    False without changing anything when the run is no longer waiting for
    review: a second click on the same message, or another reviewer who
    clicked first.
    """
    with _runs_lock:
        if not _waiting_for_review(config):
            return False
        agent_graph.update_state(config, decision)
    agent_graph.invoke(None, config)
    return True


def _tell_reviewer_not_waiting(client, channel_id: str, user_id: str) -> None:
    """Private note to the reviewer who clicked, instead of a silent no-op."""
    client.chat_postEphemeral(channel=channel_id, user=user_id, text=NOT_WAITING_NOTE)


@app.event("message")
def handle_support_question(event, client):
    """Fires on every message in SUPPORT_INBOX_CHANNEL_ID. Kicks off the
    agent graph up to the human_gate interrupt, then posts the review
    message to TEAM_REVIEW_CHANNEL_ID with the Approve/Edit/Reject buttons.

    Only new top-level messages count as questions: edits and deletions
    (which arrive with a subtype) and replies inside a thread are ignored.
    """
    if event.get("channel") != SUPPORT_INBOX_CHANNEL_ID or event.get("subtype") is not None:
        return
    if event.get("thread_ts") not in (None, event.get("ts")):
        return

    channel = event["channel"]
    ts = event["ts"]
    thread_key = _thread_key(channel, ts)
    config = {"configurable": {"thread_id": thread_key}}

    with _runs_lock:
        if thread_key in _runs_in_progress or _already_drafted(config):
            return
        _runs_in_progress.add(thread_key)

    try:
        initial_state = AgentState(
            question=event.get("text", ""),
            slack_channel_id=channel,
            slack_thread_ts=ts,
            asked_by_user_id=event.get("user", "unknown"),
        )
        try:
            result = agent_graph.invoke(initial_state.model_dump(), config)
        except Exception:
            # Every model failed, or the embedding API did: the team still
            # needs to know a question is waiting.
            logger.exception("No draft could be produced for %s", thread_key)
            client.chat_postMessage(
                channel=TEAM_REVIEW_CHANNEL_ID,
                text=(
                    "A question arrived but no draft could be produced. "
                    f"Please answer it by hand in the support inbox:\n>{initial_state.question}"
                ),
            )
            return

        client.chat_postMessage(
            channel=TEAM_REVIEW_CHANNEL_ID,
            text=f"New support question needs review: {result['question']}",
            blocks=_review_blocks(
                result["question"],
                result["draft_answer"],
                result.get("confidence") or 0.0,
                thread_key,
                result.get("passages"),
            ),
        )
    finally:
        with _runs_lock:
            _runs_in_progress.discard(thread_key)


@app.action("approve_answer")
def handle_approve(ack, body, client):
    """Resumes the graph past human_gate with review_status='approved', then
    the post/log nodes run and the answer is posted in the original thread.
    """
    ack()
    thread_key = body["actions"][0]["value"]
    config = {"configurable": {"thread_id": thread_key}}
    reviewer_id = body["user"]["id"]

    if not _resume_after_review(config, {"review_status": "approved", "reviewed_by_user_id": reviewer_id}):
        _tell_reviewer_not_waiting(client, body["channel"]["id"], reviewer_id)
        return

    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"Approved by <@{reviewer_id}> and posted in the support thread.",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ Approved by <@{reviewer_id}> and posted in the support thread."},
            }
        ],
    )


@app.action("edit_answer")
def handle_edit(ack, body, client):
    """Opens a modal for the reviewer to rewrite the draft before it resumes
    the graph with review_status='edited'.
    """
    ack()
    thread_key = body["actions"][0]["value"]
    config = {"configurable": {"thread_id": thread_key}}
    if not _waiting_for_review(config):
        _tell_reviewer_not_waiting(client, body["channel"]["id"], body["user"]["id"])
        return
    current_draft = agent_graph.get_state(config).values.get("draft_answer") or ""

    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "edit_answer_submit",
            "private_metadata": json.dumps(
                {
                    "thread_key": thread_key,
                    "review_channel": body["channel"]["id"],
                    "review_ts": body["message"]["ts"],
                }
            ),
            "title": {"type": "plain_text", "text": "Edit answer"},
            "submit": {"type": "plain_text", "text": "Send"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "answer_block",
                    "label": {"type": "plain_text", "text": "Answer"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "answer_input",
                        "multiline": True,
                        "initial_value": current_draft,
                    },
                }
            ],
        },
    )


@app.view("edit_answer_submit")
def handle_edit_submission(ack, body, client, view):
    """Resumes the graph with the reviewer's rewritten answer and
    review_status='edited', the counterpart to handle_edit's modal.
    """
    ack()
    metadata = json.loads(view["private_metadata"])
    thread_key = metadata["thread_key"]
    edited_text = view["state"]["values"]["answer_block"]["answer_input"]["value"]
    reviewer_id = body["user"]["id"]

    config = {"configurable": {"thread_id": thread_key}}
    decision = {"review_status": "edited", "final_answer": edited_text, "reviewed_by_user_id": reviewer_id}
    if not _resume_after_review(config, decision):
        _tell_reviewer_not_waiting(client, metadata["review_channel"], reviewer_id)
        return

    client.chat_update(
        channel=metadata["review_channel"],
        ts=metadata["review_ts"],
        text=f"Edited by <@{reviewer_id}> and posted in the support thread.",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✏️ Edited by <@{reviewer_id}> and posted in the support thread."},
            }
        ],
    )


@app.action("reject_answer")
def handle_reject(ack, body, client):
    """Resumes the graph with review_status='rejected': post/log are
    skipped, so nothing is posted in the support thread.
    """
    ack()
    thread_key = body["actions"][0]["value"]
    config = {"configurable": {"thread_id": thread_key}}
    reviewer_id = body["user"]["id"]

    if not _resume_after_review(config, {"review_status": "rejected", "reviewed_by_user_id": reviewer_id}):
        _tell_reviewer_not_waiting(client, body["channel"]["id"], reviewer_id)
        return

    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"Rejected by <@{reviewer_id}>.",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"❌ Rejected by <@{reviewer_id}>. Nothing was posted in the support thread.",
                },
            }
        ],
    )


# HTTP transport: a Flask app wrapping the same Bolt `app` and its handlers
# above. Only exercised when SLACK_MODE=http; gunicorn imports this module
# and serves `flask_app` directly, bypassing __main__ entirely.
flask_app = Flask(__name__)
_request_handler = SlackRequestHandler(app)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return _request_handler.handle(request)


@flask_app.route("/", methods=["GET"])
def health():
    """Render (and Slack's own URL-verification ping, if ever used) just
    need a 200 here: no health-check logic beyond "the process is up".
    """
    return "ok"


if __name__ == "__main__":
    if os.getenv("SLACK_MODE", "socket") == "http":
        flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
    else:
        SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
