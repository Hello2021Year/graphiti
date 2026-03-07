"""Redis queue backend (optional). Requires redis package and INGEST_QUEUE_BACKEND=redis, REDIS_URL."""

from __future__ import annotations

import json
import logging
from typing import Any

from graph_service.queue_backend.base import IngestQueueBackend

logger = logging.getLogger(__name__)

REDIS_QUEUE_KEY = 'graph_service:ingest:queue'
REDIS_QUEUE_BLOCK_SEC = 5


class RedisIngestQueueBackend(IngestQueueBackend):
    """Redis list (LPUSH/BRPOP). Jobs stored as JSON: {type, payload}."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: Any = None

    async def _client(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            except ImportError as e:
                raise RuntimeError('Redis backend requires: pip install redis') from e
        return self._redis

    async def put(self, job: Any) -> None:
        if callable(job):
            raise TypeError(
                'Redis backend requires serializable job dict (type + payload), not callable'
            )
        client = await self._client()
        await client.lpush(REDIS_QUEUE_KEY, json.dumps(job, default=str))

    async def get(self) -> Any:
        client = await self._client()
        while True:
            result = await client.brpop(REDIS_QUEUE_KEY, timeout=REDIS_QUEUE_BLOCK_SEC)
            if result is None:
                continue
            _, raw = result
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:
                logger.warning('Invalid job JSON from Redis: %s', e)
                continue

    def task_done(self) -> None:
        pass

    async def qsize(self) -> int:
        client = await self._client()
        return await client.llen(REDIS_QUEUE_KEY)
