"""Auth: login with email + verification code, issue bearer + refresh token."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import jwt
from aiomysql import Connection

from graph_service.config import get_settings
from graph_service.db import get_conn


class LoginResult(NamedTuple):
    user_id: int
    email: str
    access_token: str
    refresh_token: str
    expires_in: int


# TODO: real verification (e.g. send code via email); for now accept default code only
def _verify_code(email: str, code: str) -> bool:
    settings = get_settings()
    return code == settings.DEFAULT_VERIFICATION_CODE


def _make_access_token(user_id: int, email: str) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.JWT_ACCESS_EXPIRE_SECONDS
    exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    payload = {"sub": str(user_id), "email": email, "exp": exp}
    token = jwt.encode(
        payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return token, expires_in


def _make_refresh_token_str() -> str:
    return secrets.token_urlsafe(48)


async def _get_or_create_user(conn: Connection, email: str) -> int:
    cursor = await conn.cursor()
    try:
        await cursor.execute(
            "SELECT id FROM users WHERE email = %s", (email,)
        )
        row = await cursor.fetchone()
        if row:
            return int(row[0])
        await cursor.execute(
            "INSERT INTO users (email) VALUES (%s)", (email,)
        )
        return int(cursor.lastrowid or 0)
    finally:
        await cursor.close()


async def _store_refresh_token(conn: Connection, user_id: int, token: str) -> None:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_EXPIRE_DAYS
    )
    cursor = await conn.cursor()
    try:
        await cursor.execute(
            "INSERT INTO refresh_tokens (user_id, token, expires_at) VALUES (%s, %s, %s)",
            (user_id, token, expires_at),
        )
    finally:
        await cursor.close()


async def login(email: str, code: str) -> LoginResult | None:
    if not _verify_code(email, code):
        return None
    async with get_conn() as conn:
        user_id = await _get_or_create_user(conn, email)
        access_token, expires_in = _make_access_token(user_id, email)
        refresh_token = _make_refresh_token_str()
        await _store_refresh_token(conn, user_id, refresh_token)
        return LoginResult(
            user_id=user_id,
            email=email,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        )
