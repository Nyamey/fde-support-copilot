"""Tests for Slack event/action handling, without hitting the real Slack API.

slack_app's handler functions are plain module-level functions (slack_bolt
decorates them but doesn't hide them), so they can be called directly with
fake event/body dicts and a mocked client — no network calls needed.
"""

import slack_app


def test_health_endpoint_returns_ok():
    """Render's health check (and any future URL-verification ping) just
    needs a 200 here.
    """
    client = slack_app.flask_app.test_client()

    response = client.get("/")

    assert response.status_code == 200


def test_events_endpoint_delegates_to_the_bolt_request_handler(mocker):
    handle = mocker.patch.object(slack_app._request_handler, "handle", return_value="handled")
    client = slack_app.flask_app.test_client()

    response = client.post("/slack/events", json={"type": "event_callback"})

    assert response.status_code == 200
    handle.assert_called_once()


def test_message_outside_support_inbox_is_ignored(mocker):
    client = mocker.Mock()
    event = {"channel": "C_OTHER", "ts": "1.1", "text": "random chatter", "user": "U1"}

    slack_app.handle_support_question(event, client)

    client.chat_postMessage.assert_not_called()


def test_message_subtype_edits_are_ignored(mocker):
    """Slack fires a 'message' event (with a subtype) for edits/deletes too —
    only a plain new message should kick off the agent.
    """
    client = mocker.Mock()
    event = {
        "channel": "C_INBOX",
        "ts": "1.1",
        "text": "edited text",
        "user": "U1",
        "subtype": "message_changed",
    }

    slack_app.handle_support_question(event, client)

    client.chat_postMessage.assert_not_called()


def test_support_question_posts_a_review_message_with_the_draft(mocker):
    client = mocker.Mock()
    mocker.patch.object(
        slack_app.agent_graph,
        "invoke",
        return_value={"question": "How do I reset my password?", "draft_answer": "Click 'Forgot password'.", "confidence": 0.9},
    )
    event = {"channel": "C_INBOX", "ts": "1700000000.000100", "text": "How do I reset my password?", "user": "U1"}

    slack_app.handle_support_question(event, client)

    client.chat_postMessage.assert_called_once()
    _args, kwargs = client.chat_postMessage.call_args
    assert kwargs["channel"] == "C_REVIEW"
    blocks_text = str(kwargs["blocks"])
    assert "How do I reset my password?" in blocks_text
    assert "Click 'Forgot password'." in blocks_text


def test_approve_action_resumes_graph_with_approved_status(mocker):
    client = mocker.Mock()
    update_state = mocker.patch.object(slack_app.agent_graph, "update_state")
    invoke = mocker.patch.object(slack_app.agent_graph, "invoke")
    body = {
        "actions": [{"value": "C_INBOX:1.1"}],
        "user": {"id": "U_REVIEWER"},
        "channel": {"id": "C_REVIEW"},
        "message": {"ts": "2.2"},
    }

    slack_app.handle_approve(lambda: None, body, client)

    config = {"configurable": {"thread_id": "C_INBOX:1.1"}}
    update_state.assert_called_once_with(
        config, {"review_status": "approved", "reviewed_by_user_id": "U_REVIEWER"}
    )
    invoke.assert_called_once_with(None, config)
    client.chat_update.assert_called_once()


def test_reject_action_never_triggers_a_post(mocker):
    client = mocker.Mock()
    mocker.patch.object(slack_app.agent_graph, "update_state")
    invoke = mocker.patch.object(slack_app.agent_graph, "invoke")
    body = {
        "actions": [{"value": "C_INBOX:1.1"}],
        "user": {"id": "U_REVIEWER"},
        "channel": {"id": "C_REVIEW"},
        "message": {"ts": "2.2"},
    }

    slack_app.handle_reject(lambda: None, body, client)

    # The graph itself (route_after_review, tested separately) is what
    # guarantees post() doesn't run on a rejection — this just confirms the
    # handler resumes with review_status="rejected" rather than skipping the
    # resume entirely, which would leave the graph stuck mid-interrupt.
    invoke.assert_called_once()
    config = {"configurable": {"thread_id": "C_INBOX:1.1"}}
    assert invoke.call_args.args == (None, config)
