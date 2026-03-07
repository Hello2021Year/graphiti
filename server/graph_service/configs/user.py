"""User manager config (MemOS-style): SQLite, MySQL."""

from __future__ import annotations

from typing import Any, ClassVar  # noqa: I001

from pydantic import Field, field_validator, model_validator

from graph_service.configs.base import BaseConfig


class BaseUserManagerConfig(BaseConfig):
    """Base user manager config."""

    user_id: str = Field(default='root', description='Default user ID')


class SQLiteUserManagerConfig(BaseUserManagerConfig):
    """SQLite user manager config."""

    db_path: str | None = Field(
        default=None,
        description='Path to SQLite database file',
    )


class MySQLUserManagerConfig(BaseUserManagerConfig):
    """MySQL user manager config (MemOS-style)."""

    host: str = Field(default='localhost', description='MySQL host')
    port: int = Field(default=3306, description='MySQL port')
    username: str = Field(default='root', description='MySQL username')
    password: str = Field(default='', description='MySQL password')
    database: str = Field(default='memos_users', description='MySQL database name')
    charset: str = Field(default='utf8mb4', description='Charset')


class UserManagerConfigFactory(BaseConfig):
    """Factory for user manager config: sqlite or mysql."""

    backend: str = Field(default='sqlite', description='Backend: sqlite, mysql')
    config: Any = Field(default_factory=dict, description='Backend config (dict or instance)')

    backend_to_class: ClassVar[dict[str, type[BaseUserManagerConfig]]] = {
        'sqlite': SQLiteUserManagerConfig,
        'mysql': MySQLUserManagerConfig,
    }

    @field_validator('backend')
    @classmethod
    def validate_backend(cls, v: str) -> str:
        if v not in cls.backend_to_class:
            raise ValueError(f'Unsupported user manager backend: {v}')
        return v

    @model_validator(mode='after')
    def instantiate_config(self) -> UserManagerConfigFactory:
        config_class = self.backend_to_class[self.backend]
        raw = self.config if isinstance(self.config, dict) else {}
        self.config = config_class(**raw)
        return self
