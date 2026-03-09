# question3：ingest 修复、文件处理（按 MemOS）、用户与 API 鉴权（参考 MemOS）及 DDL

## 一、ingest.py 初始化与类型问题修复（已做）

### 1.1 问题原因

- `AsyncWorker` 在 `__init__` 里将 `self.graphiti = None`，类型为 `Graphiti | None`。
- 在后台任务 `_file_ingest_task`、`add_messages_task` 中访问 `async_worker.graphiti.add_episode_bulk` 等时，类型检查器认为 `graphiti` 可能为 `None`，报错：`None` 没有 `add_episode_bulk` 属性（reportOptionalMemberAccess）。

### 1.2 修改内容

| 位置 | 修改 |
|------|------|
| 文件头 | 增加 `from __future__ import annotations`、`from typing import TYPE_CHECKING`。 |
| 类型 | 在 `TYPE_CHECKING` 下 `from graphiti_core.graphiti import Graphiti as GraphitiClient`，`self.graphiti: GraphitiClient \| None`、`self.task: asyncio.Task[None] \| None`。 |
| 方法 | 增加 `_get_graphiti(self) -> GraphitiClient`：若 `self.graphiti is None` 则 `raise RuntimeError(...)`，否则返回 `self.graphiti`，供 worker 内任务使用。 |
| 任务内 | `add_messages_task`、`_file_ingest_task` 中不再直接使用 `async_worker.graphiti`，改为 `graphiti = async_worker._get_graphiti()` 后使用 `graphiti`，类型收窄且避免 Optional 访问。 |
| `stop()` | 使用局部变量 `task = self.task` 再 `if task is not None: task.cancel(); await task`，满足类型检查。 |

效果：类型检查通过，且 worker 已关闭时入队任务会通过 `_get_graphiti()` 得到 `RuntimeError` 并跳过执行，行为正确。

---

## 二、文件处理按 MemOS 的实现

### 2.1 MemOS 侧（[MemOS](https://github.com/MemTensor/MemOS)、[mem-reader](https://github.com/MemTensor/MemOS/blob/main/pyproject.toml)）

- **解析**：使用 **markitdown**（DOCX、PDF、PPTX、XLS、XLSX 等）将文件转为 Markdown 文本。
- **分块**：使用 **chonkie**（SentenceChunker）按句子边界分块，可配置 `chunk_size`、`chunk_overlap`（默认 2048 / 128 tokens）；MemReader 可选依赖中还有 **langchain-text-splitters** 做 markdown 分块。
- **FileContentParser / parse_fine**：将文件转为“记忆”格式（含 LLM 时输出格式需统一，见 [Issue #1124](https://github.com/MemTensor/MemOS/issues/1124)）。本服务不做 parse_fine 的 LLM 部分，只做「解析 + 分块」与 MemOS 对齐。

### 2.2 本服务实现（按 MemOS 处理）

- **解析**：上传文件 → 临时路径 → **markitdown**（`parse_file`）→ 得到 Markdown 字符串（与 MemOS 一致）。
- **分块模式**：
  - **fast**：使用 graphiti_core 的 `chunk_text_content` 默认参数（段落/句子边界）。
  - **fine**：同上，更小 `chunk_size_tokens` / `overlap_tokens`，更细粒度。
  - **memos**：**按 MemOS** — 使用 **chonkie** 的 `SentenceChunker`（`chunk_size=2048`, `chunk_overlap=128`），按句子边界分块；与 MemOS mem-reader 一致。需安装可选依赖：`pip install graph-service[mem-reader]`（即 chonkie）。
- **入口**：`server/graph_service/file_processing.py` 的 `process_doc_or_md(path_or_content, mode)`，`mode in ('fast','fine','memos')`；若为文件路径则先 `parse_file`，再按 mode 分块，返回 `list[str]`，供 ingest 构造 `RawEpisode` 并 `add_episode_bulk`。
- **API**：`POST /ingest/file`、`POST /submit/file` 的查询参数 **mode** 支持 `fast` | `fine` | `memos`。

这样文件的处理流程与 MemOS 一致：markitdown 解析 + 可选 chonkie 分句分块。

---

## 三、API 鉴权与用户管理（参考 MemOS）

### 3.1 MemOS 侧（[Authentication](https://docs.mem.ai/api-reference/overview/authentication)、[memos-api-mcp](https://github.com/MemTensor/memos-api-mcp)、[PR #166](https://github.com/MemTensor/MemOS/pull/166)）

- **鉴权方式**：HTTP **Bearer Token**（`Authorization: Bearer $MEMOS_API_KEY`）或 `Authorization: Token <api-key>`。
- **用户标识**：`MEMOS_USER_ID`（稳定、建议用邮箱的 SHA-256 等）；与 channel/site 关联。
- **用户存储**：MemOS 提供 **User Manager 工厂**，支持 **SQLite / MySQL** 后端，使用 **SQLAlchemy** 与 **pymysql**（mem-user 可选依赖）。

### 3.2 本服务实现（参考 MemOS）

- **鉴权**：支持 **X-API-Key** 或 **Authorization: Bearer &lt;key&gt;**，与 MemOS 的 Bearer/Token 用法一致。
- **用户**：每个用户有唯一 `id`、`username`、`created_at`；可与图分区（如 `graphiti_id`）关联。
- **API Key**：创建时生成随机 key（前缀 `sk-`），**仅返回一次**；存储只保存 **key 的哈希**（SHA-256），鉴权时用请求头中的 key 哈希与库中比对。
- **存储**：默认 **SQLite**（单文件）；可通过配置或环境变量切换路径；生产可换 MySQL，表结构兼容（见下方 DDL）。

---

## 四、DDL（用户与 API Key 表结构）

以下为当前实现使用的建表语句，便于迁移或改为 MySQL 时复用。

### 4.1 SQLite（当前默认）

```sql
-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- API Key 表（仅存 key 哈希，不存明文）
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT 'default',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys(key_hash);
```

### 4.2 MySQL（参考 MemOS mem-user，生产可选用）

```sql
-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- API Key 表
CREATE TABLE IF NOT EXISTS api_keys (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    key_hash VARCHAR(64) NOT NULL,
    name VARCHAR(64) NOT NULL DEFAULT 'default',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX ix_api_keys_key_hash (key_hash),
    INDEX ix_api_keys_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

说明：

- SQLite 的 `TEXT` 在 MySQL 中对应 `VARCHAR(36)`（UUID）或 `VARCHAR(64)`（SHA-256 hex）。
- `key_hash` 为 API Key 的 SHA-256 十六进制字符串（64 字符）。
- 本服务当前实现使用 SQLite 与上述 SQLite DDL；若改用 MySQL，只需实现相同的 CRUD 接口（或使用 SQLAlchemy 映射上述结构），并配置连接与 `AUTH_DB_PATH`（或等效配置）。

---

## 五、修改清单与使用方式

### 5.1 修改清单

| 序号 | 位置 | 说明 |
|------|------|------|
| 1 | `server/graph_service/routers/ingest.py` | 修复 AsyncWorker 类型与 `_get_graphiti()`；任务内用 `graphiti = _get_graphiti()`；`stop()` 中 task 类型收窄。 |
| 2 | `server/graph_service/file_processing.py` | 按 MemOS：支持 **memos** 模式，使用 **chonkie** SentenceChunker；fast/fine 仍用 graphiti_core；`process_doc_or_md(path_or_content, mode)`。 |
| 3 | `server/graph_service/routers/ingest.py` | 文件上传接口 **mode** 支持 `fast` \| `fine` \| `memos`，调用 file_processing 后构造 RawEpisode 并 bulk 入图。 |
| 4 | `server/pyproject.toml` | 可选依赖 **mem-reader**：`chonkie>=1.0.7,<2.0.0`（与 MemOS mem-reader 一致）。 |
| 5 | `server/graph_service/auth/db.py` | SQLite 建表与 CRUD（users、api_keys）；DDL 见第四节。 |
| 6 | `server/graph_service/auth/auth.py` | API Key 生成与哈希；`get_current_user` / `get_current_user_optional`，从 X-API-Key 或 Bearer 取 key 并校验。 |
| 7 | `server/graph_service/routers/auth.py` | `POST /auth/register`：创建用户并返回 API Key（仅一次）。 |
| 8 | `server/graph_service/main.py` | 注册 auth router；lifespan 中 `init_db()`；可选 `AUTH_REQUIRED` 时对 ingest 使用 `get_current_user`。 |

### 5.2 启动与调用

- **安装（含 MemOS 风格分块）**：`cd server && uv sync`；若需 **memos** 模式：`uv sync --extra mem-reader`。
- **启动**：`uvicorn graph_service.main:app --reload --host 0.0.0.0 --port 8000`。首次运行会按 DDL 创建 SQLite 表（默认 `./data/graph_service.db`）。
- **注册用户并获 API Key**：`POST /auth/register` body `{"username": "myuser"}` → 返回 `user_id`、`api_key`（仅一次）。
- **提交文件（按 MemOS 分块）**：`POST /ingest/file` 或 `POST /submit/file`，Query **mode=memos**（或 fast/fine），Header `X-API-Key: <api_key>` 或 `Authorization: Bearer <api_key>`，Body 上传文件。
- **快速查看结果**：检索接口使用相同 `graphiti_id`；Neo4j Browser 查 Episodic/Entity；或看服务日志 “File ingest (bulk) completed … mode=memos”。

### 5.3 正确性说明

- ingest 类型/初始化问题已通过 `_get_graphiti()` 与类型注解修复。
- 文件处理：解析与 MemOS 一致（markitdown）；分块在 **memos** 模式下与 MemOS 一致（chonkie SentenceChunker）；fast/fine 沿用 graphiti_core，便于不装 chonkie 时使用。
- 用户与 API Key：鉴权方式与 MemOS 一致（Bearer/Token）；DDL 已给出 SQLite 与 MySQL，便于迁移或与 MemOS 用户体系对齐。
