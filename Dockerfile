# All-in-one LOCAL DEV image: Postgres + the FastAPI API + the Vite client in one
# container, so a teammate runs a single `docker compose up` with nothing to wire.
# This is deliberately NOT how production runs (prod keeps Postgres, the API, and an
# nginx-served static client separate -- see README "Serving It Remotely"). Nothing
# here changes application code; it only packages what already exists.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PGDATA=/var/lib/postgresql/data \
    DEBIAN_FRONTEND=noninteractive

# System deps: Postgres server+client, Node 20 (Vite 7 needs >=20), supervisor to
# run the three processes, and the bits NodeSource's installer needs.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql postgresql-client supervisor curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 # Put the Debian-versioned Postgres server binaries (postgres, initdb, pg_ctl...)
 # on a stable PATH so the entrypoint and supervisor can call them by name.
 && ln -sf /usr/lib/postgresql/*/bin/* /usr/local/bin/

# --- Backend: editable install, matching the prod server image ---
WORKDIR /app/server
COPY server/ ./
RUN pip install -e .

# --- Frontend: install deps in a cached layer, then copy the source ---
WORKDIR /app/client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
# The browser (on the host) reaches the API via its published loopback port, not
# the compose-internal service name. This file survives the runtime bind mounts
# (we only mount client/src + index.html), so the served UI always targets :8001.
RUN printf 'VITE_API_BASE_URL=http://127.0.0.1:8001/v1\n' > /app/client/.env

# --- Process orchestration + first-boot DB init ---
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
 && mkdir -p "$PGDATA" /var/run/postgresql \
 && chown -R postgres:postgres "$PGDATA" /var/run/postgresql

EXPOSE 8000 5173 5432
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
