#!/usr/bin/env bash
# Bring up the Lucena dev stack: Postgres + engine (gRPC) + backend (WS/REST).
#
#   ./serve.sh          start everything (idempotent)
#   ./serve.sh stop     stop engine + backend (Postgres left running)
#   ./serve.sh status   show what's up
#   ./serve.sh logs     tail the engine + backend logs
#
# GEMINI_API_KEY is inherited from your environment (it's in ~/.zshrc); the backend needs it
# for real coaching turns. Override ports/paths via the LUCENA_* env vars below.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/backend/.venv/bin/python"
RUN="$ROOT/.run"; LOGS="$RUN/logs"
ENGINE_PID="$RUN/engine.pid"; BACKEND_PID="$RUN/backend.pid"

: "${LUCENA_STOCKFISH:=$(command -v stockfish || true)}"
# Maia (human-move predictor) — poisoned-line detection needs it. Auto-point at the local venv+wrapper.
if [ -z "${LUCENA_MAIA:-}" ] && [ -x "$ROOT/.venv-maia/bin/python" ]; then
  LUCENA_MAIA="$ROOT/.venv-maia/bin/python $ROOT/engine/scripts/maia_policy_uci.py"
fi
export LUCENA_MAIA
: "${LUCENA_HOME:=$HOME/.lucena-run}"
: "${LUCENA_ENGINE_PORT:=50051}"
: "${LUCENA_BACKEND_PORT:=8766}"
: "${LUCENA_PG_DSN:=postgresql:///lucena_dev}"
export LUCENA_STOCKFISH LUCENA_HOME LUCENA_ENGINE_PORT LUCENA_BACKEND_PORT LUCENA_PG_DSN

mkdir -p "$LOGS" "$LUCENA_HOME"

_alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

stop() {
  for pf in "$BACKEND_PID" "$ENGINE_PID"; do
    if _alive "$pf"; then kill "$(cat "$pf")" 2>/dev/null && echo "stopped $(basename "$pf" .pid) (pid $(cat "$pf"))"; fi
    rm -f "$pf"
  done
  # Belt-and-suspenders: a stale holder on the port (pid-file missed it) made `start` a no-op and kept
  # serving OLD CODE — the "restart didn't deploy" trap. Kill any lingering backend proc and RECLAIM
  # the port, waiting until it's actually free.
  pkill -f "lucena_backend.httpserver" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    holder="$(lsof -ti ":$LUCENA_BACKEND_PORT" 2>/dev/null || true)"
    [ -z "$holder" ] && break
    echo "$holder" | xargs -r kill -9 2>/dev/null || true
    sleep 1
  done
}

status() {
  _alive "$ENGINE_PID"  && echo "engine   : up   (pid $(cat "$ENGINE_PID"), :$LUCENA_ENGINE_PORT)"   || echo "engine   : down"
  _alive "$BACKEND_PID" && echo "backend  : up   (pid $(cat "$BACKEND_PID"), :$LUCENA_BACKEND_PORT)" || echo "backend  : down"
  pg_isready >/dev/null 2>&1 && echo "postgres : up   (:5432)" || echo "postgres : down"
}

case "${1:-up}" in
  stop)    stop; exit 0 ;;
  status)  status; exit 0 ;;
  logs)    tail -n 40 -F "$LOGS/engine.log" "$LOGS/backend.log"; exit 0 ;;
esac
# 'up' or 'restart' from here — both start the backend. Check the key BEFORE any stop, so a keyless
# 'restart' fails fast without taking down a running backend.
[ -n "${GEMINI_API_KEY:-}${GOOGLE_API_KEY:-}" ] || {
  echo "ERROR: no GEMINI_API_KEY in the environment — refusing to start the backend keyless."
  echo "Run:  GEMINI_API_KEY=\"\$KEY\" ./serve.sh   (or export it, e.g. from ~/.zshrc)"
  exit 1
}
[ "${1:-up}" = "restart" ] && stop   # reliable redeploy: stop (reclaims the port) then start below

# --- preflight ---------------------------------------------------------------
[ -x "$PY" ] || { echo "backend venv missing — run: python3.13 -m venv backend/.venv && backend/.venv/bin/pip install -e engine -e backend"; exit 1; }
[ -n "$LUCENA_STOCKFISH" ] || { echo "stockfish not found — brew install stockfish (or set LUCENA_STOCKFISH)"; exit 1; }

# --- postgres ----------------------------------------------------------------
if ! pg_isready >/dev/null 2>&1; then
  echo "postgres down — starting…"
  rm -f /opt/homebrew/var/postgresql@16/postmaster.pid 2>/dev/null || true
  pg_ctl -D /opt/homebrew/var/postgresql@16 -l "$LOGS/postgres.log" start >/dev/null 2>&1 || brew services start postgresql@16 >/dev/null 2>&1 || true
  sleep 2
fi
pg_isready >/dev/null 2>&1 || { echo "postgres still not reachable"; exit 1; }
"$PY" -c "import psycopg; psycopg.connect('$LUCENA_PG_DSN').close()" 2>/dev/null || createdb lucena_dev

# --- engine ------------------------------------------------------------------
if _alive "$ENGINE_PID"; then
  echo "engine already up (pid $(cat "$ENGINE_PID"))"
else
  nohup "$PY" -m lucena_engine.server.serve > "$LOGS/engine.log" 2>&1 &
  echo $! > "$ENGINE_PID"
  echo "engine   -> :$LUCENA_ENGINE_PORT (pid $(cat "$ENGINE_PID"))"
fi

# --- backend -----------------------------------------------------------------
# Reclaim the port from an ORPHAN holder (not our pid file) — else the new process can't bind and the
# orphan keeps serving stale code (exactly the bug that made a "restart" ship nothing).
holder="$(lsof -ti ":$LUCENA_BACKEND_PORT" 2>/dev/null || true)"
if [ -n "$holder" ] && ! _alive "$BACKEND_PID"; then
  echo "reclaiming :$LUCENA_BACKEND_PORT from orphan pid $holder"
  echo "$holder" | xargs -r kill -9 2>/dev/null || true; sleep 1
fi
if _alive "$BACKEND_PID"; then
  echo "backend already up (pid $(cat "$BACKEND_PID"))"
else
  nohup "$PY" -m lucena_backend.httpserver > "$LOGS/backend.log" 2>&1 &
  echo $! > "$BACKEND_PID"
  echo "backend  -> :$LUCENA_BACKEND_PORT (pid $(cat "$BACKEND_PID"))"
fi

sleep 4
echo
status
echo
echo "WS:   ws://127.0.0.1:$LUCENA_BACKEND_PORT/ws     REST: http://127.0.0.1:$LUCENA_BACKEND_PORT"
echo "logs: ./serve.sh logs      stop: ./serve.sh stop"
