"""Session list/detail DTOs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SessionSummary(BaseModel):
    id: int
    user_id: int
    name: str
    created_at: datetime
    updated_at: datetime


class MessageItem(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    created_at: datetime


class SessionDetail(BaseModel):
    id: int
    user_id: int
    name: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageItem]
