#!/usr/bin/env bash
# Stop the backend and frontend. Leaves shared services (Postgres, Ollama) running,
# since other tools may depend on them; stop those by hand if you want them down.
# Usage: scripts/stop.sh
set -uo pipefail

pkill -f "uvicorn src.app" 2>/dev/null && echo "stopped backend" || echo "backend not running"
pkill -f "vite" 2>/dev/null && echo "stopped frontend" || echo "frontend not running"
echo "(Postgres/Ollama left running)"
