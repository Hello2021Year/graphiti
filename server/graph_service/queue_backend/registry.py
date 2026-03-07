"""Resolve queue backend from config (memory by default, redis if configured)."""

from __future__ import annotations

from graph_service.config import get_settings
from graph_service.queue_backend.base import IngestQueueBackend
from graph_service.queue_backend.memory import MemoryIngestQueueBackend


def get_queue_backend() -> IngestQueueBackend:
    """Return queue backend: memory (default) or redis from config."""
    settings = get_settings()
    backend = getattr(settings, 'ingest_queue_backend', 'memory')
    if backend == 'redis':
        redis_url = getattr(settings, 'redis_url', None) or ''
        if not redis_url:
            raise ValueError('INGEST_QUEUE_BACKEND=redis requires REDIS_URL')
        from graph_service.queue_backend.redis_backend import RedisIngestQueueBackend

        return RedisIngestQueueBackend(redis_url)
    return MemoryIngestQueueBackend()
