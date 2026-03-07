"""Parser config (MemOS-style): backend markitdown."""

from __future__ import annotations

from typing import Any, ClassVar  # noqa: I001

from pydantic import Field, field_validator, model_validator

from graph_service.configs.base import BaseConfig


class BaseParserConfig(BaseConfig):
    """Base parser config."""


class MarkItDownParserConfig(BaseParserConfig):
    """MarkItDown parser config."""


class ParserConfigFactory(BaseConfig):
    """Factory for parser config: backend + config dict."""

    backend: str = Field(..., description='Parser backend')
    config: Any = Field(default_factory=dict, description='Backend config (dict or instance)')

    backend_to_class: ClassVar[dict[str, type[BaseParserConfig]]] = {
        'markitdown': MarkItDownParserConfig,
    }

    @field_validator('backend')
    @classmethod
    def validate_backend(cls, v: str) -> str:
        if v not in cls.backend_to_class:
            raise ValueError(f'Invalid parser backend: {v}')
        return v

    @model_validator(mode='after')
    def create_config(self) -> ParserConfigFactory:
        config_class = self.backend_to_class[self.backend]
        raw = self.config if isinstance(self.config, dict) else {}
        self.config = config_class(**raw)
        return self
