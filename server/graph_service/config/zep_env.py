"""Protocol for Zep/Graphiti environment (Neo4j + OpenAI) used by create_graphiti."""

from __future__ import annotations

from typing import Protocol


class ZepEnvDep(Protocol):
    """Settings object that provides Neo4j and LLM/embedder configuration."""

    @property
    def neo4j_uri(self) -> str | None: ...

    @property
    def neo4j_user(self) -> str | None: ...

    @property
    def neo4j_password(self) -> str | None: ...

    @property
    def openai_api_key(self) -> str | None: ...

    @property
    def openai_base_url(self) -> str | None: ...

    @property
    def embedding_model_name(self) -> str | None: ...

    @property
    def model_name(self) -> str | None: ...
