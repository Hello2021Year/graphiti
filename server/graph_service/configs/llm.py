"""LLM config (MemOS-style): OpenAI-compatible for doc extraction."""

from __future__ import annotations

from typing import Any, ClassVar  # noqa: I001

from pydantic import Field, field_validator, model_validator

from graph_service.configs.base import BaseConfig


class BaseLLMConfig(BaseConfig):
    """Base LLM config."""

    model_name_or_path: str = Field(..., description='Model name')
    temperature: float = Field(default=0.3, description='Sampling temperature')
    max_tokens: int = Field(default=2048, description='Max tokens to generate')
    api_base: str | None = Field(default=None, description='API base URL')
    api_key: str | None = Field(default=None, description='API key (or from env)')


class OpenAILLMConfig(BaseLLMConfig):
    """OpenAI-compatible API config."""

    api_base: str = Field(default='https://api.openai.com/v1', description='API base URL')
    api_key: str = Field(..., description='API key')


class LLMConfigFactory(BaseConfig):
    """Factory for LLM config."""

    backend: str = Field(default='openai', description='LLM backend')
    config: Any = Field(default_factory=dict, description='Backend config (dict or instance)')

    backend_to_class: ClassVar[dict[str, type[BaseLLMConfig]]] = {
        'openai': OpenAILLMConfig,
    }

    @field_validator('backend')
    @classmethod
    def validate_backend(cls, v: str) -> str:
        if v not in cls.backend_to_class:
            raise ValueError(f'Invalid LLM backend: {v}')
        return v

    @model_validator(mode='after')
    def create_config(self) -> LLMConfigFactory:
        config_class = self.backend_to_class[self.backend]
        raw = self.config if isinstance(self.config, dict) else {}
        self.config = config_class(**raw)
        return self
