# 动态标签报错与 DBMS 通知：原因、规避与可借鉴的 Issue

## 一、动态标签报错：情况、如何避免、为何出现

### 1.1 报错长什么样

- **Neo4j 报错**：`Neo.ClientError.Statement.SyntaxError: Setting labels or properties dynamically is not supported.`
- **问题语句**：`SET n:$(node.labels)`（或类似用参数当“标签名”的写法）

### 1.2 为什么会出现

- 在 Cypher/Neo4j 里：
  - **可以**用参数传**值**：如 `SET n.name = $name`、`MERGE (n:Entity {uuid: $uuid})`。
  - **不可以**用参数传**图结构**：**标签名**（如 `Entity`、`Person`）、关系类型、属性名等不能写成 `$param`，必须写在查询字符串里。
- graphiti_core 里 Neo4j 的 **bulk 写入**原先用一条 UNWIND 查询，对每个节点写 `SET n:$(node.labels)`，相当于“用参数拼标签”，触发了上述限制，所以 Neo4j 直接报语法错误。

因此：**出现是因为在 Cypher 里用参数去“动态”设置标签，而 Neo4j 不支持这种用法。**

### 1.3 如何避免（本仓库已做的修复）

- **不要**在 Cypher 里用 `SET n:$(node.labels)` 或任何“参数当标签名”的写法。
- 在本仓库的 **graphiti_core** 里已改为：
  - 对**每个节点**生成一条独立 Cypher，在**查询字符串里**把标签写死（如 `SET n:Entity` 或 `SET n:Entity:Person`），
  - 返回 `list[(query, params)]`，由 Neo4j driver 和 bulk_utils 逐条执行。
- 这样既满足“不同节点不同标签”，又不触碰“动态标签”语法，报错就不会再出现。

### 1.4 相关 GitHub Issue

- **[#1022](https://github.com/getzep/graphiti/issues/1022) Neo4j Label Setting Bug**：就是 `SET n:$(node.labels)` 导致的同一类错误，已由维护者修复。
- **[#659](https://github.com/getzep/graphiti/issues/659)**：见下文“可借鉴点”，是另一条线（APOC + 健壮性）。

---

## 二、Issue #659 的可借鉴之处

**链接**：[Bug: Ingestion fails with Cypher Error when using dynamic labels due to unsafe apoc.create.addLabels call #659](https://github.com/getzep/graphiti/issues/659)

### 2.1 在说什么

- 使用 **`apoc.create.addLabels`** 根据传入的 `labels` 给节点打标签时，若 `labels` 为 **null、空列表、或非字符串列表**，会直接抛 `CypherError`，整批写入失败。
- 根因：Cypher 里**无条件**调用 `CALL apoc.create.addLabels(n, node.labels)`，没有对“坏数据”做防护。

### 2.2 可借鉴的点

1. **对“动态标签”相关逻辑做健壮性处理**  
   - 若 graphiti 某路径用 APOC 的 `addLabels`，应对 `node.labels` 做判空、类型检查；  
   - 或像 #659 提议的：用 `FOREACH` 等写法，**仅在 `node.labels` 非空且合法时才调用** `apoc.create.addLabels`，避免单条坏数据拖垮整批。

2. **与“参数化标签”的区别**  
   - **#659**：讨论的是 **APOC 动态打标签** 时的**入参健壮性**（null/空/类型）。  
   - **本仓库遇到的**：是 **`SET n:$(node.labels)`** 这种**用参数当标签名**的 Cypher 语法限制。  
   - 本仓库采用的“按节点生成静态标签查询”的改法，**不依赖 APOC**，也避免了参数化标签，同时减少了 APOC 入参问题的影响面。

3. **建议**  
   - 若后续在 graphiti_core 里仍使用 `apoc.create.addLabels`，可参考 #659 的提议：对 `labels` 做判空与类型校验，或在 Cypher 里用条件执行（如 FOREACH），只在有效时才调用。

---

## 三、Issue #220、#289、#350：“Received notification from DBMS server” 可借鉴之处

### 3.1 #220：Getting warnings while doing data ingestion

**链接**：[Getting warnings while doing data ingestion #220](https://github.com/getzep/graphiti/issues/220)

- **现象**：  
  - 大量 `Received notification from DBMS server`，例如：**The provided property key is not in the database (the missing property name is: content)**（查询 Episodic 时）。  
  - 还有 **Connection reset by peer**、导入 30 个 chunk 约 20 分钟。
- **可借鉴**：  
  - 这类 WARNING 多数是 **RETURN 里引用了库里当前没有的属性**（例如旧数据、旧 schema 没有 `content`）。  
  - 先确认已对当前库执行 **`graphiti.build_indices_and_constraints()`**，并尽量用与当前 graphiti 版本匹配的 schema 写入数据。  
  - 若仍大量出现，可能是 **graphiti 版本升级后查询多了新字段，但库里老数据没有**，需要做数据迁移或接受“查询仍执行、仅部分属性为 null”的行为。

### 3.2 #289：Received notification from DBMS server（已关闭）

**链接**：[Received notification from DBMS server #289](https://github.com/getzep/graphiti/issues/289)

- **现象**：  
  - 同上，大量 **UnknownPropertyKeyWarning**：  
    - Episodic：缺 `content`、`source_description`、`source`、`entity_edges`；  
    - RELATES_TO：缺 `fact_embedding`、`episodes`。
- **可借鉴**：  
  - 维护者 @prasmussen15 会问：**是否在跑任何业务前执行过 `graphiti.build_indices_and_constraints()`**，以及 **使用的 Graphiti 版本**。  
  - 说明：**先建好索引/约束、再用当前版本写入数据**，能减少“查询里有的属性在库里不存在”的警告。  
  - 若库是旧版本写入的，**升级 graphiti 后**新查询会多出 `entity_edges`、`episodes`、`fact_embedding` 等，旧节点/边没有这些属性就会触发通知。  
  - **#289 已关闭**：按维护者指引（build_indices_and_constraints + 版本/使用方式）可处理。

### 3.3 #350：Received notification from DBMS server, and no searched result while data in Neo4j

**链接**：[Received notification from DBMS server, and no searched result while data in Neo4j #350](https://github.com/getzep/graphiti/issues/350)

- **现象**：  
  - 同样的 **UnknownPropertyKeyWarning**（缺 `content`、缺 `episodes` 等）；  
  - **数据已写入 Neo4j，但 search 结果为空**。
- **可借鉴**：  
  1. **WARNING 原因**：与 #289 一致，多为 **schema/版本不一致**（查询 RETURN 了当前库里没有的属性）。  
  2. **搜索为空**：  
     - 讨论里有人通过检查 **Entity 的 `name_embedding` 是否为空** 发现：节点存在但 **embedding 未写入**，导致向量搜索无结果。  
     - 做法：先查 `MATCH (n:Entity) WHERE n.name_embedding IS NOT NULL RETURN count(n)`；若为 0，说明需要让 graphiti 正常跑完 embedding 写入（或按 issue 里提到的办法手动补写 embedding）。  
  3. **建议**：  
     - 确保 **build_indices_and_constraints()** 在写入前执行；  
     - 写入后确认 **既有节点数，又有带 embedding 的节点**；  
     - 若仍无结果，再查是否 filter（如 group_id）、搜索配置（limit、min_score）过严。

### 3.4 小结：DBMS 通知与无结果的规避

| 情况 | 建议 |
|------|------|
| 大量 UnknownPropertyKeyWarning | 先执行 `build_indices_and_constraints()`；确认 graphiti 版本与写入数据的版本一致；若库是旧版本建的，考虑迁移或接受部分属性为 null。 |
| 搜索无结果但库里已有数据 | 检查 Entity/RELATES_TO 的 embedding 是否写入（如 `name_embedding`、`fact_embedding`）；确认 group_id、limit、min_score 等过滤条件合理。 |
| 使用 Neo4j 5.26+ | 与 #289、#350 环境一致，按上述步骤即可对照排查。 |

---

## 四、动态标签报错：快速对照

| 问题 | 原因 | 如何避免 |
|------|------|----------|
| `Setting labels or properties dynamically is not supported`，语句里出现 `SET n:$(node.labels)` | Neo4j 不支持用**参数**当**标签名**；Cypher 里标签必须写在查询字符串里。 | 不在 Cypher 里用 `SET n:$(...)` 写标签；本仓库已改为“按节点生成带静态标签的查询”逐条执行。 |
| 使用 APOC `apoc.create.addLabels` 时整批失败 | `labels` 为 null/空/非字符串列表时，APOC 会报错（#659）。 | 调用前校验 `labels`；或在 Cypher 里用条件执行（如 FOREACH），仅在有效时调用 addLabels。 |
| 无语法错误，但大量 “missing property name: content / episodes / fact_embedding / entity_edges” | 查询 RETURN 了当前库里不存在的属性（旧数据或旧 schema）。 | 先 `build_indices_and_constraints()`；用当前版本写入；或做数据迁移补齐新字段（#220、#289、#350）。 |

---

以上内容已写入 **`doc/question2.md`**，并已引用 [Issue #659](https://github.com/getzep/graphiti/issues/659)、[#220](https://github.com/getzep/graphiti/issues/220)、[#289](https://github.com/getzep/graphiti/issues/289)、[#350](https://github.com/getzep/graphiti/issues/350)。
