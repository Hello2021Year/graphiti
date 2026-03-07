#!/usr/bin/env bash
# Run Graphiti server with gunicorn (ASGI via uvicorn worker).
# Run from server/: ./scripts/run_gunicorn.sh
# Override: BIND=0.0.0.0:8000 WORKERS=2 ./scripts/run_gunicorn.sh

set -e
cd "$(dirname "$0")/.."
BIND="${BIND:-0.0.0.0:8000}"
WORKERS="${WORKERS:-1}"

exec uv run gunicorn graph_service.main:app \
  -k uvicorn.workers.UvicornWorker \
  -b "$BIND" \
  -w "$WORKERS" \
  "$@"
