"""
Pluggable ingest queue backend: default in-memory, optional Redis.
Config: INGEST_QUEUE_BACKEND=memory|redis, REDIS_URL for redis.
"""

from graph_service.queue_backend.base import IngestQueueBackend
from graph_service.queue_backend.memory import MemoryIngestQueueBackend
from graph_service.queue_backend.registry import get_queue_backend

__all__ = [
    'IngestQueueBackend',
    'MemoryIngestQueueBackend',
    'get_queue_backend',
]
