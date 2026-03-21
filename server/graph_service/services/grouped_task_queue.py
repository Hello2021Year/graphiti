import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

TaskCallable = Callable[[], Awaitable[None]]


class GroupedTaskQueue:
    """Queue tasks sequentially per group, while allowing cross-group parallelism."""

    def __init__(self):
        self._queues: dict[str, asyncio.Queue[TaskCallable]] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._shutdown = False

    async def enqueue(self, group_id: str, task: TaskCallable) -> int:
        if self._shutdown:
            raise RuntimeError('Queue is shutting down')

        queue = self._queues.setdefault(group_id, asyncio.Queue())
        await queue.put(task)
        if group_id not in self._workers or self._workers[group_id].done():
            self._workers[group_id] = asyncio.create_task(self._worker(group_id))

        return queue.qsize()

    async def _worker(self, group_id: str) -> None:
        logger.info(f'Started queue worker for group_id={group_id}')
        queue = self._queues[group_id]
        try:
            while True:
                task = await queue.get()
                try:
                    await task()
                except Exception as exc:
                    logger.exception(f'Failed to process task for group_id={group_id}: {exc}')
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            logger.info(f'Cancelled queue worker for group_id={group_id}')
            raise
        finally:
            logger.info(f'Stopped queue worker for group_id={group_id}')

    async def shutdown(self) -> None:
        self._shutdown = True
        for task in self._workers.values():
            task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers.values(), return_exceptions=True)

        self._workers.clear()
        self._queues.clear()
