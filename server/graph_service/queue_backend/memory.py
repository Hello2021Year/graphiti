"""In-memory queue backend (default): asyncio.Queue, jobs are callables."""

from __future__ import annotations

import asyncio
from typing import Any

from graph_service.queue_backend.base import IngestQueueBackend


class MemoryIngestQueueBackend(IngestQueueBackend):
    """Default: in-memory asyncio.Queue. Jobs are callables (e.g. partial)."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue()

    async def put(self, job: Any) -> None:
        self._queue.put_nowait(job)

    async def get(self) -> Any:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def qsize(self) -> int:
        return self._queue.qsize()
