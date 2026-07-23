#!/usr/bin/env bash
# Start the local dev stack: Postgres + backend + frontend.
# Reads .env and decides whether to start Ollama: only if OPENAI_* points at a local
# Ollama (port 11434 / "ollama"); a remote LLM (e.g. Lumen) skips it.
# The proactive daemon follows TRIGGER_DAEMON_ENABLED from .env.
# Usage: scripts/start.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/.run"
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
BACKEND_PORT=8000
FRONTEND_PORT=5173

mkdir -p "$RUN"
[ -f "$ROOT/.env" ] && { set -a; . "$ROOT/.env"; set +a; }

brew services start postgresql@16 >/dev/null 2>&1 || true

# Local Ollama or remote LLM? Decide from what .env points OPENAI_* at.
case "${OPENAI_BASE_URL:-}${OPENAI_API_KEY:-}" in
  *11434*|*ollama*|*Ollama*)
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
      echo "ollama already running"
    else
      echo "starting ollama…"
      nohup ollama serve >"$RUN/ollama.log" 2>&1 &
    fi
    ;;
  *)
    echo "remote LLM (${OPENAI_BASE_URL:-unset}); not starting ollama"
    ;;
esac

( cd "$ROOT/server" && nohup "$ROOT/.venv/bin/python" -m uvicorn src.app:app \
    --host 127.0.0.1 --port "$BACKEND_PORT" >"$RUN/backend.log" 2>&1 & )
( cd "$ROOT/client" && nohup npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" \
    >"$RUN/frontend.log" 2>&1 & )

echo "backend :$BACKEND_PORT, frontend :$FRONTEND_PORT (logs in .run/)"
echo "proactive daemon: TRIGGER_DAEMON_ENABLED=${TRIGGER_DAEMON_ENABLED:-false}"
echo "open http://127.0.0.1:$FRONTEND_PORT"
