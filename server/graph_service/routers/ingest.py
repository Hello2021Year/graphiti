"""
Ingest router: POST /messages (async worker), POST /ingest/file, entity-node, clear, delete endpoints.

Worker lifecycle: started in app lifespan (main.py), not in router lifespan.
FastAPI does not run APIRouter lifespan when the router is included, so the worker
would never start if started here. Using request-scoped Graphiti in background tasks
causes "Driver closed" because the request ends before the queue is processed.
See: https://github.com/getzep/graphiti/pull/1178
"""
import asyncio
import logging
import os
import tempfile
from functools import partial

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from graphiti_core.errors import NodeNotFoundError  # type: ignore
from graphiti_core.nodes import EpisodeType  # type: ignore
from graphiti_core.utils.bulk_utils import RawEpisode  # type: ignore
from graphiti_core.utils.content_chunking import chunk_text_content  # type: ignore
from graphiti_core.utils.datetime_utils import utc_now  # type: ignore
from graphiti_core.utils.maintenance.graph_data_operations import clear_data  # type: ignore

from graph_service.config import get_settings
from graph_service.dto import (
    AddEntityNodeRequest,
    AddMessagesRequest,
    FileIngestResponse,
    Message,
    Result,
)
from graph_service.parsers import parse_file
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


async def _file_ingest_task(
    path: str,
    name: str,
    group_id: str | None,
    desc: str | None,
    use_bulk: bool,
) -> None:
    """Parse file to Markdown, optionally chunk, then add_episode or add_episode_bulk."""
    try:
        text = await asyncio.to_thread(parse_file, path)
        if not text.strip():
            logger.warning('Parsed file %s produced empty text', name)
            return
        now = utc_now()
        desc = desc or name
        if use_bulk:
            chunks = chunk_text_content(text)
            raw_episodes = [
                RawEpisode(
                    name=f'{name}#{i}',
                    content=chunk,
                    source_description=desc,
                    source=EpisodeType.text,
                    reference_time=now,
                )
                for i, chunk in enumerate(chunks)
            ]
            await async_worker.graphiti.add_episode_bulk(raw_episodes, group_id=group_id)
            logger.info(
                'File ingest (bulk) completed: %s -> %s episodes (graphiti_id=%s)',
                name,
                len(raw_episodes),
                group_id,
            )
        else:
            await async_worker.graphiti.add_episode(
                name=name,
                episode_body=text,
                source=EpisodeType.text,
                source_description=desc,
                reference_time=now,
                group_id=group_id,
            )
            logger.info('File ingest completed: %s (graphiti_id=%s)', name, group_id)
    finally:
        try:
            os.unlink(path)
        except OSError as e:
            logger.warning('Failed to remove temp file %s: %s', path, e)


@router.post(
    '/ingest/file',
    status_code=status.HTTP_202_ACCEPTED,
    response_model=FileIngestResponse,
    summary='Upload file and ingest into graph',
    description=(
        'Upload a file (PDF, Word, Excel, PowerPoint, etc.); it is converted to Markdown and '
        'ingested. Use **graphiti_id** to associate with a graph/partition. '
        'With **use_bulk**=true (default), content is chunked and sent via add_episode_bulk for faster graph build.'
    ),
)
@router.post(
    '/submit/file',
    status_code=status.HTTP_202_ACCEPTED,
    response_model=FileIngestResponse,
    summary='Submit file (提交文件)',
    description='Same as POST /ingest/file: upload a file to be parsed and ingested into the graph.',
)
async def ingest_file(
    file: UploadFile = File(..., description='File to ingest (e.g. PDF, DOCX, XLSX)'),
    graphiti_id: str | None = Query(
        default=None,
        description='Graph/group id to associate with the ingested file. Optional.',
    ),
    source_description: str | None = Query(
        default=None,
        description='Source description for the episode (e.g. document title). Optional.',
    ),
    use_bulk: bool = Query(
        default=True,
        description='If true, chunk content and use add_episode_bulk for faster graph build; else single add_episode.',
    ),
):
    """Upload a file, parse to Markdown, and queue for graph ingest. Options appear in Swagger."""
    if async_worker.graphiti is None:
        logger.error('POST /ingest/file rejected: ingest worker not started')
        raise HTTPException(
            status_code=503,
            detail='Ingest worker not ready. Ensure server uses app lifespan that starts the worker.',
        )

    filename = file.filename or 'unknown'
    suffix = os.path.splitext(filename)[1] or ''
    fd, temp_path = tempfile.mkstemp(suffix=suffix)
    try:
        os.close(fd)
        content = await file.read()
        with open(temp_path, 'wb') as f:
            f.write(content)
    except Exception as e:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        logger.error('Failed to save uploaded file: %s', e)
        raise HTTPException(status_code=400, detail=f'Failed to save file: {e}') from e

    await async_worker.queue.put(
        partial(
            _file_ingest_task,
            temp_path,
            filename,
            graphiti_id,
            source_description,
            use_bulk,
        ),
    )
    logger.info('POST /ingest/file: enqueued file=%s graphiti_id=%s use_bulk=%s', filename, graphiti_id, use_bulk)
    return FileIngestResponse(
        message='File added to processing queue',
        success=True,
        filename=filename,
        graphiti_id=graphiti_id,
    )


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
