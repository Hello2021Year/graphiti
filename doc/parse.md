# MemOS Parsers 与文件上传构建服务：嵌入评估与修改点

## 一、MemOS Parsers 代码概览

参考：[MemOS/src/memos/parsers](https://github.com/MemTensor/MemOS/tree/main/src/memos/parsers)

| 文件 | 作用 |
|------|------|
| `base.py` | 抽象基类 `BaseParser`：`parse(file_path: str) -> str` |
| `markitdown.py` | `MarkItDownParser`：用 [Microsoft MarkItDown](https://github.com/microsoft/markitdown) 将文件转为 Markdown 文本 |
| `factory.py` | `ParserFactory`：按配置创建 parser（当前 backend 仅 `markitdown`） |

**依赖链**：

- `memos.configs.parser`：`BaseParserConfig`、`MarkItDownParserConfig`、`ParserConfigFactory`
- `memos.configs.base`：`BaseConfig`
- `memos.memos_tools.singleton`：`singleton_factory`
- `memos.dependency`：`require_python_package`（按需安装 `markitdown[all]`）
- `memos.log`：`get_logger`

**核心能力**：给定本地 `file_path`，返回可读的 **Markdown 文本**，便于后续做 RAG/图谱构建。

---

## 二、是否可以直接嵌入当前程序并提供文件上传构建服务

### 2.1 结论概览

| 问题 | 结论 |
|------|------|
| 能否嵌入并“提供服务”？ | **可以**：在 **server** 层提供“文件上传 → 解析为文本 → 调用现有 ingest”即可。 |
| 是否放进 graphiti_core？ | **不建议**。Core 只应处理“文本/结构化输入 → 图谱”，不负责文件格式与 I/O。 |
| 是否直接依赖整包 MemOS？ | **可选**。更推荐在 server 中只依赖 **markitdown**，自写一层薄解析接口，避免引入 MemOS 的 config/singleton/log 体系。 |

### 2.2 为何不建议放进 graphiti_core

- **职责边界**：graphiti_core 的入口是 `add_episode(episode_body: str, ...)` / `add_episode_bulk(bulk_episodes)`，输入是 **已有文本** 或 **RawEpisode**，不涉及“文件类型、上传、临时目录”。
- **依赖与复杂度**：MemOS 的 parser 依赖一整套 memos config/base、singleton、dependency、log。若放进 core，会：
  - 把“文件解析”和“图谱构建”绑在一起，不利于 core 被其他环境复用（如无 HTTP、无文件的 CLI/批处理）。
  - 增加 core 的依赖和配置面。
- **可替换性**：解析实现（markitdown / 其他库）更适合在 **应用层** 按需切换，而不是写死在 core。

因此：**解析与文件上传放在 server，core 保持“只吃文本”不变。**

### 2.3 如何提供“文件上传 + 构建”服务

- **在 server 增加**：
  1. **文件上传接口**：例如 `POST /ingest/file` 或 `POST /files/upload`，接收 `multipart/form-data` 文件。
  2. **解析步骤**：将上传文件写到临时路径，用“解析器”得到 `str`（可直接用 [markitdown](https://github.com/microsoft/markitdown) 实现，或封装 MemOS 的 `MarkItDownParser`）。
  3. **构建步骤**：将得到的文本交给现有 ingest 流程：
     - 短文本：一次 `add_episode(..., episode_body=text, source=EpisodeType.text, ...)`。
     - 长文本：先按需分块（可复用或参考 `graphiti_core.utils.content_chunking`），再对每块调用 `add_episode` 或使用 `add_episode_bulk`。

这样即可在**不修改 graphiti_core** 的前提下，提供“上传文件 → 解析 → 构建图谱”的完整服务。

---

## 三、修改点汇总：放在 server 而非 graphiti_core

所有与“文件解析、上传、构建入口”相关的改动都只在 **server** 完成，**graphiti_core 无需改动**。

### 3.1 方案 A：最小依赖（推荐）—— 仅用 markitdown

**思路**：不依赖 MemOS，在 server 中只依赖 `markitdown`，自写一层薄解析接口。

| 修改点 | 位置 | 说明 |
|--------|------|------|
| 依赖 | `server/pyproject.toml` | 增加可选依赖：`markitdown[all]`（或 `markitdown` 按需）。 |
| 解析模块 | `server/graph_service/parsers/`（新建） | 例如 `parser.py`：提供 `parse_file(file_path: str) -> str`，内部用 `MarkItDown().convert(file_path).text_content`；可再按后缀或 content-type 选择是否只允许部分类型。 |
| 上传 + 构建端点 | `server/graph_service/routers/ingest.py` 或新建 `routers/files.py` | 接收 `UploadFile`，写入临时文件，调用 `parse_file`，再根据长度决定单次 `add_episode` 或分块后 `add_episode` / `add_episode_bulk`；如需异步队列可复用现有 `async_worker` 入队。 |
| DTO | `server/graph_service/dto/ingest.py` 或新 dto | 可选：描述“文件上传”的请求/响应（如 `group_id`、`source_description`、是否分块等）。 |
| 配置 | `server/graph_service/config.py` | 可选：如允许的扩展名、最大文件大小、临时目录等。 |

**特点**：实现快、依赖少、不引入 MemOS 体系；与 MemOS 的“能力”等价（都是文件 → Markdown 文本）。

### 3.2 方案 B：复用 MemOS 的 Parser 体系

**思路**：在 server 中把 MemOS 作为**可选依赖**，使用其 `ParserFactory` + `MarkItDownParser`。

| 修改点 | 位置 | 说明 |
|--------|------|------|
| 依赖 | `server/pyproject.toml` | 增加可选依赖：`memos`（或 MemOS 的包名），并保证其依赖的 `markitdown` 可用。 |
| 解析调用 | `server/graph_service/parsers/` 或 `routers/` | 使用 MemOS 的 `ParserConfigFactory` + `ParserFactory.from_config(...)` 得到 `BaseParser`，再调用 `parser.parse(file_path)`。需适配 MemOS 的 config 模型（如从 server 的 `config.py` 或环境变量构造）。 |
| 上传 + 构建端点 | 同方案 A | 与方案 A 一致：上传 → 临时文件 → `parser.parse(path)` → `add_episode` / 分块后 bulk。 |

**特点**：可沿用 MemOS 的多 backend 设计（若后续他们增加更多 parser）；代价是引入 MemOS 的 config/singleton/log 等，需在 server 内做适配。

---

## 四、推荐落地方案（方案 A）的步骤摘要

1. **server/pyproject.toml**  
   - 添加：`markitdown[all]`（或按需的 `markitdown`）。

2. **server/graph_service/parsers/**（新建）  
   - `parser.py`：实现 `parse_file(file_path: str) -> str`，内部使用 `MarkItDown`；可加简单错误处理与日志。  
   - 可选：按后缀限制允许的类型（如 `.md`、`.pdf`、`.docx` 等，以 markitdown 支持为准）。

3. **server/graph_service/routers/ingest.py**（或新建 `routers/files.py`）  
   - 新增端点，例如 `POST /ingest/file`：  
     - 接收 `file: UploadFile`，以及可选 `group_id`、`source_description` 等。  
     - 将 `file` 写入临时目录，得到 `file_path`。  
     - 调用 `parse_file(file_path)` 得到 `text`。  
     - 若需异步：将“对 text 调用 add_episode（或分块后 add_episode）”封装为任务，放入现有 `async_worker.queue`（与 `/messages` 一致）；若同步：直接在当前请求中调用 `add_episode`。  
     - 清理临时文件；返回 202 或 201 及简要结果。

4. **graphiti_core**  
   - **无需修改**：仍只接收 `episode_body: str` 与现有参数。

5. **文档**  
   - 在 `doc/quick_start.md` 或 API 说明中补充：文件上传构建的用法（如 curl/示例请求）。

---

## 五、总结表

| 项目 | 说明 |
|------|------|
| MemOS parsers 是否可直接嵌入？ | 可以，但**仅在 server 层**嵌入；不在 graphiti_core 嵌入。 |
| 是否在 graphiti_core 改代码？ | **否**。Core 保持“只吃文本”，不处理文件与解析。 |
| 是否在 server 改代码？ | **是**。新增解析模块 + 上传端点 + 可选 DTO/配置。 |
| 推荐实现方式 | 方案 A：server 仅依赖 **markitdown**，自写 `parse_file` 与上传接口，复用现有 `add_episode` / worker。 |
| 可选实现方式 | 方案 B：server 可选依赖 MemOS，用其 ParserFactory + MarkItDownParser，上传与构建流程同方案 A。 |

这样即可在不改动 graphiti_core 的前提下，用 MemOS 的“思路”（文件 → Markdown → 图谱）在 server 提供完整的文件上传构建服务，并明确所有修改点均在 **server** 下完成。

---

## 六、MemOS 其他依赖说明（当前实现无需 MemOS 整包）

参考 [MemOS/src](https://github.com/MemTensor/MemOS/tree/main/src)：MemOS 除 `memos/parsers` 外还有 `memos/configs`、`memos/memos_tools`、`memos/dependency`、`memos/log` 等。**当前实现没有依赖 MemOS 仓库**，只依赖 [markitdown](https://github.com/microsoft/markitdown) 做「文件 → Markdown 文本」的解析，因此**没有其他 MemOS 依赖**。若将来要接 MemOS 的 ParserFactory 等，再按 parse.md 方案 B 引入 memos 包即可。

---

## 七、解析成“消息”并批量入图（已实现）

**思路**：文件先转成 Markdown 字符串（`parse_file`），再按**文本分块**变成多条“消息”，每条对应一个 episode，最后用 **add_episode_bulk** 一次性写入图，比逐条 add_episode 更快建图。

**实现要点**：

1. **分块**：使用 graphiti_core 的 `chunk_text_content(text)`（按段落/句子边界、可配置 chunk_size/overlap），得到 `list[str]`。
2. **构造 RawEpisode**：每个 chunk 对应一个 `RawEpisode(name=f"{filename}#{i}", content=chunk, source_description=..., source=EpisodeType.text, reference_time=now)`。
3. **批量写入**：`await graphiti.add_episode_bulk(raw_episodes, group_id=graphiti_id)`。
4. **接口行为**：  
   - **POST /ingest/file**、**POST /submit/file**（提交文件）均支持查询参数 **use_bulk**（默认 true）：  
     - `use_bulk=true`：先 chunk，再 `add_episode_bulk`，快速建图。  
     - `use_bulk=false`：整份文件作为一条 episode，单次 `add_episode`。

这样既能把“文件解析成多条消息”，又能按需选用 message 式单条写入或 bulk 批量写入，与现有框架（worker、graphiti_id、EpisodeType）一致。

---

## 八、已完成的修改过程（与现有框架集成）

| 步骤 | 位置 | 说明 |
|------|------|------|
| 1 | `server/pyproject.toml` | 增加依赖 `markitdown[all]`。 |
| 2 | `server/graph_service/parsers/` | 新建 `parser.py`、`__init__.py`，实现 `parse_file(file_path) -> str`（仅用 markitdown，无 MemOS）。 |
| 3 | `server/graph_service/dto/ingest.py` | 新增 `FileIngestResponse`（message, success, filename, graphiti_id）。 |
| 4 | `server/graph_service/routers/ingest.py` | ① 新增 **POST /ingest/file**、**POST /submit/file**（提交文件接口），参数：file, graphiti_id, source_description, use_bulk；② 后台任务：parse_file → 若 use_bulk 则 chunk_text_content → 构造 RawEpisode 列表 → add_episode_bulk，否则 add_episode；③ 与现有 async_worker、graphiti_id、EpisodeType 集成。 |
| 5 | graphiti_core | **无修改**。仅使用其公开接口：add_episode、add_episode_bulk、chunk_text_content、RawEpisode、utc_now。 |

---

## 九、如何启动、调用接口与快速查看结果

### 9.1 启动服务

在项目根目录或 server 目录下安装依赖并启动：

```bash
# 在 server 目录
cd server
uv sync
uvicorn graph_service.main:app --reload --host 0.0.0.0 --port 8000
```

或使用 Makefile（若存在）：

```bash
cd server && make run
```

确保环境变量已配置（如 `.env`）：`OPENAI_API_KEY`、`NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` 等。Worker 在 app lifespan 中启动，会随服务一起就绪。

### 9.2 调用“提交文件”接口

**方式一：Swagger UI**

1. 打开浏览器访问：`http://localhost:8000/docs`。
2. 找到 **POST /ingest/file** 或 **POST /submit/file**（提交文件）。
3. 点击 “Try it out”，选择 **file**，填写可选参数 **graphiti_id**、**source_description**、**use_bulk**（默认 true 表示分块批量入图）。
4. 点击 “Execute”，返回 202 表示已加入处理队列。

**方式二：curl**

```bash
# 提交文件，使用默认 bulk 建图，并指定 graphiti_id
curl -X POST "http://localhost:8000/ingest/file?graphiti_id=my-graph" \
  -F "file=@/path/to/your/document.pdf" \
  -F "source_description=My Document"

# 或使用 /submit/file（同上）
curl -X POST "http://localhost:8000/submit/file?graphiti_id=my-graph&use_bulk=true" \
  -F "file=@/path/to/your/document.pdf"
```

### 9.3 快速查看结果

1. **检索接口**：调用现有检索 API（如 `GET /memory`、search 等），传入相同的 **graphiti_id**（即 group_id）即可查询刚写入的图谱内容。
2. **Neo4j 图库**：若使用 Neo4j，打开 Neo4j Browser，对应用户配置的库（如 `neo4j` 或 graphiti_id 对应的 database），执行 Cypher 查询，例如：
   - `MATCH (e:Episodic) RETURN e.name, e.content LIMIT 20`
   - `MATCH (n:Entity) RETURN n.name LIMIT 20`
3. **日志**：服务端日志会输出 “File ingest (bulk) completed: … -> N episodes”，可确认文件已分块并批量写入。
