"""Abstract ingest queue backend (pluggable)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IngestQueueBackend(ABC):
    """Queue backend for ingest jobs. Default: memory. Config can switch to Redis etc."""

    @abstractmethod
    async def put(self, job: Any) -> None:
        """Enqueue a job. For memory: job is a callable; for Redis: job is serializable dict."""

    @abstractmethod
    async def get(self) -> Any:
        """Block until a job is available; return the job (callable or payload dict)."""

    @abstractmethod
    def task_done(self) -> None:
        """Mark the last get() as done (optional for some backends)."""

    async def qsize(self) -> int:
        """Approximate queue size (optional)."""
        return 0
