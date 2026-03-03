#!/usr/bin/env bash
# Build a knowledge graph via the Graphiti server API.
# Default: http://localhost:8000 (override with BASE_URL).
# Requires: server running (e.g. uvicorn graph_service.main:app --reload)

set -e
BASE_URL="${BASE_URL:-http://localhost:8000}"
GROUP_ID="${GROUP_ID:-quick-start-group}"

echo "Using BASE_URL=$BASE_URL GROUP_ID=$GROUP_ID"

# 1. Health check
curl -s -X GET "$BASE_URL/healthcheck" | jq .

# 2. (Optional) Clear existing graph for a fresh start
# curl -s -X POST "$BASE_URL/clear" | jq .

# 3. Add messages (ingest conversation as episodes; processed asynchronously)
curl -s -X POST "$BASE_URL/messages" \
  -H "Content-Type: application/json" \
  -d "{
    \"group_id\": \"$GROUP_ID\",
    \"messages\": [
      {
        \"content\": \"My name is Alice and I work at Acme.\",
        \"role_type\": \"user\",
        \"role\": \"Alice\",
        \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%S.000Z)\",
        \"source_description\": \"chat\"
      },
      {
        \"content\": \"Alice mentioned she works at Acme Corp.\",
        \"role_type\": \"assistant\",
        \"role\": \"Bot\",
        \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%S.000Z)\",
        \"source_description\": \"chat\"
      }
    ]
  }" | jq .

# 4. Add entity nodes (sync)
curl -s -X POST "$BASE_URL/entity-node" \
  -H "Content-Type: application/json" \
  -d "{
    \"uuid\": \"entity-alice-001\",
    \"group_id\": \"$GROUP_ID\",
    \"name\": \"Alice\",
    \"summary\": \"User who works at Acme.\"
  }" | jq .

curl -s -X POST "$BASE_URL/entity-node" \
  -H "Content-Type: application/json" \
  -d "{
    \"uuid\": \"entity-acme-001\",
    \"group_id\": \"$GROUP_ID\",
    \"name\": \"Acme Corp\",
    \"summary\": \"Company where Alice works.\"
  }" | jq .

echo "Build requests sent. Wait a few seconds for /messages processing, then run GET requests or Cypher."
