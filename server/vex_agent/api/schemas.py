from typing import Literal

from pydantic import BaseModel, Field

Chat = Literal["student", "research"]


class MessageRequest(BaseModel):
    session_id: str | None = Field(
        default=None,
        description="Optional session identifier override for testing or replaying a known session.",
    )
    message: str = Field(default="", max_length=2000, description="Student message text.")
    chat: Chat = Field(
        default="student",
        description="Which chat the message belongs to: the student view or the research view.",
    )
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


class ResearchOverrides(BaseModel):
    """Agent settings a researcher tries from the research preview. A field left out
    keeps the production default. Calls made with them still count against the
    session's token budget."""

    model: str | None = Field(default=None, max_length=200, description="Model id to call.")
    prompt_template: str | None = Field(
        default=None,
        max_length=50_000,
        description="Replacement prompt template. {placeholders} are filled in; see /v1/research/config.",
    )
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=16, le=4096)
    trim_reply: bool = Field(
        default=True,
        description="Trim the reply to bite size (enforce_student_response_length), as students get it.",
    )


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
        max_length=2000,
        description="Raw student chat message to include in the main LLM prompt.",
    )
    overrides: ResearchOverrides | None = Field(
        default=None,
        description="Research-only agent settings from the research preview.",
    )
    chat: Chat = Field(
        default="student",
        description="Which chat the reply belongs to. Overrides always mean the research chat.",
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
    llm_tokens: int | None = Field(default=None, description="Tokens this reply's LLM calls spent.")
    session_tokens: "TokenUsage | None" = None
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


class TokenUsage(BaseModel):
    """This browser session's LLM token budget."""

    used: int
    limit: int


class ResearchDefaults(BaseModel):
    model: str
    max_tokens: int
    trim_reply: bool


class ResearchConfigResponse(BaseModel):
    defaults: ResearchDefaults
    models: list[str]
    models_error: str | None = None
    prompt_template: str
    placeholders: dict[str, str]
    session_tokens: TokenUsage


StudentResponseResponse.model_rebuild()
