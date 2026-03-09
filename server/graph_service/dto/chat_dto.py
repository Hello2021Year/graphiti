"""Chat and session DTOs."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: int
    session_id: int | None = None
    message: str
    session_name: str | None = None


class ChatResponse(BaseModel):
    session_id: int
    reply: str
    message_id: int | None = None
