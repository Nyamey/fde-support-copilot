"""Shared state passed between every node of the support-copilot agent graph."""

from typing import Literal
from pydantic import BaseModel, Field


class RetrievedPassage(BaseModel):
    source: str
    text: str
    score: float


class AgentState(BaseModel):
    # input
    question: str
    slack_channel_id: str
    slack_thread_ts: str
    asked_by_user_id: str

    # retrieve
    passages: list[RetrievedPassage] = Field(default_factory=list)

    # draft
    draft_answer: str | None = None
    confidence: float | None = None

    # human_gate
    review_status: Literal["pending", "approved", "edited", "rejected"] = "pending"
    final_answer: str | None = None
    reviewed_by_user_id: str | None = None

    # log
    logged: bool = False
