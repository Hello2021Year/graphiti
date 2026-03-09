# User History & Auth Feature Summary

本文档记录本次需求的所有改动：邮箱验证码登录、MySQL 用户/会话存储、第三方大模型接口、用户多 Session 历史能力，以及鉴权 TODO。

---

## 1. 邮箱 + 验证码登录，MySQL 与 DDL

### 1.1 数据库

- **数据库**：MySQL，库名默认 `graphiti`（可通过 `MYSQL_DATABASE` 配置）。
- **DDL 位置**：`migration/sql/` 下两个脚本：
  - `001_user_and_auth.sql`：用户表、验证码表、refresh_token 表。
  - `002_sessions_and_messages.sql`：会话表、会话消息表。

### 1.2 表结构概要

| 表名 | 说明 |
|------|------|
| `users` | 用户：id, email, created_at, updated_at，email 唯一。 |
| `verification_codes` | 验证码（预留）：email, code, used, expires_at。当前登录未用此表，验证逻辑为 TODO。 |
| `refresh_tokens` | 刷新令牌：user_id, token, expires_at，用于后续刷新 access token（当前未实现刷新接口）。 |
| `sessions` | 用户会话：user_id, name, created_at, updated_at，一个用户可有多个 session。 |
| `session_messages` | 会话消息：session_id, role(user/assistant/system), content, created_at。 |

### 1.3 登录与 Token

- **验证码**：TODO，真实发送验证码未实现；当前**默认验证码为 `20250325`**（可通过 `DEFAULT_VERIFICATION_CODE` 配置）。
- **接口**：`POST /auth/login`  
  - Body: `{ "email": "user@example.com", "code": "20250325" }`  
  - 成功返回：`access_token`（JWT）、`refresh_token`（随机字符串、写入 `refresh_tokens` 表）、`expires_in`（秒）。
- **Token 用途**：Bearer 鉴权为 TODO，当前接口均不鉴权；登录仅用于拿到 token，后续可在此基础上加鉴权。

---

## 2. 鉴权（TODO）

- 当前**所有接口均不鉴权**，不在请求中校验 Bearer Token。
- 计划：后续在需要保护的接口上增加鉴权中间件或依赖项，从 JWT 解析 `user_id`。

---

## 3. 第三方大模型接口（UCloud）

- **配置**：使用环境变量 `UCLOUD_API_KEY`（必填）、可选 `UCLOUD_LLM_BASE_URL`、`UCLOUD_LLM_MODEL`。
- **流程**（与「保存用户历史」一起实现）：
  1. 用户发一条消息 → 先写入当前 session 的 `session_messages`（role=user）。
  2. 若配置了 Graphiti（app.state.graphiti），则调用 `add_memory_async(content=message, user_id)` 写入记忆。
  3. 调用 Graphiti 的 `search_async(query=message, user_id)` 获取用户记忆，拼进 system prompt。
  4. 将「记忆上下文 + 当前会话最近若干轮对话」拼成 messages，调用 UCloud 大模型接口（OpenAI 兼容的 chat/completions）。
  5. 将大模型回复写入 `session_messages`（role=assistant），并返回给客户端。

---

## 4. 用户历史与多 Session

- **设计参考**：多 Session、每 Session 多轮对话的存储方式参考了 [Zep legacy](https://github.com/getzep/zep/tree/main/legacy) 等实现：一个用户多个 session，每个 session 内按时间顺序存消息。
- **能力**：
  - **创建 Session**：`POST /sessions?user_id=1&name=会话名称`，返回新 session 信息。
  - **列举 Session**：`GET /sessions?user_id=1`，返回该用户所有 session 列表（id, name, created_at, updated_at）。
  - **查看某 Session 详情**：`GET /sessions/{session_id}?user_id=1`，返回该 session 的元信息 + 全部 `session_messages`（id, role, content, created_at）。
- **Chat 与 Session 绑定**：  
  `POST /chat` Body 可带 `session_id`（可选）、`user_id`、`message`、可选 `session_name`。  
  - 若不传 `session_id`，则自动创建新 session（使用 `session_name` 或默认 "New session"），并在该 session 下完成本轮对话与存储。

---

## 5. 代码与配置变更清单

| 类型 | 路径 | 说明 |
|------|------|------|
| DDL | `migration/sql/001_user_and_auth.sql` | users, verification_codes, refresh_tokens |
| DDL | `migration/sql/002_sessions_and_messages.sql` | sessions, session_messages |
| 配置 | `server/graph_service/config.py` | MySQL / JWT / 验证码默认值 / UCloud API |
| 依赖 | `server/pyproject.toml` | 新增 aiomysql, PyJWT, httpx |
| 数据库 | `server/graph_service/database.py` | MySQL 连接池（aiomysql）、init/close、get_conn |
| 认证 | `server/graph_service/services/auth_service.py` | 验证码校验（默认 20250325）、JWT 签发、refresh_token 入库 |
| 会话 | `server/graph_service/services/session_service.py` | sessions / session_messages 的创建、列表、详情、追加消息 |
| 大模型 | `server/graph_service/services/llm_service.py` | 调用 UCloud LLM（OpenAI 兼容 chat/completions） |
| 路由 | `server/graph_service/routers/auth.py` | POST /auth/login |
| 路由 | `server/graph_service/routers/chat.py` | POST /chat（消息入库、记忆检索、调 UCloud、回复入库） |
| 路由 | `server/graph_service/routers/sessions.py` | GET/POST /sessions、GET /sessions/{id} |
| DTO | `server/graph_service/dto/auth_dto.py` | LoginRequest / LoginResponse |
| DTO | `server/graph_service/dto/chat_dto.py` | ChatRequest / ChatResponse |
| DTO | `server/graph_service/dto/session_dto.py` | SessionSummary / MessageItem / SessionDetail |
| 入口 | `server/graph_service/main.py` | FastAPI app、lifespan 初始化/关闭 DB、挂载 auth/chat/sessions 路由 |

---

## 6. 环境变量（示例）

```bash
# MySQL
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=graphiti

# JWT
JWT_SECRET=your_secret
JWT_ACCESS_EXPIRE_SECONDS=3600
JWT_REFRESH_EXPIRE_DAYS=7

# 验证码（开发默认）
DEFAULT_VERIFICATION_CODE=20250325

# UCloud 大模型
UCLOUD_API_KEY=your_ucloud_api_key
UCLOUD_LLM_BASE_URL=https://api.ucloud.cn/llm/v1
UCLOUD_LLM_MODEL=gpt-4
```

---

## 7. 部署前需执行

1. 在 MySQL 中创建数据库（若不存在）：`CREATE DATABASE graphiti;`
2. 按顺序执行 DDL：  
   `mysql -u root -p graphiti < migration/sql/001_user_and_auth.sql`  
   `mysql -u root -p graphiti < migration/sql/002_sessions_and_messages.sql`
3. 配置好上述环境变量后启动服务（如 `uvicorn graph_service.main:app --reload`）。

以上改动均已输出到本文档（`user-history.md`）。
