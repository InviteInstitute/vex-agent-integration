#!/usr/bin/env bash
# Deploy the latest to this prod server via docker compose: pull, rebuild the
# images, roll the stack (db + api), apply the SQL migrations, then verify
# /healthz. Unlike lm-dashboard, the api does NOT create the schema on startup --
# server/db/migrations/ is the source of truth and is applied here (every file is
# idempotent via IF NOT EXISTS, so re-running the whole loop is safe). Refuses to
# run over uncommitted changes to tracked files -- commit, stash, or discard them
# first so a pull never silently clobbers edits.
#
# The proactive trigger daemon runs in-process inside the api (gated by
# TRIGGER_DAEMON_ENABLED), so there is no separate daemon service to roll.
#
# The client is a static Vite build served by nginx from client/dist, not by the
# api. This script does not rebuild it; run `npm --prefix client run build` when
# the frontend changes.
#
# Prereqs on this host: Docker + the compose v2 plugin, and a `.env` with
# POSTGRES_PASSWORD and the app secrets (see .env.example).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Deploying VEX Agent (docker compose) ..."

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Working tree has uncommitted changes to tracked files -- aborting:"
  git status --short
  exit 1
fi

BEFORE=$(git rev-parse HEAD)
git pull --ff-only
AFTER=$(git rev-parse HEAD)
if [ "$BEFORE" = "$AFTER" ]; then
  echo "Already up to date ($AFTER)."
else
  echo "Updated $BEFORE -> $AFTER"
fi

echo "Building + rolling the stack ..."
docker compose -f compose.yml up -d --build

echo "Applying migrations (idempotent) ..."
for f in server/db/migrations/*.sql; do
  echo "  $f"
  docker compose -f compose.yml exec -T db \
    psql -U vexagent -d vexagent -v ON_ERROR_STOP=1 -q < "$f" >/dev/null
done

echo "Waiting for the API to come back up ..."
for _ in $(seq 1 30); do
  curl -s -o /dev/null http://127.0.0.1:8001/healthz && break
  sleep 1
done

code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/healthz)
if [ "$code" = "200" ]; then
  echo "Deploy OK -- /healthz = 200"
else
  echo "WARNING: /healthz returned $code -- check: docker compose -f compose.yml logs api"
  exit 1
fi

docker compose -f compose.yml ps
