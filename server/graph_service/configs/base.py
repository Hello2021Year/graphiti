"""Base config: Pydantic model with optional YAML/JSON load (MemOS-style)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class BaseConfig(BaseModel):
    """Base configuration; subclasses can load from file."""

    model_config = ConfigDict(extra='forbid', strict=True)

    @classmethod
    def from_yaml_file(cls, yaml_path: str | Path) -> Any:
        """Load configuration from a YAML file."""
        import yaml

        with open(yaml_path, encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    @classmethod
    def from_json_file(cls, json_path: str | Path) -> Any:
        """Load configuration from a JSON file."""
        with open(json_path, encoding='utf-8') as f:
            data = f.read()
        return cls.model_validate_json(data)
