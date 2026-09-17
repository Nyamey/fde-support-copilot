"""Slack entry point: listens for questions in SUPPORT_INBOX_CHANNEL_ID,
runs them through the agent graph, and posts the human-approval message
(with Approve / Edit / Reject buttons) to TEAM_REVIEW_CHANNEL_ID.

Runs in Socket Mode for local dev (no public URL / no signing-secret setup
needed) — switch to slack_bolt's Flask/FastAPI adapter with HTTP mode when
deploying behind the Dockerfile's exposed port.
"""

import json
import os

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from agent.graph import build_graph
from agent.state import AgentState

load_dotenv()

app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    # Skips Slack's auth.test call at startup when unset/false — needed so
    # importing this module in tests (a fake token) doesn't hit the network.
    # Real deployments should leave SLACK_TOKEN_VERIFICATION unset (defaults on).
    token_verification_enabled=os.getenv("SLACK_TOKEN_VERIFICATION", "true").lower() == "true",
)
agent_graph = build_graph(checkpoint_path=os.getenv("AGENT_CHECKPOINT_PATH", "agent_checkpoints.sqlite"))

SUPPORT_INBOX_CHANNEL_ID = os.environ.get("SUPPORT_INBOX_CHANNEL_ID")
TEAM_REVIEW_CHANNEL_ID = os.environ.get("TEAM_REVIEW_CHANNEL_ID")


def _thread_key(channel: str, ts: str) -> str:
    """LangGraph checkpoint thread_id — the original Slack channel+ts, so an
    action handler can find the right paused graph to resume.
    """
    return f"{channel}:{ts}"


def _review_blocks(question: str, draft_answer: str, confidence: float, thread_key: str) -> list[dict]:
    confidence_label = "high" if confidence >= 0.6 else "low" if confidence > 0 else "none"
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*New question:*\n>{question}"}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Draft answer* (confidence: {confidence_label}):\n{draft_answer}"},
        },
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


@app.event("message")
def handle_support_question(event, client):
    """Fires on every message in SUPPORT_INBOX_CHANNEL_ID. Kicks off the
    agent graph up to the human_gate interrupt, then posts the review
    message to TEAM_REVIEW_CHANNEL_ID with the Approve/Edit/Reject buttons.
    """
    if event.get("channel") != SUPPORT_INBOX_CHANNEL_ID or event.get("subtype") is not None:
        return

    channel = event["channel"]
    ts = event["ts"]
    thread_key = _thread_key(channel, ts)
    config = {"configurable": {"thread_id": thread_key}}

    initial_state = AgentState(
        question=event.get("text", ""),
        slack_channel_id=channel,
        slack_thread_ts=ts,
        asked_by_user_id=event.get("user", "unknown"),
    )
    result = agent_graph.invoke(initial_state.model_dump(), config)

    client.chat_postMessage(
        channel=TEAM_REVIEW_CHANNEL_ID,
        text=f"New support question needs review: {result['question']}",
        blocks=_review_blocks(
            result["question"], result["draft_answer"], result.get("confidence") or 0.0, thread_key
        ),
    )


@app.action("approve_answer")
def handle_approve(ack, body, client):
    """Resumes the graph past human_gate with review_status='approved', then
    the post/log nodes run and the answer reaches the customer.
    """
    ack()
    thread_key = body["actions"][0]["value"]
    config = {"configurable": {"thread_id": thread_key}}
    reviewer_id = body["user"]["id"]

    agent_graph.update_state(config, {"review_status": "approved", "reviewed_by_user_id": reviewer_id})
    agent_graph.invoke(None, config)

    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"Approved and sent by <@{reviewer_id}>.",
        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": f"✅ Approved and sent by <@{reviewer_id}>."}}],
    )


@app.action("edit_answer")
def handle_edit(ack, body, client):
    """Opens a modal for the reviewer to rewrite the draft before it resumes
    the graph with review_status='edited'.
    """
    ack()
    thread_key = body["actions"][0]["value"]
    config = {"configurable": {"thread_id": thread_key}}
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
    review_status='edited' — the counterpart to handle_edit's modal.
    """
    ack()
    metadata = json.loads(view["private_metadata"])
    thread_key = metadata["thread_key"]
    edited_text = view["state"]["values"]["answer_block"]["answer_input"]["value"]
    reviewer_id = body["user"]["id"]

    config = {"configurable": {"thread_id": thread_key}}
    agent_graph.update_state(
        config, {"review_status": "edited", "final_answer": edited_text, "reviewed_by_user_id": reviewer_id}
    )
    agent_graph.invoke(None, config)

    client.chat_update(
        channel=metadata["review_channel"],
        ts=metadata["review_ts"],
        text=f"Edited and sent by <@{reviewer_id}>.",
        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": f"✏️ Edited and sent by <@{reviewer_id}>."}}],
    )


@app.action("reject_answer")
def handle_reject(ack, body, client):
    """Resumes the graph with review_status='rejected' — post/log are
    skipped, nothing reaches the customer.
    """
    ack()
    thread_key = body["actions"][0]["value"]
    config = {"configurable": {"thread_id": thread_key}}
    reviewer_id = body["user"]["id"]

    agent_graph.update_state(config, {"review_status": "rejected", "reviewed_by_user_id": reviewer_id})
    agent_graph.invoke(None, config)

    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=f"Rejected by <@{reviewer_id}>.",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"❌ Rejected by <@{reviewer_id}>. Nothing was sent to the customer."},
            }
        ],
    )


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()
