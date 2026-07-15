#!/usr/bin/env bash
# Container entrypoint for the Lucena app image.
#
# The backend's __main__ binds 127.0.0.1 (dev default), which is unreachable
# from outside the container. We launch serve() explicitly with host=$LUCENA_HOST
# (0.0.0.0 in the image) so the published port works — no backend code change.
set -euo pipefail

: "${LUCENA_HOST:=0.0.0.0}"
: "${LUCENA_BACKEND_PORT:=8766}"
: "${LUCENA_HOME:=/data}"

# --- wait for Postgres (the backend auto-creates its schema on first connect,
#     but it needs the server reachable and the database to exist first) -------
if [ -n "${LUCENA_PG_DSN:-}" ]; then
  echo "lucena: waiting for Postgres…"
  for i in $(seq 1 60); do
    if python -c "import os,psycopg; psycopg.connect(os.environ['LUCENA_PG_DSN']).close()" 2>/dev/null; then
      echo "lucena: Postgres reachable."
      break
    fi
    [ "$i" = "60" ] && { echo "lucena: Postgres not reachable after 60s — check LUCENA_PG_DSN"; exit 1; }
    sleep 1
  done
fi

if [ -z "${GEMINI_API_KEY:-}${GOOGLE_API_KEY:-}" ]; then
  echo "lucena: WARN — no GEMINI_API_KEY/GOOGLE_API_KEY set; the server runs but coaching turns fail at the LLM call."
fi

mkdir -p "$LUCENA_HOME"

echo "lucena: backend → ${LUCENA_HOST}:${LUCENA_BACKEND_PORT}  (stockfish=${LUCENA_STOCKFISH:-stockfish}, maia=${LUCENA_MAIA:+on})"
exec python -c "import os; from lucena_backend.httpserver import serve; \
serve(home=os.environ['LUCENA_HOME'], host=os.environ['LUCENA_HOST'], port=int(os.environ['LUCENA_BACKEND_PORT']))"
