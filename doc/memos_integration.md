# MemOS 集成：文件处理封装与配置模块

## 一、设计原则

1. **文件处理全部放在 parsers 下**：解析、分块、LLM 提取等均在 `server/graph_service/parsers/` 内完成，**不直接调用 graphiti**。上游（如 ingest 路由）只调用 parsers 的接口，再将返回的“消息”列表转为 RawEpisode 等写入图。
2. **配置模块 MemOS 风格**：`server/graph_service/configs/` 提供可配置的 parser、chunker、LLM、user（SQLite/MySQL），支持 YAML/JSON 与 env。

---

## 二、修改与新增文件一览

### 2.1 配置模块（configs，MemOS 风格）

| 路径 | 说明 |
|------|------|
| `server/graph_service/configs/__init__.py` | 导出 BaseConfig, ParserConfigFactory, ChunkerConfigFactory, LLMConfigFactory, UserManagerConfigFactory, MySQLUserManagerConfig |
| `server/graph_service/configs/base.py` | BaseConfig，`from_yaml_file` / `from_json_file` |
| `server/graph_service/configs/parser.py` | ParserConfigFactory，backend: markitdown |
| `server/graph_service/configs/chunker.py` | ChunkerConfigFactory，backend: sentence, simple |
| `server/graph_service/configs/llm.py` | LLMConfigFactory，backend: openai（api_key, api_base, model 等） |
| `server/graph_service/configs/user.py` | UserManagerConfigFactory；SQLiteUserManagerConfig、**MySQLUserManagerConfig**（host, port, username, password, database, charset） |
| `server/graph_service/configs/mysql.example.yaml` | MySQL 配置示例，可直接用 `UserManagerConfigFactory.from_yaml_file()` 加载 |
| `server/graph_service/configs/README.md` | configs 使用说明与 MySQL 配置方式 |

说明：原有 FastAPI 配置仍在 **`server/graph_service/config.py`**（Settings, get_settings），未改动。新增的 **configs** 包仅用于文件处理与用户后端配置，与 MemOS 的 config 结构对齐。

### 2.2 文件处理（parsers，无 graphiti）

| 路径 | 说明 |
|------|------|
| `server/graph_service/parsers/parser.py` | 已有；`parse_file(path)`，markitdown，不变 |
| `server/graph_service/parsers/prompts.py` | **新增**。MemOS 风格 doc-reader 提示词（中/英），`get_doc_reader_prompt(chunk_text)` |
| `server/graph_service/parsers/chunker.py` | **新增**。`chunk_text(text, chunk_size, chunk_overlap, backend)`；backend=sentence 时优先 chonkie，否则 simple 按字符分块；读 env `FILE_PARSER_CHUNK_SIZE` / `FILE_PARSER_CHUNK_OVERLAP` |
| `server/graph_service/parsers/llm_client.py` | **新增**。`extract_memory_from_chunk(chunk_text, api_key=, model=, api_base=)`，调用 OpenAI 兼容 API，解析 JSON（key, value, memory_type, tags），**不依赖 graphiti** |
| `server/graph_service/parsers/file_processor.py` | **新增**。`process_file_to_messages(path_or_content, mode=fast|fine, use_llm=, api_key=, ...)`：先 `parse_file` 或直接用内容 → `chunk_text` → mode=fine 且 use_llm 时对每块调用 `extract_memory_from_chunk` → 返回 `list[dict]`，每项 `{content, tags, memory_type}`，供上层转成消息或 RawEpisode |
| `server/graph_service/parsers/__init__.py` | 导出 `parse_file`, `process_file_to_messages`, `chunk_text` |

以上均在 **parsers** 目录内完成，**没有任何 import graphiti**。

### 2.3 其他

- **`server/graph_service/file_processing.py`**：保留现有逻辑（供 ingest 的 fast/fine/memos 分块）；如需完全走 MemOS 流程，可改为在此处调用 `parsers.process_file_to_messages`，再将返回的 `content` 列表转成 RawEpisode（仍不把 graphiti 引入 parsers）。
- **MySQL 实际连接**：当前 **auth/db.py** 仍为 SQLite。configs 中的 **MySQLUserManagerConfig** 与 **mysql.example.yaml** 仅提供配置结构；若要用 MySQL 存用户/API Key，需在 auth 层根据 `UserManagerConfigFactory` 选择 SQLite 或 MySQL 并实现对应连接（可后续按 configs 的 MySQL 配置扩展）。

---

## 三、使用方式

### 3.1 仅解析 + 分块（无 LLM）

```python
from graph_service.parsers import parse_file, chunk_text

text = parse_file("/path/to/doc.pdf")
chunks = chunk_text(text, chunk_size=1280, chunk_overlap=200, backend="sentence")
```

### 3.2 解析 + 分块 + LLM 提取（MemOS fine 风格）

```python
import os
from graph_service.parsers import process_file_to_messages

messages = process_file_to_messages(
    "/path/to/doc.pdf",
    mode="fine",
    use_llm=True,
    api_key=os.environ.get("OPENAI_API_KEY"),
    model="gpt-4o-mini",
    chunk_size=1280,
    chunk_overlap=200,
)
# messages: list[dict] with keys content, tags, memory_type
# 上层可将 content 转为 RawEpisode.content 等写入 graphiti
```

### 3.3 配置加载（MemOS 风格）

```python
from graph_service.configs import (
    ParserConfigFactory,
    ChunkerConfigFactory,
    LLMConfigFactory,
    UserManagerConfigFactory,
)
# From dict (e.g. from env)
parser_cfg = ParserConfigFactory(backend="markitdown", config={})
chunker_cfg = ChunkerConfigFactory(backend="sentence", config={"chunk_size": 1280, "chunk_overlap": 200})
llm_cfg = LLMConfigFactory(backend="openai", config={"model_name_or_path": "gpt-4o-mini", "api_key": "..."})
user_cfg = UserManagerConfigFactory.from_yaml_file("graph_service/configs/mysql.example.yaml")
# user_cfg.config is MySQLUserManagerConfig when backend=mysql
```

### 3.4 MySQL 配置

- 示例文件：`server/graph_service/configs/mysql.example.yaml`
- 字段：host, port, username, password, database, charset（与 MemOS mem_user 一致）
- 通过 `UserManagerConfigFactory.from_yaml_file()` 或从 env 构造 config dict 加载；实际用 MySQL 存用户时需在 auth 层接此配置并实现 MySQL 连接与 DDL。

---

## 四、MemOS mem-reader 对应关系

| MemOS（mem-reader / configs） | 本仓库 |
|-------------------------------|--------|
| markitdown 解析文件 | `parsers/parser.parse_file` |
| chonkie / CharacterTextChunker / MarkdownChunker | `parsers/chunker.chunk_text`（sentence→chonkie，simple→字符分块） |
| FileContentParser.parse_fine + LLM | `parsers/file_processor.process_file_to_messages(mode='fine', use_llm=True)` + `parsers/llm_client.extract_memory_from_chunk` |
| DOC_READER prompt | `parsers/prompts.get_doc_reader_prompt` |
| ParserConfigFactory / ChunkerConfigFactory / LLMConfigFactory | `configs/parser`, `configs/chunker`, `configs/llm` |
| UserManagerConfigFactory (MySQL) | `configs/user.UserManagerConfigFactory`, `MySQLUserManagerConfig`，示例 `configs/mysql.example.yaml` |

所有文件操作与 LLM 调用均限制在 **parsers** 与 **configs** 中；与 graphiti 的衔接仅在上层（如 ingest 路由）将 `process_file_to_messages` 的返回转为图谱写入。
