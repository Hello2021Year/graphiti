"""Application configuration. Uses env vars for MySQL, JWT, UCloud API, queue, idempotency."""

from functools import lru_cache
from os import getenv


def _str(key: str, default: str = "") -> str:
    return getenv(key, default)


def _int(key: str, default: int = 0) -> int:
    try:
        return int(getenv(key, str(default)))
    except ValueError:
        return default


class Settings:
    """Server settings from environment."""

    def __init__(self) -> None:
        self.MYSQL_HOST = _str("MYSQL_HOST", "127.0.0.1")
        self.MYSQL_PORT = _int("MYSQL_PORT", 3306)
        self.MYSQL_USER = _str("MYSQL_USER", "root")
        self.MYSQL_PASSWORD = _str("MYSQL_PASSWORD", "")
        self.MYSQL_DATABASE = _str("MYSQL_DATABASE", "graphiti")

        self.JWT_SECRET = _str("JWT_SECRET", "change-me-in-production")
        self.JWT_ALGORITHM = _str("JWT_ALGORITHM", "HS256")
        self.JWT_ACCESS_EXPIRE_SECONDS = _int("JWT_ACCESS_EXPIRE_SECONDS", 3600)
        self.JWT_REFRESH_EXPIRE_DAYS = _int("JWT_REFRESH_EXPIRE_DAYS", 7)

        self.DEFAULT_VERIFICATION_CODE = _str("DEFAULT_VERIFICATION_CODE", "20250325")

        self.UCLOUD_API_KEY = _str("UCLOUD_API_KEY", "")
        self.UCLOUD_LLM_BASE_URL = _str(
            "UCLOUD_LLM_BASE_URL", "https://api.ucloud.cn/llm/v1"
        )
        self.UCLOUD_LLM_MODEL = _str("UCLOUD_LLM_MODEL", "gpt-4")

        self.idempotency_ttl_sec = _int("IDEMPOTENCY_TTL_SEC", 86400)
        self.ingest_queue_backend = _str("INGEST_QUEUE_BACKEND", "memory")
        self.redis_url = _str("REDIS_URL", "")

    @property
    def mysql_dsn(self) -> str:
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
