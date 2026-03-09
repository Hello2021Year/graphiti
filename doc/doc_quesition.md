# Server 改动说明与常见问题

## 1. 最开始的 Server 与当前实现的对比（Client 与 Lifespan）

### 1.1 对比总览

| 维度 | 最开始 / 原始实现 | 当前实现 |
|------|------------------|----------|
| **Lifespan 位置** | 只有 main 的 lifespan 里调用 `initialize_graphiti(settings)`，不保存 client；ingest 路由自带 `APIRouter(lifespan=lifespan)`，在 router 的 lifespan 里启动/停止 AsyncWorker | main 的 lifespan：创建并保存**一个** Graphiti client 到 `app.state.graphiti`，**在同一个 lifespan 里**启动和停止 AsyncWorker；ingest 路由**不再**带 lifespan |
| **Graphiti 客户端（普通请求）** | `get_graphiti` 为**按请求**创建：每次请求新建 ZepGraphiti，`yield` 给路由用，在 `finally` 里 `await client.close()`，即**请求结束即关闭** | `get_graphiti` 只做 `return request.app.state.graphiti`，**复用** lifespan 里创建的那一个 client，**不再**在请求结束时 close |
| **Graphiti 客户端（POST /messages 后台任务）** | 任务里用的是**请求作用域**的 `graphiti`（通过 `ZepGraphitiDep` 注入），请求先返回，client 被 close，后台任务再跑时就会 “Driver closed” | 任务里只用 **`async_worker.graphiti`**，由 worker 在 **`start()`** 里用 `create_graphiti(get_settings())` 创建的**独立、持久**的 client，与请求生命周期无关 |
| **Worker 是否真的跑起来** | Router 的 lifespan 在 FastAPI 里**不会**在 `include_router` 时执行，所以 worker **从未被启动**，队列无人消费；若改成“首次请求时启动”，仍会用到已关闭的请求 client → “Driver closed” | Worker 在 **main 的 lifespan** 里 `await async_worker.start()` / `await async_worker.stop()`，**一定会**随应用启停；worker 自带持久 client，不会因请求结束而关闭 |

### 1.2 Client 调用方式对比

**原始：**

- **main.py**  
  - `lifespan`: 只做 `await initialize_graphiti(settings)`（建索引用的临时 client，用后即丢，**没有** `app.state.graphiti`）。
- **zep_graphiti.py**  
  - `get_graphiti(settings)`: 每次请求 `client = ZepGraphiti(...)` → `yield client` → `finally: await client.close()`。  
  - 所有路由（包括 ingest）都通过 `ZepGraphitiDep` 拿到这个**仅在本请求内有效**的 client。
- **ingest.py**  
  - `add_messages` 把 `graphiti.add_episode(...)` 包成任务放进队列；任务里用的 `graphiti` 就是上面这个请求级 client。  
  - Worker 若在 router lifespan 启动（实际不会跑），或后来改成“首次 /messages 时启动”，任务执行时请求早已结束，client 已 close → **Driver closed**。

**当前：**

- **main.py**  
  - `lifespan`:  
    - `client = create_graphiti(settings)`，`await client.build_indices_and_constraints()`，`app.state.graphiti = client`；  
    - `await async_worker.start()`（worker 内部会再创建一个自己的 client）；  
    - `yield`；  
    - `await async_worker.stop()`，`await client.close()`。
- **zep_graphiti.py**  
  - `get_graphiti(request)`: 直接 `return request.app.state.graphiti`（**不**创建、**不**关闭）。  
  - 除 `/messages` 外的路由仍通过 `ZepGraphitiDep` 使用这个**共享** client。
- **ingest.py**  
  - `add_messages` **不再**注入 `ZepGraphitiDep`；任务里只调 **`async_worker.graphiti.add_episode(...)`**。  
  - `AsyncWorker.start()` 里执行 `self.graphiti = create_graphiti(get_settings())`，`stop()` 里 `await self.graphiti.close()`。  
  - 因此 **POST /messages 的后台任务只用 worker 自己的持久 client**，与请求和 `app.state.graphiti` 的生命周期解耦。

### 1.3 Lifespan 部分小结

- **原始**：只有 main 的 lifespan 做初始化；worker 的启停挂在** router lifespan** 上，而 FastAPI **不会**执行被 include 的 router 的 lifespan，所以 worker 实际上没启动；即使后来改成“懒启动”，用的仍是请求级 client，问题依旧。  
- **当前**：**所有** 启停都在 **main 的 app lifespan** 里完成（共享 client 的创建/关闭 + worker 的 start/stop）；ingest 路由不再带 lifespan，仅提供接口和 worker 逻辑。这样既保证 worker 一定随应用启停，又保证后台任务使用独立、持久的 Graphiti 客户端，避免 “Driver closed”。  
- 参考：[PR #1178](https://github.com/getzep/graphiti/pull/1178)（将 AsyncWorker 启停移到 app lifespan，并为 worker 提供独立持久 client）。

---

## 2. UNWIND 查询是什么？动态标签问题在 GitHub 上常见吗？

### 2.1 UNWIND 查询是什么

在 Cypher（Neo4j 的查询语言）里，**UNWIND** 把**一个列表变成多行**，便于对“一批数据”做同一条语句里的批量操作。

- 写法示例：`UNWIND $nodes AS node`  
  - `$nodes` 是参数，例如 `[{ uuid: "a", name: "A" }, { uuid: "b", name: "B" }]`。  
  - 执行后相当于有两“行”，每行一个 `node`（一个 map）。  
- 后面可以写：  
  - `MERGE (n:Entity {uuid: node.uuid})`  
  - `SET n.name = node.name, ...`  
  这样一条查询就能处理列表中所有节点，而不是在应用层循环多次请求。

在 graphiti_core 里，Neo4j 的 **bulk 写入**（例如 `add_nodes_and_edges_bulk`）原本就是用 **UNWIND $nodes AS node** 再配合 **SET n:$(node.labels)** 想一次性写入多个实体节点并给每个节点打上不同标签。

### 2.2 为何会报 “Setting labels or properties dynamically is not supported”

Neo4j 里：

- **可以**用参数传**值**：例如 `SET n.name = $name`、`MERGE (n:Entity {uuid: $uuid})`。  
- **不可以**用参数传**结构/标签名**：例如 **`SET n:$(node.labels)`** 这种“用参数拼出标签”的写法是**不被支持的**。  
标签、关系类型等属于“图结构”，必须写在查询字符串里，不能通过 `$...` 动态传入。所以一旦 graphiti_core 在 bulk 里用了 `SET n:$(node.labels)`，Neo4j 就会报：

`Neo.ClientError.Statement.SyntaxError: Setting labels or properties dynamically is not supported.`

### 2.3 在 graphiti_core 里做的三处修改（避免“动态标签”）

为在不改 Neo4j 语法的前提下继续支持“不同节点不同标签”的 bulk，在 **graphiti_core** 里做了三处修改：

1. **`graphiti_core/models/nodes/node_db_queries.py`**  
   - Neo4j 的 **`get_entity_node_save_bulk_query`** 不再返回“一条 UNWIND + `SET n:$(node.labels)`”的查询。  
   - 改为对**每个节点**生成一条独立 Cypher，在**查询字符串里**把标签写死（如 `SET n:Entity` 或 `SET n:Entity:Person`），并返回 **`list[(query, params)]`**，每条用对应的 `entity_data`（且去掉 `labels` 键，避免当属性写入）。

2. **`graphiti_core/driver/neo4j/operations/entity_node_ops.py`**  
   - **`save_bulk`** 中若拿到的是上面的 list，就**逐条**执行 `(query, params)`，而不再执行一条 UNWIND + 动态标签的查询。

3. **`graphiti_core/utils/bulk_utils.py`**  
   - 若 **`get_entity_node_save_bulk_query`** 返回的是 list，就按 list 逐条执行；否则保持原来的单条查询 + `nodes=nodes`，以兼容其他后端。

这样 Neo4j 侧不再出现“用参数设置标签”的语法，报错就会消失。

### 2.4 这个问题在 GitHub 上常见吗？

**常见，且已有专门 issue。**

- **Neo4j Label Setting Bug**：[Issue #1022](https://github.com/getzep/graphiti/issues/1022)  
  - 描述的就是 Neo4j 在设置多个标签时使用 **`SET n:$(node.labels)`**，导致  
    `Neo.ClientError.Statement.SyntaxError: Setting labels or properties dynamically is not supported.`  
  - 根因说明：Cypher 参数只能传值，不能传标签/关系类型等结构；并提到与 “Custom ontology #262” 的回归有关。  
  - 该 issue 在 2025-10-30 左右被关闭，由维护者修复。  

因此：**“动态标签”在 GitHub 上是一个被记录并修复过的问题**；你遇到的正是同一类错误，我们在本仓库的 graphiti_core 里用“按节点生成静态标签的 bulk”做了同样的修复思路。

---

## 3. `graphiti-core = { path = "..", editable = true }` 与“在该目录下重新”具体是什么意思？

### 3.1 这句话在说什么

- **`graphiti-core = { path = "..", editable = true }`**  
  这是在 **server 的依赖配置**里，把 **graphiti-core** 从“从 PyPI 安装的版本”改成“从**本地路径**安装的版本”。  
  - **path**：指定“包在哪里”。这里 `".."` 表示**上一级目录**（以 server 项目根为基准）。  
  - 在本仓库结构下，**server** 在 `graphiti/server/`，**上一级** `..` 就是 **`graphiti/`**（即包含 `graphiti_core/` 和 `pyproject.toml` 的仓库根目录），也就是 **graphiti-core 这个包所在的目录**。  
  - **editable = true**：以“可编辑”方式安装，即安装的是**指向该目录的链接**；你改 `graphiti_core/` 里的代码，**不用重新 pip/uv install**，下次跑 server 就会用最新代码（重启进程即可）。

- **“在该目录下重新”**  
  指的是：**在 server 所在目录**（即 `server/`）里，**重新执行一次依赖安装**（例如 `uv sync` 或 `pip install -e ".[dev]"`），让依赖解析器根据新的 `path` 和 `editable` 把本地的 graphiti-core 装进 server 的虚拟环境。  
  “重新”强调：改完 `pyproject.toml` 或 `uv.lock` 后，必须再跑一次安装命令，否则 server 仍会用旧的（例如 PyPI 的）graphiti-core。

### 3.2 在本仓库里的具体操作步骤

本仓库结构大致为：

```text
graphiti/                    # 仓库根，即 ".." 对 server 来说
├── graphiti_core/           # graphiti-core 的源码
├── pyproject.toml            # 定义 name = "graphiti-core"
├── server/
│   ├── pyproject.toml       # 这里要改依赖
│   ├── uv.lock
│   └── graph_service/
│       └── ...
```

1. **改 server 的依赖（只改 server 的 pyproject.toml）**  
   在 **`server/pyproject.toml`** 里，把原来从 PyPI 拉 graphiti-core 的那一行，改成用本地路径 + 可编辑，例如：

   ```toml
   dependencies = [
       "fastapi>=0.115.0",
       "graphiti-core @ file:///${PROJECT_ROOT}",  # 不行，要用 path
   ]
   ```

   更标准的写法是（uv/pip 都支持）：

   ```toml
   dependencies = [
       "fastapi>=0.115.0",
       "graphiti-core>=0.28.1",
   ]
   ```

   改成：

   ```toml
   dependencies = [
       "fastapi>=0.115.0",
       "graphiti-core @ file:///..",   # 某些工具
   ]
   ```

   或**推荐**（uv 的写法）：在 `[project]` 里保留 `"graphiti-core>=0.28.1"`，在文件末尾增加：

   ```toml
   [tool.uv.sources]
   graphiti-core = { path = "..", editable = true }
   ```

   `path = ".."` 是相对于 **server/pyproject.toml 所在目录**的路径，即上一级目录 = 本仓库根（含 graphiti_core 与根 pyproject.toml）。这样 uv 会优先用本地包而不是 PyPI。

   若不用 uv，只用 pip，可在 **server 目录**下执行：

   ```bash
   pip install -e ..
   ```

   这会把上一级目录（graphiti 根）以 editable 方式安装为 graphiti-core，覆盖同名的 PyPI 包。

2. **“在该目录下重新”执行安装**  
   - 进入 **server 目录**：  
     `cd server`（或 `cd /path/to/graphiti/server`）  
   - 重新安装依赖（二选一即可）：  
     - 使用 **uv**：  
       `uv sync` 或 `uv sync --extra dev`  
     - 使用 **pip**（若用 editable）：  
       `pip install -e ..`  
         然后再按需：  
       `pip install -r requirements.txt` 或 `pip install -e ".[dev]"`  

3. **验证**  
   - 在 server 的虚拟环境里：  
     `python -c "import graphiti_core; print(graphiti_core.__file__)"`  
   - 应看到路径指向**本仓库**下的 `graphiti_core` 目录，而不是 site-packages 里某个已发布的包。  

4. **之后**  
   - 修改 `graphiti_core/` 下的代码后，**只需重启 server 进程**（无需再 `uv sync` / `pip install`），就会用到最新逻辑。

### 3.3 路径按实际项目结构调整

- 若 server 不在 `graphiti/server/`，而是和 graphiti 仓库**平级**，例如：  
  `project/server/` 和 `project/graphiti/`，则在 **server 的 pyproject.toml** 里应写成：  
  `path = "../graphiti"`（或相对 server 项目根到 graphiti 根的实际相对路径）。  
- 若用绝对路径（不推荐，不利于别人克隆）：  
  `path = "/Users/xxx/graphiti"`。  
- **原则**：`path` 指向的目录里，必须有一个能安装成 **graphiti-core** 的包（即包含 `graphiti_core/` 和定义 `name = "graphiti-core"` 的 `pyproject.toml`）。

---

以上三部分分别回答了：  
1）最初 server 与当前在 client 与 lifespan 上的差异；  
2）UNWIND 是什么、动态标签报错原因、graphiti_core 的三处修改，以及该问题在 GitHub（如 #1022）上的情况；  
3）`graphiti-core = { path = "..", editable = true }` 和“在该目录下重新”的具体含义及在本仓库中的操作步骤。
