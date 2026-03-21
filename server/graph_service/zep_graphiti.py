import asyncio
import logging
from typing import Annotated

from fastapi import Depends
from graphiti_core import Graphiti  # type: ignore
from graphiti_core.edges import EntityEdge  # type: ignore
from graphiti_core.errors import EdgeNotFoundError, GroupsEdgesNotFoundError, NodeNotFoundError
from graphiti_core.llm_client import LLMClient  # type: ignore
from graphiti_core.nodes import EntityNode, EpisodicNode  # type: ignore

from graph_service.config import ZepEnvDep
from graph_service.dto import FactResult
from graph_service.errors import ResourceNotFoundError, ServiceNotReadyError

logger = logging.getLogger(__name__)

_graphiti_client: 'ZepGraphiti | None' = None
_graphiti_lock = asyncio.Lock()


class ZepGraphiti(Graphiti):
    def __init__(self, uri: str, user: str, password: str, llm_client: LLMClient | None = None):
        super().__init__(uri, user, password, llm_client)

    async def save_entity_node(self, name: str, uuid: str, group_id: str, summary: str = ''):
        new_node = EntityNode(
            name=name,
            uuid=uuid,
            group_id=group_id,
            summary=summary,
        )
        await new_node.generate_name_embedding(self.embedder)
        await new_node.save(self.driver)
        return new_node

    async def get_entity_edge(self, uuid: str):
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            return edge
        except EdgeNotFoundError as e:
            raise ResourceNotFoundError(e.message) from e

    async def delete_group(self, group_id: str):
        try:
            edges = await EntityEdge.get_by_group_ids(self.driver, [group_id])
        except GroupsEdgesNotFoundError:
            logger.warning(f'No edges found for group {group_id}')
            edges = []

        nodes = await EntityNode.get_by_group_ids(self.driver, [group_id])

        episodes = await EpisodicNode.get_by_group_ids(self.driver, [group_id])

        for edge in edges:
            await edge.delete(self.driver)

        for node in nodes:
            await node.delete(self.driver)

        for episode in episodes:
            await episode.delete(self.driver)

    async def delete_entity_edge(self, uuid: str):
        try:
            edge = await EntityEdge.get_by_uuid(self.driver, uuid)
            await edge.delete(self.driver)
        except EdgeNotFoundError as e:
            raise ResourceNotFoundError(e.message) from e

    async def delete_episodic_node(self, uuid: str):
        try:
            episode = await EpisodicNode.get_by_uuid(self.driver, uuid)
            await episode.delete(self.driver)
        except NodeNotFoundError as e:
            raise ResourceNotFoundError(e.message) from e


def _apply_llm_overrides(client: ZepGraphiti, settings: ZepEnvDep) -> None:
    if settings.openai_base_url is not None:
        client.llm_client.config.base_url = settings.openai_base_url
    if settings.openai_api_key is not None:
        client.llm_client.config.api_key = settings.openai_api_key
    if settings.model_name is not None:
        client.llm_client.model = settings.model_name


def _create_graphiti_client(settings: ZepEnvDep) -> ZepGraphiti:
    client = ZepGraphiti(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    _apply_llm_overrides(client, settings)
    return client


async def initialize_graphiti(settings: ZepEnvDep):
    global _graphiti_client

    async with _graphiti_lock:
        if _graphiti_client is not None:
            return _graphiti_client

        client = _create_graphiti_client(settings)
        try:
            await client.build_indices_and_constraints()
            _graphiti_client = client
            return _graphiti_client
        except Exception:
            await client.close()
            raise


async def shutdown_graphiti() -> None:
    global _graphiti_client

    async with _graphiti_lock:
        if _graphiti_client is None:
            return

        await _graphiti_client.close()
        _graphiti_client = None


def get_initialized_graphiti() -> ZepGraphiti:
    if _graphiti_client is None:
        raise ServiceNotReadyError('Graphiti client is not initialized')
    return _graphiti_client


async def get_graphiti(settings: ZepEnvDep):
    if _graphiti_client is None:
        await initialize_graphiti(settings)
    return get_initialized_graphiti()


def get_fact_result_from_edge(edge: EntityEdge):
    return FactResult(
        uuid=edge.uuid,
        name=edge.name,
        fact=edge.fact,
        valid_at=edge.valid_at,
        invalid_at=edge.invalid_at,
        created_at=edge.created_at,
        expired_at=edge.expired_at,
    )


ZepGraphitiDep = Annotated[ZepGraphiti, Depends(get_graphiti)]
