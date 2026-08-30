#!/usr/bin/env bash
# First-boot bring-up for the all-in-one dev container. On a fresh Postgres volume
# this initializes the cluster, creates the role + database, applies every
# migration, and seeds the bundled fixtures -- the manual steps that otherwise trip
# people up. It is idempotent: a sentinel inside PGDATA means an existing volume is
# left alone. Then it hands off to supervisor, which owns the long-running trio
# (postgres + api + client).
set -euo pipefail

export PGDATA="${PGDATA:-/var/lib/postgresql/data}"
DB_USER="${POSTGRES_USER:-vexagent}"
DB_NAME="${POSTGRES_DB:-vexagent}"
SENTINEL="$PGDATA/.vex_seeded"

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set -- copy .env.example to .env}"

log() { echo "[entrypoint] $*"; }

seed_database() {
  log "Fresh volume -- initializing Postgres cluster at $PGDATA"
  su postgres -c "initdb -D '$PGDATA' --auth-local=trust --auth-host=scram-sha-256" >/dev/null

  # Dev-only: allow password-authenticated connections from any address so a DB GUI
  # on the host (via the published :5433) can connect. The host bind is loopback-only
  # (see compose.yml) and a password is still required.
  su postgres -c "printf 'host all all all scram-sha-256\n' >> '$PGDATA/pg_hba.conf'"

  log "Starting Postgres for one-time setup"
  su postgres -c "pg_ctl -D '$PGDATA' -w -t 60 start" >/dev/null

  cat > /tmp/pg_setup.sql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${POSTGRES_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${POSTGRES_PASSWORD}';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
SQL
  su postgres -c "psql -v ON_ERROR_STOP=1 -d postgres -f /tmp/pg_setup.sql" >/dev/null
  rm -f /tmp/pg_setup.sql

  log "Applying migrations"
  for f in /app/server/db/migrations/*.sql; do
    log "  - $(basename "$f")"
    PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 \
      -h 127.0.0.1 -p 5432 -U "$DB_USER" -d "$DB_NAME" -f "$f" >/dev/null
  done

  log "Seeding fixtures (bundled VEX telemetry -- no Invite Hub needed)"
  cd /app/server
  for f in tests/fixtures/raw_logs/*.ndjson; do
    if vex-parse-logs --input "$f" --insert >/dev/null 2>&1; then
      log "  - loaded $(basename "$f")"
    else
      log "  - skipped $(basename "$f") (fixture not loadable, continuing)"
    fi
  done

  su postgres -c "pg_ctl -D '$PGDATA' -m fast -w stop" >/dev/null
  touch "$SENTINEL"
  log "Database ready."
}

if [ ! -f "$SENTINEL" ]; then
  seed_database
else
  log "Existing seeded volume -- skipping init (delete the 'pgdata' volume to reseed)."
fi

log "Starting supervisor: postgres + api + client"
exec supervisord -c /etc/supervisor/supervisord.conf
