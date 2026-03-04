"""
Ingest router: POST /messages (async worker), entity-node, clear, delete endpoints.

Worker lifecycle: started in app lifespan (main.py), not in router lifespan.
FastAPI does not run APIRouter lifespan when the router is included, so the worker
would never start if started here. Using request-scoped Graphiti in background tasks
causes "Driver closed" because the request ends before the queue is processed.
See: https://github.com/getzep/graphiti/pull/1178
"""
import asyncio
import logging
from functools import partial

from fastapi import APIRouter, HTTPException, status
from graphiti_core.errors import NodeNotFoundError  # type: ignore
from graphiti_core.nodes import EpisodeType  # type: ignore
from graphiti_core.utils.maintenance.graph_data_operations import clear_data  # type: ignore

from graph_service.config import get_settings
from graph_service.dto import AddEntityNodeRequest, AddMessagesRequest, Message, Result
from graph_service.zep_graphiti import create_graphiti, ZepGraphitiDep

logger = logging.getLogger(__name__)


class AsyncWorker:
    """Background worker for message ingest. Uses its own persistent Graphiti client."""

    def __init__(self):
        self.queue = asyncio.Queue()
        self.task = None
        self.graphiti = None

    async def worker(self):
        logger.info('Ingest worker loop started')
        while True:
            job = None
            try:
                queue_size = self.queue.qsize()
                logger.debug('Worker waiting for job (queue size=%s)', queue_size)
                job = await self.queue.get()
                logger.info('Worker processing job (queue size after get=%s)', self.queue.qsize())
                await job()
                logger.debug('Worker job completed')
            except asyncio.CancelledError:
                logger.info('Worker cancelled (shutdown)')
                break
            except NodeNotFoundError as e:
                logger.warning('Worker job skipped (node not found): %s', e)
            except Exception as e:
                logger.error('Worker job failed: %s', e, exc_info=True)
            finally:
                if job is not None:
                    self.queue.task_done()
        logger.info('Ingest worker loop stopped')

    async def start(self) -> None:
        if self.task is not None and not self.task.done():
            logger.debug('Ingest worker already running, skip start')
            return
        settings = get_settings()
        self.graphiti = create_graphiti(settings)
        logger.info('Ingest worker: created dedicated Graphiti client')
        self.task = asyncio.create_task(self.worker())
        logger.info('Ingest worker started')

    async def stop(self) -> None:
        logger.info('Ingest worker stopping...')
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self.graphiti:
            await self.graphiti.close()
            self.graphiti = None
            logger.info('Ingest worker Graphiti client closed')
        while not self.queue.empty():
            self.queue.get_nowait()
        logger.info('Ingest worker stopped')


async_worker = AsyncWorker()

router = APIRouter()


@router.post('/messages', status_code=status.HTTP_202_ACCEPTED)
async def add_messages(request: AddMessagesRequest):
    """Queue messages for async ingest. Worker uses its own Graphiti client (see PR #1178)."""
    if async_worker.graphiti is None:
        logger.error('POST /messages rejected: ingest worker not started (check app lifespan)')
        raise HTTPException(
            status_code=503,
            detail='Ingest worker not ready. Ensure server uses app lifespan that starts the worker.',
        )

    async def add_messages_task(m: Message):
        await async_worker.graphiti.add_episode(
            uuid=m.uuid,
            group_id=request.group_id,
            name=m.name,
            episode_body=f'{m.role or ""}({m.role_type}): {m.content}',
            reference_time=m.timestamp,
            source=EpisodeType.message,
            source_description=m.source_description,
        )

    enqueued = 0
    for m in request.messages:
        await async_worker.queue.put(partial(add_messages_task, m))
        enqueued += 1
    logger.info('POST /messages: enqueued %s message(s) for group_id=%s', enqueued, request.group_id)
    return Result(message='Messages added to processing queue', success=True)


@router.post('/entity-node', status_code=status.HTTP_201_CREATED)
async def add_entity_node(
    request: AddEntityNodeRequest,
    graphiti: ZepGraphitiDep,
):
    logger.debug('POST /entity-node: uuid=%s group_id=%s name=%s', request.uuid, request.group_id, request.name)
    node = await graphiti.save_entity_node(
        uuid=request.uuid,
        group_id=request.group_id,
        name=request.name,
        summary=request.summary,
    )
    logger.info('POST /entity-node: created uuid=%s', request.uuid)
    return node


@router.delete('/entity-edge/{uuid}', status_code=status.HTTP_200_OK)
async def delete_entity_edge(uuid: str, graphiti: ZepGraphitiDep):
    await graphiti.delete_entity_edge(uuid)
    logger.info('DELETE /entity-edge: deleted uuid=%s', uuid)
    return Result(message='Entity Edge deleted', success=True)


@router.delete('/group/{group_id}', status_code=status.HTTP_200_OK)
async def delete_group(group_id: str, graphiti: ZepGraphitiDep):
    await graphiti.delete_group(group_id)
    logger.info('DELETE /group: deleted group_id=%s', group_id)
    return Result(message='Group deleted', success=True)


@router.delete('/episode/{uuid}', status_code=status.HTTP_200_OK)
async def delete_episode(uuid: str, graphiti: ZepGraphitiDep):
    await graphiti.delete_episodic_node(uuid)
    logger.info('DELETE /episode: deleted uuid=%s', uuid)
    return Result(message='Episode deleted', success=True)


@router.post('/clear', status_code=status.HTTP_200_OK)
async def clear(graphiti: ZepGraphitiDep):
    await clear_data(graphiti.driver)
    await graphiti.build_indices_and_constraints()
    logger.info('POST /clear: graph cleared and indices rebuilt')
    return Result(message='Graph cleared', success=True)
