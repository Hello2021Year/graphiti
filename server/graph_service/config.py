from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore


class Settings(BaseSettings):
    openai_api_key: str
    openai_base_url: str | None = Field(None)
    model_name: str | None = Field(None)
    embedding_model_name: str | None = Field(None)
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    auth_required: bool = Field(
        default=False, description='If true, ingest endpoints require X-API-Key'
    )
    auth_db_path: str | None = Field(
        None, description='Path to SQLite DB for users/api_keys; default data/graph_service.db'
    )
    # Ingest queue: memory (default) or redis. Redis requires REDIS_URL.
    ingest_queue_backend: str = Field(
        default='memory', description='Queue backend: memory (default) or redis'
    )
    redis_url: str | None = Field(
        default=None, description='Redis URL when ingest_queue_backend=redis'
    )
    # Idempotency: reject duplicate add within window (X-Idempotency-Key).
    idempotency_ttl_sec: int = Field(
        default=86400, description='Idempotency key TTL in seconds (default 24h)'
    )

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')


@lru_cache
def get_settings():
    return Settings()  # type: ignore[call-arg]


ZepEnvDep = Annotated[Settings, Depends(get_settings)]
