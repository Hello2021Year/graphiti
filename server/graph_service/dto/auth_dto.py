"""Auth request/response DTOs."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    code: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
