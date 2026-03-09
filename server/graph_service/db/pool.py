"""MySQL connection pool for user, auth, and session storage."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiomysql

from graph_service.config import get_settings


async def get_pool() -> aiomysql.Pool:
    settings = get_settings()
    return await aiomysql.create_pool(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
        minsize=1,
        maxsize=10,
    )


_pool: aiomysql.Pool | None = None


async def init_db() -> None:
    global _pool
    _pool = await get_pool()


async def close_db() -> None:
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
        _pool = None


@asynccontextmanager
async def get_conn() -> AsyncGenerator[aiomysql.Connection, None]:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    async with _pool.acquire() as conn:
        yield conn
