#!/usr/bin/env bash
# Start/stop the local dev stack: Postgres (Homebrew), FastAPI backend, Vite frontend.
# Usage: scripts/dev.sh {start|stop|restart|status}
#
# ponytail: stop uses pkill by command pattern (dev-only, one instance per machine).
# Switch to pidfiles if you ever run multiple uvicorn/vite instances here.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/.run"
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
BACKEND_PORT=8000
FRONTEND_PORT=5173

start() {
  mkdir -p "$RUN"
  brew services start postgresql@16 >/dev/null 2>&1 || true
  curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 \
    || echo "warning: Ollama not responding on :11434 (start it with 'ollama serve')"

  [ -f "$ROOT/.env" ] && { set -a; . "$ROOT/.env"; set +a; }

  ( cd "$ROOT/server" && nohup "$ROOT/.venv/bin/python" -m uvicorn src.app:app \
      --host 127.0.0.1 --port "$BACKEND_PORT" >"$RUN/backend.log" 2>&1 & )
  ( cd "$ROOT/client" && nohup npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" \
      >"$RUN/frontend.log" 2>&1 & )

  echo "starting backend :$BACKEND_PORT and frontend :$FRONTEND_PORT (logs in .run/)"
  echo "open http://127.0.0.1:$FRONTEND_PORT"
}

stop() {
  pkill -f "uvicorn src.app" 2>/dev/null && echo "stopped backend" || echo "backend not running"
  pkill -f "vite" 2>/dev/null && echo "stopped frontend" || echo "frontend not running"
  echo "(Postgres left running; 'brew services stop postgresql@16' to stop it too)"
}

check() { curl -sf -o /dev/null "$1" && echo up || echo down; }

status() {
  printf "backend  :%s   " "$BACKEND_PORT"; check "http://127.0.0.1:$BACKEND_PORT/health"
  printf "frontend :%s   " "$FRONTEND_PORT"; check "http://127.0.0.1:$FRONTEND_PORT/"
  printf "ollama   :11434  "; check "http://localhost:11434/api/tags"
  printf "postgres         "; pg_isready -q && echo up || echo down
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; sleep 1; start ;;
  status)  status ;;
  *) echo "usage: $0 {start|stop|restart|status}"; exit 1 ;;
esac
