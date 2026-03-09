"""Session and message storage (user history)."""

from datetime import datetime
from typing import Any

import aiomysql
from aiomysql import Connection

from graph_service.db import get_conn


async def create_session(user_id: int, name: str = "New session") -> int:
    async with get_conn() as conn:
        cursor = await conn.cursor()
        try:
            await cursor.execute(
                "INSERT INTO sessions (user_id, name) VALUES (%s, %s)",
                (user_id, name),
            )
            return int(cursor.lastrowid or 0)
        finally:
            await cursor.close()


async def list_sessions(user_id: int) -> list[dict[str, Any]]:
    async with get_conn() as conn:
        cursor = await conn.cursor(aiomysql.DictCursor)
        try:
            await cursor.execute(
                "SELECT id, user_id, name, created_at, updated_at FROM sessions WHERE user_id = %s ORDER BY updated_at DESC",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in (rows or [])]
        finally:
            await cursor.close()


async def get_session(session_id: int, user_id: int) -> dict[str, Any] | None:
    async with get_conn() as conn:
        cursor = await conn.cursor(aiomysql.DictCursor)
        try:
            await cursor.execute(
                "SELECT id, user_id, name, created_at, updated_at FROM sessions WHERE id = %s AND user_id = %s",
                (session_id, user_id),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await cursor.close()


async def get_session_messages(session_id: int, user_id: int) -> list[dict[str, Any]]:
    async with get_conn() as conn:
        cursor = await conn.cursor(aiomysql.DictCursor)
        try:
            await cursor.execute(
                """
                SELECT m.id, m.session_id, m.role, m.content, m.created_at
                FROM session_messages m
                INNER JOIN sessions s ON s.id = m.session_id AND s.user_id = %s
                WHERE m.session_id = %s
                ORDER BY m.created_at ASC
                """,
                (user_id, session_id),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in (rows or [])]
        finally:
            await cursor.close()


async def add_message(session_id: int, user_id: int, role: str, content: str) -> int:
    if role not in ("user", "assistant", "system"):
        raise ValueError("role must be user, assistant, or system")
    async with get_conn() as conn:
        cursor = await conn.cursor()
        try:
            await cursor.execute(
                "SELECT id FROM sessions WHERE id = %s AND user_id = %s",
                (session_id, user_id),
            )
            if not await cursor.fetchone():
                raise ValueError("session not found or access denied")
            await cursor.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP(3) WHERE id = %s",
                (session_id,),
            )
            await cursor.execute(
                "INSERT INTO session_messages (session_id, role, content) VALUES (%s, %s, %s)",
                (session_id, role, content),
            )
            return int(cursor.lastrowid or 0)
        finally:
            await cursor.close()
