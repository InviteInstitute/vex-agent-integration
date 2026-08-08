---
description: Bring up Postgres and the API with docker compose, apply migrations, load a session, and run one feedback tick.
---

# Quickstart

You need **Docker** with the Compose v2 plugin, and an LLM the agent can call. In
development that can be a local [Ollama](https://ollama.com), so you do not need any
cloud credentials to see it work.

## Configure

The backend reads its secrets from a repo-root `.env`. Copy the example and fill it in.

```bash
cp .env.example .env
```

At a minimum set `POSTGRES_PASSWORD` (compose refuses to start without it) and point the
agent at an LLM. For a fully local setup, aim it at Ollama.

```bash
POSTGRES_PASSWORD=choose-something-strong
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
NAVIGATOR_MODEL=llama3.2:latest
```

!!! tip "Real logs are optional to start"
    `INVITE_HUB_USERNAME` and `INVITE_HUB_PASSWORD` let the agent fetch live VEX logs
    from the Invite Institute Hub. You can leave them empty at first and load a bundled
    fixture session instead, which is what the steps below do.

## Run The Stack

```bash
docker compose up --build
```

That starts two services.

| Service | Address | Notes |
|---|---|---|
| API | `http://127.0.0.1:8001` | FastAPI, container port 8000 |
| Postgres | `127.0.0.1:5433` | container port 5432, user and db both `vexagent` |

## Apply Migrations

The SQL files under `server/db/migrations/` are the source of truth for the schema.
Apply them in order against the running database. Point `DATABASE_URL` at the published
port `5433`.

```bash
export DATABASE_URL=postgresql://vexagent:$POSTGRES_PASSWORD@127.0.0.1:5433/vexagent
for f in server/db/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
```

## Load A Session And Ask For Feedback

Load a bundled fixture so there is real telemetry to ground on. This uses the
`vex-parse-logs` console script that ships with the `vex_agent` package.

```bash
vex-parse-logs --input server/tests/fixtures/raw_logs/01_error_flagging_a.ndjson --insert
```

Now run one feedback pass by hand for that session. The admin tick detects any triggers,
generates a proactive message for each new one, and returns what it found.

```bash
curl -X POST http://127.0.0.1:8001/admin/tick \
  -H "Content-Type: application/json" \
  -d '{"student_id":"STUDENT_ID","session_id":"SESSION_ID"}'
```

The response lists the triggers it detected and the messages it pushed. To see delivery
the way a student would, watch the live stream in another terminal.

```bash
curl -N http://127.0.0.1:8001/v1/students/STUDENT_ID/stream
```

## Bare Metal, For Backend Work

When you want reload-on-save on the API, run it in a venv instead.

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
uvicorn vex_agent.app:app --reload --log-level info   # :8000
```

Run the client alongside it.

```bash
cd client
cp .env.example .env.local        # set VITE_API_BASE_URL, e.g. http://127.0.0.1:8000/v1
npm install && npm run dev         # :5173
```

!!! note "One daemon writes"
    The proactive daemon is off by default and assumes a single writer. Turn it on with
    `TRIGGER_DAEMON_ENABLED=true`, and run exactly one instance. See
    [Configuration](guides/configuration.md) for every flag.

## Run These Docs Locally

This site is [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).

```bash
pip install mkdocs-material && mkdocs serve
```

It serves on [http://localhost:4100](http://localhost:4100) and live-reloads as you edit
anything under `docs/`.

## Next Steps

<div class="grid cards" markdown>

-   :material-sitemap:{ .lg .middle } **[Architecture](concepts/architecture.md)**

    ---

    How the layers fit together and where the two lanes meet.

-   :material-tune:{ .lg .middle } **[Configuration](guides/configuration.md)**

    ---

    Every environment variable, plus NaviGator and Ollama setups.

</div>
