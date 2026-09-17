"""Unit tests for each agent node, in isolation — no real Slack or LLM calls."""

from agent.state import AgentState, RetrievedPassage
from agent import nodes


def make_state(**overrides) -> AgentState:
    defaults = dict(
        question="How do I reset my password?",
        slack_channel_id="C123",
        slack_thread_ts="1234.5678",
        asked_by_user_id="U123",
    )
    defaults.update(overrides)
    return AgentState(**defaults)


def test_retrieve_returns_passages(mocker):
    fake_passages = [RetrievedPassage(source="faq.md", text="Click 'Forgot password'.", score=0.92)]
    mocker.patch("agent.nodes.kb_search", return_value=fake_passages)

    result = nodes.retrieve(make_state())

    assert result["passages"] == fake_passages


def test_draft_says_i_dont_know_when_passages_are_empty(mocker):
    """A draft with zero relevant passages should have low confidence and
    say so explicitly, rather than let the LLM invent a plausible answer.
    """
    completion = mocker.patch("agent.nodes.litellm.completion")

    result = nodes.draft(make_state(passages=[]))

    assert result["confidence"] == 0.0
    assert "don't have enough information" in result["draft_answer"].lower()
    completion.assert_not_called()


def test_draft_grounds_answer_in_retrieved_passages(mocker):
    passages = [
        RetrievedPassage(source="faq.md", text="Click 'Forgot password' on the login page.", score=0.9),
    ]
    fake_response = {"choices": [{"message": {"content": "Click 'Forgot password' on the login page."}}]}
    completion = mocker.patch("agent.nodes.litellm.completion", return_value=fake_response)

    result = nodes.draft(make_state(passages=passages))

    assert result["draft_answer"] == "Click 'Forgot password' on the login page."
    assert result["confidence"] == 0.9
    sent_messages = completion.call_args.kwargs["messages"]
    assert "faq.md" in sent_messages[1]["content"]


def test_draft_confidence_is_zero_when_llm_says_it_does_not_know(mocker):
    passages = [RetrievedPassage(source="faq.md", text="Unrelated passage.", score=0.8)]
    fake_response = {
        "choices": [{"message": {"content": "I don't have enough information in the knowledge base to answer this confidently."}}]
    }
    mocker.patch("agent.nodes.litellm.completion", return_value=fake_response)

    result = nodes.draft(make_state(passages=passages))

    assert result["confidence"] == 0.0


def test_human_gate_approved_uses_the_draft_as_final_answer():
    state = make_state(draft_answer="Click 'Forgot password'.", review_status="approved")

    result = nodes.human_gate(state)

    assert result["final_answer"] == "Click 'Forgot password'."


def test_human_gate_edited_uses_the_reviewers_rewrite():
    state = make_state(
        draft_answer="Original draft.",
        review_status="edited",
        final_answer="Reviewer's rewritten answer.",
    )

    result = nodes.human_gate(state)

    assert result["final_answer"] == "Reviewer's rewritten answer."


def test_human_gate_rejected_sets_no_final_answer():
    state = make_state(draft_answer="Original draft.", review_status="rejected")

    result = nodes.human_gate(state)

    assert "final_answer" not in result


def test_post_sends_final_answer_to_the_original_thread(mocker):
    client = mocker.patch("agent.nodes.WebClient")
    state = make_state(final_answer="Here's how to reset your password.")

    nodes.post(state)

    client.return_value.chat_postMessage.assert_called_once_with(
        channel="C123", thread_ts="1234.5678", text="Here's how to reset your password."
    )


def test_log_indexes_the_question_and_final_answer(mocker):
    add_to_index = mocker.patch("agent.nodes.add_to_index")
    state = make_state(final_answer="Here's how to reset your password.")

    result = nodes.log(state)

    assert result == {"logged": True}
    add_to_index.assert_called_once()
    _args, kwargs = add_to_index.call_args
    assert "How do I reset my password?" in kwargs["text"]
    assert "Here's how to reset your password." in kwargs["text"]


def test_post_is_never_called_after_rejection():
    """route_after_review in agent/graph.py must send review_status='rejected'
    straight to END, never to post().
    """
    from langgraph.graph import END

    from agent.graph import route_after_review

    assert route_after_review(make_state(review_status="rejected")) == END


def test_route_after_review_goes_to_post_when_approved_or_edited():
    from agent.graph import route_after_review

    assert route_after_review(make_state(review_status="approved")) == "post"
    assert route_after_review(make_state(review_status="edited")) == "post"
