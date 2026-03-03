# Graphiti Server Quick Start

Default base URL: **http://localhost:8000** (override with `BASE_URL`). Start the server from `server/`: `uvicorn graph_service.main:app --reload`.

---

## 1. Build the graph (POST APIs)

Run the script (from repo root or `server/`):

```bash
BASE_URL=http://localhost:8000 ./server/scripts/build_graph.sh
```

Or call the APIs manually.

### POST `/healthcheck`

```bash
curl -s -X GET "http://localhost:8000/healthcheck"
```

### POST `/messages` (ingest conversation as episodes)

Messages are queued and processed asynchronously; each message becomes an Episodic node.

```bash
curl -s -X POST "http://localhost:8000/messages" \
  -H "Content-Type: application/json" \
  -d '{
    "group_id": "my-group",
    "messages": [
      {
        "content": "I am Bob, I work at Acme.",
        "role_type": "user",
        "role": "Bob",
        "timestamp": "2025-03-04T12:00:00.000Z",
        "source_description": "chat"
      }
    ]
  }'
```

### POST `/entity-node` (create entity node)

```bash
curl -s -X POST "http://localhost:8000/entity-node" \
  -H "Content-Type: application/json" \
  -d '{
    "uuid": "entity-bob-001",
    "group_id": "my-group",
    "name": "Bob",
    "summary": "User who works at Acme."
  }'
```

### POST `/clear` (optional – clear full graph and rebuild indices)

```bash
curl -s -X POST "http://localhost:8000/clear"
```

### DELETE `/entity-edge/{uuid}`

```bash
curl -s -X DELETE "http://localhost:8000/entity-edge/EDGE_UUID"
```

### DELETE `/group/{group_id}`

```bash
curl -s -X DELETE "http://localhost:8000/group/my-group"
```

### DELETE `/episode/{uuid}`

```bash
curl -s -X DELETE "http://localhost:8000/episode/EPISODE_UUID"
```

---

## 2. Get results (GET / POST retrieval)

### GET `/healthcheck`

```bash
curl -s "http://localhost:8000/healthcheck"
```

### GET `/entity-edge/{uuid}`

Get one entity edge (fact) by UUID.

```bash
curl -s "http://localhost:8000/entity-edge/YOUR_EDGE_UUID"
```

### GET `/episodes/{group_id}`

Get recent episodes for a group. Query params: `last_n` (required).

```bash
curl -s "http://localhost:8000/episodes/my-group?last_n=10"
```

### POST `/search`

Semantic/keyword search over facts (entity edges). Returns matching facts.

```bash
curl -s -X POST "http://localhost:8000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "group_ids": ["my-group"],
    "query": "Who works at Acme?",
    "max_facts": 10
  }'
```

### POST `/get-memory`

Build a query from conversation messages and return relevant facts.

```bash
curl -s -X POST "http://localhost:8000/get-memory" \
  -H "Content-Type: application/json" \
  -d '{
    "group_id": "my-group",
    "max_facts": 10,
    "center_node_uuid": null,
    "messages": [
      { "content": "What do we know about Alice?", "role_type": "user", "role": "User" }
    ]
  }'
```

---

## 3. Cypher queries (Neo4j)

Connect to Neo4j (e.g. Browser at `http://localhost:7474`) and run these in the `neo4j` database (or the one configured for the server).

### Schema overview

- **Nodes:** `Entity`, `Episodic`, `Community`, `Saga`
- **Relationships:** `RELATES_TO` (entity–entity fact), `MENTIONS` (episode–entity), `HAS_EPISODE`, `NEXT_EPISODE`, `HAS_MEMBER`

### List all entities in a group

```cypher
MATCH (n:Entity)
WHERE n.group_id = 'my-group'
RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary, n.created_at AS created_at
ORDER BY n.created_at DESC;
```

### List all episodes (Episodic) in a group

```cypher
MATCH (e:Episodic)
WHERE e.group_id = 'my-group'
RETURN e.uuid AS uuid, e.name AS name, e.content AS content, e.source AS source, e.valid_at AS valid_at, e.created_at AS created_at
ORDER BY e.valid_at DESC
LIMIT 50;
```

### Get one episode by UUID

```cypher
MATCH (e:Episodic {uuid: $uuid})
RETURN e.uuid AS uuid, e.name AS name, e.group_id AS group_id, e.created_at AS created_at,
       e.source AS source, e.source_description AS source_description, e.content AS content, e.valid_at AS valid_at;
```

### List entity–entity facts (RELATES_TO) in a group

```cypher
MATCH (a:Entity)-[e:RELATES_TO]->(b:Entity)
WHERE e.group_id = 'my-group'
RETURN e.uuid AS uuid, a.name AS source_name, b.name AS target_name, e.name AS edge_name, e.fact AS fact,
       e.created_at AS created_at, e.valid_at AS valid_at, e.expired_at AS expired_at
ORDER BY e.created_at DESC
LIMIT 50;
```

### Get one entity edge by UUID

```cypher
MATCH (a:Entity)-[e:RELATES_TO]->(b:Entity)
WHERE e.uuid = $uuid
RETURN e.uuid AS uuid, a.uuid AS source_node_uuid, b.uuid AS target_node_uuid,
       e.group_id AS group_id, e.name AS name, e.fact AS fact,
       e.created_at AS created_at, e.expired_at AS expired_at, e.valid_at AS valid_at, e.invalid_at AS invalid_at;
```

### Episodes that mention an entity

```cypher
MATCH (ep:Episodic)-[m:MENTIONS]->(n:Entity {uuid: $entity_uuid})
RETURN ep.uuid AS episode_uuid, ep.content AS content, ep.valid_at AS valid_at
ORDER BY ep.valid_at DESC;
```

### One-hop graph around an entity (entities and facts)

```cypher
MATCH (n:Entity {uuid: $entity_uuid})
OPTIONAL MATCH (n)-[e:RELATES_TO]->(other:Entity)
WHERE e.group_id = $group_id
RETURN n, e, other
LIMIT 100;
```

### Count nodes and edges by group

```cypher
MATCH (n)
WHERE n.group_id = 'my-group' AND (n:Entity OR n:Episodic OR n:Community)
WITH labels(n)[0] AS label, count(n) AS cnt
RETURN label, cnt;

MATCH ()-[e:RELATES_TO]->()
WHERE e.group_id = 'my-group'
RETURN count(e) AS relation_count;
```

### Fulltext search on episode content (Neo4j 5.x)

After the server has created the fulltext index `episode_content`:

```cypher
CALL db.index.fulltext.queryNodes('episode_content', 'Acme')
YIELD node, score
WHERE node:Episodic AND node.group_id = 'my-group'
RETURN node.uuid AS uuid, node.content AS content, score
ORDER BY score DESC
LIMIT 10;
```

---

## 4. Build script reference

The script `server/scripts/build_graph.sh` runs, in order:

1. `GET /healthcheck`
2. (Optional) `POST /clear` – commented out by default
3. `POST /messages` – one conversation with two messages
4. `POST /entity-node` – two entities (Alice, Acme Corp)

Environment variables:

- `BASE_URL` – default `http://localhost:8000`
- `GROUP_ID` – default `quick-start-group`

Example:

```bash
BASE_URL=http://127.0.0.1:8000 GROUP_ID=test-group ./server/scripts/build_graph.sh
```

After running the script, wait a few seconds for message processing, then use the GET or Cypher examples above to inspect the graph.
