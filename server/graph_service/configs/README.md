# Configs (MemOS-style)

Configurable parser, chunker, LLM, and user manager (SQLite/MySQL). No graphiti dependency.

## Modules

- **base**: BaseConfig, `from_yaml_file` / `from_json_file`
- **parser**: ParserConfigFactory (backend: markitdown)
- **chunker**: ChunkerConfigFactory (backend: sentence, simple)
- **llm**: LLMConfigFactory (backend: openai)
- **user**: UserManagerConfigFactory (backend: sqlite, mysql); MySQLUserManagerConfig for MySQL

## MySQL

Use `mysql.example.yaml` as template. Env overrides (optional):

- `USER_MANAGER_BACKEND=mysql`
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_CHARSET`

Or load in code:

```python
from graph_service.configs import UserManagerConfigFactory
cfg = UserManagerConfigFactory.from_yaml_file("configs/mysql.example.yaml")
# cfg.config is MySQLUserManagerConfig
```
