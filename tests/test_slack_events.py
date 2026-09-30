"""Tests for Slack event/action handling, without hitting the real Slack API.

slack_app's handler functions are plain module-level functions (slack_bolt
decorates them but doesn't hide them), so they can be called directly with
fake event/body dicts and a mocked client, with no network calls.
"""

import pytest

import slack_app
from agent.state import RetrievedPassage

ANSWER = "Click 'Forgot password' on the login page."


def _review_click(thread_key: str = "C_INBOX:1.1") -> dict:
    return {
        "actions": [{"value": thread_key}],
        "user": {"id": "U_REVIEWER"},
        "channel": {"id": "C_REVIEW"},
        "message": {"ts": "2.2"},
    }


def _paused_for_review(mocker):
    """Snapshot of a run stopped before human_gate, still waiting for a decision."""
    return mocker.Mock(next=("human_gate",), values={"review_status": "pending"})


@pytest.fixture
def real_graph_run(mocker):
    """Lets a question go through the real graph and its SQLite checkpointer,
    with the knowledge base, the model and the Slack post of the answer
    mocked. Returns the mocked client used by post() and the mocked
    add_to_index used by log().
    """
    mocker.patch("agent.nodes.kb_search", return_value=[RetrievedPassage(source="faq.md", text=ANSWER, score=0.9)])
    mocker.patch("agent.nodes.litellm.completion", return_value={"choices": [{"message": {"content": ANSWER}}]})
    thread_client = mocker.patch("agent.nodes.WebClient").return_value
    add_to_index = mocker.patch("agent.nodes.add_to_index")
    return thread_client, add_to_index


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
    """Slack fires a 'message' event (with a subtype) for edits/deletes too;
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


def test_thread_replies_are_not_treated_as_new_questions(mocker):
    """A reply such as "thanks!" under an earlier question arrives as a
    message event whose thread_ts points at the parent message.
    """
    client = mocker.Mock()
    invoke = mocker.patch.object(slack_app.agent_graph, "invoke")
    event = {"channel": "C_INBOX", "ts": "1.2", "thread_ts": "1.1", "text": "thanks!", "user": "U1"}

    slack_app.handle_support_question(event, client)

    invoke.assert_not_called()
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


def test_review_message_lists_the_sources_behind_the_draft(mocker):
    """Each file appears once, with its best score, best first."""
    client = mocker.Mock()
    passages = [
        RetrievedPassage(source="approval_flow.md", text="Any member of the review channel.", score=0.71),
        RetrievedPassage(source="overview.md", text="A reviewer approves every answer.", score=0.48),
        RetrievedPassage(source="approval_flow.md", text="The reviewer's user ID is recorded.", score=0.55),
    ]
    mocker.patch.object(
        slack_app.agent_graph,
        "invoke",
        return_value={
            "question": "Who can approve an answer?",
            "draft_answer": "Any member of the review channel.",
            "confidence": 0.58,
            "passages": passages,
        },
    )
    event = {"channel": "C_INBOX", "ts": "1700000000.000200", "text": "Who can approve an answer?", "user": "U1"}

    slack_app.handle_support_question(event, client)

    blocks_text = str(client.chat_postMessage.call_args.kwargs["blocks"])
    assert "approval_flow.md (0.71), overview.md (0.48)" in blocks_text


def test_review_message_says_when_no_source_passed_the_threshold(mocker):
    client = mocker.Mock()
    mocker.patch.object(
        slack_app.agent_graph,
        "invoke",
        return_value={
            "question": "What is the capital of Peru?",
            "draft_answer": "I don't have enough information in the knowledge base to answer this confidently.",
            "confidence": 0.0,
            "passages": [],
        },
    )
    event = {"channel": "C_INBOX", "ts": "1700000000.000300", "text": "What is the capital of Peru?", "user": "U1"}

    slack_app.handle_support_question(event, client)

    blocks_text = str(client.chat_postMessage.call_args.kwargs["blocks"])
    assert "none above the relevance threshold" in blocks_text


def test_review_channel_is_told_when_no_draft_could_be_produced(mocker):
    """If every model fails, the team still has to learn that a question is
    waiting, rather than nothing appearing in the review channel.
    """
    client = mocker.Mock()
    mocker.patch.object(slack_app.agent_graph, "invoke", side_effect=RuntimeError("every model failed"))
    event = {"channel": "C_INBOX", "ts": "1700000000.000700", "text": "How do I reset my password?", "user": "U1"}

    slack_app.handle_support_question(event, client)

    kwargs = client.chat_postMessage.call_args.kwargs
    assert kwargs["channel"] == "C_REVIEW"
    assert "no draft could be produced" in kwargs["text"]
    assert "How do I reset my password?" in kwargs["text"]


def test_redelivered_event_does_not_start_a_second_run(mocker, real_graph_run):
    """Slack sends an event again when the first delivery got no 2xx within
    3 seconds, for example while a sleeping instance boots. The copy has the
    same channel and ts, so it must not produce a second review message.
    """
    client = mocker.Mock()
    event = {"channel": "C_INBOX", "ts": "1700000000.000400", "text": "How do I reset my password?", "user": "U1"}

    slack_app.handle_support_question(event, client)
    slack_app.handle_support_question(dict(event), client)

    client.chat_postMessage.assert_called_once()


def test_event_already_being_processed_is_skipped(mocker):
    client = mocker.Mock()
    invoke = mocker.patch.object(slack_app.agent_graph, "invoke")
    mocker.patch.object(slack_app, "_runs_in_progress", {"C_INBOX:1.3"})
    event = {"channel": "C_INBOX", "ts": "1.3", "text": "How do I reset my password?", "user": "U1"}

    slack_app.handle_support_question(event, client)

    invoke.assert_not_called()
    client.chat_postMessage.assert_not_called()


def test_approve_action_resumes_graph_with_approved_status(mocker):
    client = mocker.Mock()
    mocker.patch.object(slack_app.agent_graph, "get_state", return_value=_paused_for_review(mocker))
    update_state = mocker.patch.object(slack_app.agent_graph, "update_state")
    invoke = mocker.patch.object(slack_app.agent_graph, "invoke")

    slack_app.handle_approve(lambda: None, _review_click(), client)

    config = {"configurable": {"thread_id": "C_INBOX:1.1"}}
    update_state.assert_called_once_with(
        config, {"review_status": "approved", "reviewed_by_user_id": "U_REVIEWER"}
    )
    invoke.assert_called_once_with(None, config)
    client.chat_update.assert_called_once()


def test_reject_action_never_triggers_a_post(mocker):
    client = mocker.Mock()
    mocker.patch.object(slack_app.agent_graph, "get_state", return_value=_paused_for_review(mocker))
    mocker.patch.object(slack_app.agent_graph, "update_state")
    invoke = mocker.patch.object(slack_app.agent_graph, "invoke")

    slack_app.handle_reject(lambda: None, _review_click(), client)

    # The graph itself (route_after_review, tested separately) is what
    # guarantees post() doesn't run on a rejection; this just confirms the
    # handler resumes with review_status="rejected" rather than skipping the
    # resume entirely, which would leave the graph stuck mid-interrupt.
    invoke.assert_called_once()
    config = {"configurable": {"thread_id": "C_INBOX:1.1"}}
    assert invoke.call_args.args == (None, config)


def test_click_on_an_already_decided_review_changes_nothing(mocker):
    """A second click, or a second reviewer clicking after the first one,
    must not resume the run again, overwrite the recorded decision or
    rewrite the review message. The person who clicked gets a private note.
    """
    client = mocker.Mock()
    decided = mocker.Mock(next=(), values={"review_status": "approved"})
    mocker.patch.object(slack_app.agent_graph, "get_state", return_value=decided)
    update_state = mocker.patch.object(slack_app.agent_graph, "update_state")
    invoke = mocker.patch.object(slack_app.agent_graph, "invoke")

    slack_app.handle_reject(lambda: None, _review_click(), client)

    update_state.assert_not_called()
    invoke.assert_not_called()
    client.chat_update.assert_not_called()
    client.chat_postEphemeral.assert_called_once()
    assert client.chat_postEphemeral.call_args.kwargs["user"] == "U_REVIEWER"


def test_full_loop_posts_in_the_thread_only_after_approval(mocker, real_graph_run):
    """Real graph and checkpointer: the run stops at the human gate, the
    answer is posted in the original thread only after Approve, and a second
    Approve click posts nothing more.
    """
    thread_client, add_to_index = real_graph_run
    client = mocker.Mock()
    event = {"channel": "C_INBOX", "ts": "1700000000.000500", "text": "How do I reset my password?", "user": "U1"}

    slack_app.handle_support_question(event, client)

    client.chat_postMessage.assert_called_once()
    thread_client.chat_postMessage.assert_not_called()

    slack_app.handle_approve(lambda: None, _review_click("C_INBOX:1700000000.000500"), client)
    slack_app.handle_approve(lambda: None, _review_click("C_INBOX:1700000000.000500"), client)

    thread_client.chat_postMessage.assert_called_once_with(
        channel="C_INBOX", thread_ts="1700000000.000500", text=ANSWER
    )
    add_to_index.assert_called_once()


def test_full_loop_reject_posts_nothing_and_logs_nothing(mocker, real_graph_run):
    thread_client, add_to_index = real_graph_run
    client = mocker.Mock()
    event = {"channel": "C_INBOX", "ts": "1700000000.000600", "text": "How do I reset my password?", "user": "U1"}

    slack_app.handle_support_question(event, client)
    slack_app.handle_reject(lambda: None, _review_click("C_INBOX:1700000000.000600"), client)

    thread_client.chat_postMessage.assert_not_called()
    add_to_index.assert_not_called()
    assert slack_app.agent_graph.get_state({"configurable": {"thread_id": "C_INBOX:1700000000.000600"}}).next == ()
