"""Chunker config (MemOS-style): sentence, markdown, simple."""

from __future__ import annotations

from typing import Any, ClassVar  # noqa: I001

from pydantic import Field, field_validator, model_validator

from graph_service.configs.base import BaseConfig


class BaseChunkerConfig(BaseConfig):
    """Base chunker config."""

    chunk_size: int = Field(default=1280, description='Max tokens per chunk')
    chunk_overlap: int = Field(default=200, description='Overlap between chunks')


class SentenceChunkerConfig(BaseChunkerConfig):
    """Sentence-based chunker (e.g. chonkie)."""


class SimpleChunkerConfig(BaseChunkerConfig):
    """Simple character/size-based chunker."""


class ChunkerConfigFactory(BaseConfig):
    """Factory for chunker config."""

    backend: str = Field(..., description='Chunker backend: sentence, simple')
    config: Any = Field(default_factory=dict, description='Backend config (dict or instance)')

    backend_to_class: ClassVar[dict[str, type[BaseChunkerConfig]]] = {
        'sentence': SentenceChunkerConfig,
        'simple': SimpleChunkerConfig,
    }

    @field_validator('backend')
    @classmethod
    def validate_backend(cls, v: str) -> str:
        if v not in cls.backend_to_class:
            raise ValueError(f'Invalid chunker backend: {v}')
        return v

    @model_validator(mode='after')
    def create_config(self) -> ChunkerConfigFactory:
        config_class = self.backend_to_class[self.backend]
        raw = self.config if isinstance(self.config, dict) else {}
        self.config = config_class(**raw)
        return self
