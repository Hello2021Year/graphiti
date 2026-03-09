# Graphiti 检索结果封装与 Context 说明

本文档说明 Graphiti 对检索返回结果的封装方式、context 的生成逻辑，以及查询结果如何被组合与合并。

---

## 1. 返回结果的封装（核心库）

### 1.1 统一结果类型：`SearchResults`

检索的**唯一标准返回类型**是 `graphiti_core.search.search_config.SearchResults`，定义在 `graphiti_core/search/search_config.py`：

```python
class SearchResults(BaseModel):
    edges: list[EntityEdge] = Field(default_factory=list)
    edge_reranker_scores: list[float] = Field(default_factory=list)
    nodes: list[EntityNode] = Field(default_factory=list)
    node_reranker_scores: list[float] = Field(default_factory=list)
    episodes: list[EpisodicNode] = Field(default_factory=list)
    episode_reranker_scores: list[float] = Field(default_factory=list)
    communities: list[CommunityNode] = Field(default_factory=list)
    community_reranker_scores: list[float] = Field(default_factory=list)
```

- **四类图元素**：边（facts）、实体节点、情节节点、社区节点；每类都配有对应的 **reranker 分数** 列表，与结果一一对应。
- **来源**：`graphiti_core/search/search.py` 中的 `search()` 会并行执行 edge / node / episode / community 四路检索，每路返回 `(list, scores)`，最后组装成上述一个 `SearchResults` 实例并返回。

### 1.2 面向 LLM 的 Context 字符串

将 `SearchResults` 转成「可直接塞进 LLM 的 context」的逻辑在 `graphiti_core/search/search_helpers.py` 的 **`search_results_to_context_string(search_results: SearchResults) -> str`**。

**实现要点：**

1. **按类型提取并序列化为 JSON 片段**  
   - **Facts (edges)**：`{ fact, valid_at, invalid_at }`  
   - **Entities (nodes)**：`{ entity_name, summary }`  
   - **Episodes**：`{ source_description, content }`  
   - **Communities**：`{ community_name, summary }`  

2. **序列化方式**  
   使用 `graphiti_core.prompts.prompt_helpers.to_prompt_json()` 做 JSON 序列化（默认不转义非 ASCII，便于多语言）。

3. **最终格式**  
   一个带 XML 风格标签的字符串，内含四块：`<FACTS>`、`<ENTITIES>`、`<EPISODES>`、`<COMMUNITIES>`，并附带简短说明（如 facts 的 valid_at/invalid_at 含义、communities 表示实体簇等）。

**典型用法**：上层拿到 `SearchResults` 后，若需要给 LLM 做 RAG，可调用：

```python
from graphiti_core.search.search_helpers import search_results_to_context_string
context_string = search_results_to_context_string(results)
# 将 context_string 填入 prompt 作为 context
```

### 1.3 与 Server / 其他封装的关系

- **核心库**  
  - 高级 API：`graphiti.search_()` 返回完整的 `SearchResults`（含 edges/nodes/episodes/communities 及分数）。  
  - 简单 API：`graphiti.search()` 只返回 `list[EntityEdge]`（即 `SearchResults.edges`），不包含 nodes/episodes/communities，也不包含 context 字符串。

- **Graph Service (server)**  
  - `POST /search`、`POST /get-memory` 等使用的是 `graphiti.search()`，因此只拿到 edges。  
  - Server 将每条 `EntityEdge` 转成 DTO `FactResult`（uuid, name, fact, valid_at, invalid_at, created_at, expired_at），再封装成 `SearchResults(facts=facts)`（此处的 `SearchResults` 是 **server 的 DTO**，仅含 `facts: list[FactResult]`，与 core 的 `SearchResults` 不同）。  
  - 因此：**当前 server 不返回 nodes/episodes/communities，也不返回 core 的 context 字符串**；若要在 server 层提供「context 字符串」，需要先调用返回完整 `SearchResults` 的 API（例如 `search_()`），再在 server 里调用 `search_results_to_context_string()` 并放入响应。

---

## 2. Context 部分的详细分析

### 2.1 Context 的语义与用途

- **FACTS**：实体间关系（边），带时间范围（valid_at / invalid_at），用于回答「谁在何时做了什么/与谁有什么关系」。
- **ENTITIES**：实体摘要，用于快速理解「有哪些人/组织/概念」。
- **EPISODES**：原始情节内容与来源描述，用于引用对话、文档等原文。
- **COMMUNITIES**：社区/簇的摘要，表示「紧密相关的一团实体」，用于高层次主题归纳。

设计意图是：把检索到的图结构信息转成**一段可读的、带结构的文本**，方便作为 LLM 的 system/user context，而不需要模型理解图本身。

### 2.2 各块字段与来源

| 块 | 字段 | 来源类型 | 说明 |
|----|------|----------|------|
| FACTS | fact, valid_at, invalid_at | EntityEdge | 边上的事实文本与双时间戳 |
| ENTITIES | entity_name, summary | EntityNode | 实体名与摘要（无 embedding） |
| EPISODES | source_description, content | EpisodicNode | 情节来源描述与正文 |
| COMMUNITIES | community_name, summary | CommunityNode | 社区名与摘要 |

`search_results_to_context_string` 中**不**包含任何 reranker 分数，也不包含 UUID 等内部标识；面向的是「给模型看的语义内容」。

### 2.3 扩展与定制

- 若需在 context 中增加字段（例如实体属性、episode 时间戳），只需在 `search_helpers.py` 中扩展对应的 `*_json` 列表与模板。  
- 若需不同语言或格式的说明文字，可修改同一函数中的 `context_string` 模板。  
- 若需按分数过滤或截断再生成 context，应在调用 `search_results_to_context_string` 之前对 `SearchResults` 做切片或过滤（例如只保留前 N 条 edges/nodes）。

---

## 3. 查询结果的组合方式

### 3.1 单次检索内部的组合（单 group、单 query）

在 `graphiti_core/search/search.py` 中，一次 `search()` 调用会：

1. **并行执行四路检索**  
   `edge_search`、`node_search`、`episode_search`、`community_search` 通过 `semaphore_gather` 并发执行，每路返回 `(items, scores)`。

2. **每路内部：多方法 → 合并 → 重排**  
   - **多方法**：例如 edge 支持 bm25、cosine_similarity、bfs；node 类似；episode 仅 bm25；community 支持 bm25 + cosine。  
   - 各方法各自拉取候选（如 2×limit 条），得到多份列表。  
   - **合并与重排**：通过配置的 reranker（如 RRF、MMR、cross_encoder、node_distance、episode_mentions 等）对多份列表做融合与排序，得到最终有序的 `(items, scores)`。  
   - 最终每路截断到 `limit` 条后，填入 `SearchResults` 的对应字段。

3. **组装**  
   四路的 `(items, scores)` 直接写入同一个 `SearchResults` 的 8 个列表字段，**不做跨类型**的再排序或去重；即「边、节点、情节、社区」是分别排序、分别截断后再拼在一个结构里。

### 3.2 多 group_id 下的结果合并（FalkorDB）

当使用 FalkorDB 且传入**多个 group_ids** 时，`graphiti_core.decorators.handle_multiple_group_ids` 会：

1. 对每个 group_id 单独执行被装饰的方法（如 `search_()`），每次传入 `group_ids=[gid]` 并使用对应 database 的 driver clone。  
2. 得到多个 `SearchResults`。  
3. 使用 **`SearchResults.merge(results_list)`** 合并为一个 `SearchResults`。

**`SearchResults.merge()` 的实现**（`search_config.py`）：  
对 `results_list` 中每个 `SearchResults`，将其中 8 个列表**按顺序 extend** 到同一个合并对象中（edges、edge_reranker_scores、nodes、node_reranker_scores、episodes、episode_reranker_scores、communities、community_reranker_scores）。  
即：**简单列表拼接，不做跨 group 的重新排序或去重**；顺序为「先 group A 的全部，再 group B 的全部，…」。

### 3.3 小结：结果组合的两层

| 层级 | 行为 |
|------|------|
| **单次 search() 内部** | 四路检索并行 → 每路多方法候选 → 每路用 reranker 合并排序 → 截断 → 填入 SearchResults 的 8 个列表。 |
| **多 group_ids（FalkorDB）** | 每 group 一个 SearchResults → 用 `SearchResults.merge()` 按列表 extend 合并为一个 SearchResults。 |

因此：  
- **Context 字符串**来自「单次或合并后的一个 `SearchResults`」的完整内容；  
- **查询结果的组合** = 每路内部的「多方法 + reranker」+ 多 group 时的「merge 拼接」。  
若需要「跨 group 或跨类型」的全局重排，需在应用层在拿到 `SearchResults` 后再做二次排序或过滤。

---

## 4. 相关代码位置速查

| 内容 | 路径 |
|------|------|
| SearchResults 定义与 merge | `graphiti_core/search/search_config.py` |
| search_results_to_context_string | `graphiti_core/search/search_helpers.py` |
| to_prompt_json | `graphiti_core/prompts/prompt_helpers.py` |
| 单次 search 流程与四路组装 | `graphiti_core/search/search.py`（search、edge_search、node_search、episode_search、community_search） |
| 多 group_ids 合并 | `graphiti_core/decorators.py`（handle_multiple_group_ids） |
| 简单 search 只返回 edges | `graphiti_core/graphiti.py`（search() 使用 search_config.limit，取 .edges） |
| Server 将 edge 转为 FactResult | `server/graph_service/zep_graphiti.py`（get_fact_result_from_edge）、`server/graph_service/dto/retrieve.py`（FactResult, SearchResults） |
