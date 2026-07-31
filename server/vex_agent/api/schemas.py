from typing import Literal

from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    session_id: str | None = Field(
        default=None,
        description="Optional session identifier override for testing or replaying a known session.",
    )
    message: str = Field(default="", description="Student message text.")
    playground: str | None = Field(
        default=None,
        description="Task/playground identifier for the current activity, if already known.",
    )


class MessageResponse(BaseModel):
    message_id: str
    session_id: str
    student_id: str
    playground: str
    message: str
    source: Literal["chat", "help_button"]
    status: Literal["received"]


class SessionResolutionResponse(BaseModel):
    session_id: str
    student_id: str
    playground: str
    status: Literal["resolved"]


class StudentResponseRequest(BaseModel):
    message_id: str | None = Field(
        default=None,
        description="Associated inbound message identifier, if available.",
    )
    session_id: str | None = Field(
        default=None,
        description="Resolved session identifier for the current chat session, if already known.",
    )
    playground: str | None = Field(
        default=None,
        description="Task/playground identifier for the current activity, if already known.",
    )
    response_text: str | None = Field(
        default=None,
        description="LLM-generated text shown to the student.",
    )
    student_message: str | None = Field(
        default=None,
        description="Raw student chat message to include in the main LLM prompt.",
    )


class StudentResponseResponse(BaseModel):
    response_id: str
    session_id: str
    student_id: str
    playground: str
    message_id: str | None
    response_text: str
    llm_model: str | None = None
    llm_prompt: str | None = None
    status: Literal["received"]


class FeedbackRequest(BaseModel):
    thumb: Literal["up", "down"] = Field(description="Student reaction.")
    comment: str | None = Field(
        default=None,
        description="Optional freeform student feedback.",
    )


class FeedbackResponse(BaseModel):
    student_id: str
    response_id: str
    thumb: Literal["up", "down"]
    comment: str | None
    status: Literal["received"]
