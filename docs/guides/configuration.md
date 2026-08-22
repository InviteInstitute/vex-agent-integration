---
description: Every environment variable the agent reads, plus UIUC Servers and Ollama LLM setups and the Turnstile bot gate.
---

# Configuration

The backend reads all of its configuration from a single gitignored **`.env`** at the
repo root. `docker compose` also reads that same file: it needs `POSTGRES_PASSWORD` to
start the `db` service. Copy the example and fill it in.

```bash
cp .env.example .env
```

## Environment Variables

| Variable | Where | Default | What It Does |
|---|---|---|---|
| `POSTGRES_PASSWORD` | `.env` (compose) | (none) | password for the `db` service, compose refuses to start without it |
| `DATABASE_URL` | app | (none) | Postgres connection string. Under compose the API reaches `db` on the compose network. For a venv run point it at the published port `5433` |
| `OPENAI_API_KEY` | app | (none) | key for the LLM gateway. For a local Ollama any non-empty value works (e.g. `ollama`) |
| `OPENAI_BASE_URL` | app | (none) | base URL of the OpenAI-compatible endpoint. UIUC Servers in prod, or `http://localhost:11434/v1` for Ollama |
| `NAVIGATOR_MODEL` | app | (none) | the model name to call, e.g. `gpt-oss-20b` (UIUC Servers) or `llama3.2:latest` (Ollama) |
| `BACKEND_CORS_ORIGINS` | app | `localhost:5173`, `127.0.0.1:5173` | comma-separated allowed client origins (dev only, prod is proxied same-origin by nginx) |
| `INVITE_HUB_BASE_URL` | app | `https://inviteinstitutehub.org` | the Invite Institute Hub, source of the VEX event logs |
| `INVITE_HUB_USERNAME` / `INVITE_HUB_PASSWORD` | app | (none) | Hub credentials for log ingestion, leave empty to run on fixtures only |
| `TRIGGER_DAEMON_ENABLED` | daemon | `false` | arms the proactive daemon. When on, it messages **real** students on a poll, so turning it on is a deliberate act |
| `TRIGGER_POLL_INTERVAL_S` | daemon | `5` | base seconds per tick while activity is flowing |
| `TRIGGER_STUDENT_RECENCY_HOURS` | daemon | `24` | scope the daemon to students with an event in the last N hours, so the first tick doesn't fire `inactive` for every historically idle student |
| `TRIGGER_IDLE_MAX_S` | daemon | `30` | idle-backoff ceiling (how far the poll gap stretches when it's quiet) |
| `TRIGGER_DISABLED` | daemon | (empty) | comma-separated trigger types to detect-but-not-act-on (e.g. `inactive,explorer`), still persisted to `agent_triggers` |
| `SESSION_SECRET` | API | insecure dev default | signs the "this browser solved Turnstile" cookie. Set a long random value in any real deployment or the cookie is forgeable |
| `TURNSTILE_SECRET` | API | (none) | Cloudflare Turnstile server-side secret. Unset means the bot gate can't verify anyone |

## The LLM Gateway

Feedback runs through any OpenAI-compatible endpoint, set with the three `OPENAI_*` /
`NAVIGATOR_MODEL` variables. Nothing about the pedagogy changes when you swap them.

=== "UIUC Servers (production)"

    ```bash
    OPENAI_API_KEY=your-uiuc-key
    OPENAI_BASE_URL=https://api.ai.it.ufl.edu/
    NAVIGATOR_MODEL=gpt-oss-20b
    ```

=== "Ollama (local, no cloud)"

    ```bash
    OPENAI_API_KEY=ollama
    OPENAI_BASE_URL=http://localhost:11434/v1
    NAVIGATOR_MODEL=llama3.2:latest
    ```

!!! tip "Warm-up on boot"
    On startup the API primes the LLM client and the Invite Hub auth token in a
    background thread, so the first student request doesn't pay that cold-start. A
    dependency that's cold at boot never blocks startup.

## The Bot Gate (Turnstile)

There is no student login. The only gate is **Cloudflare Turnstile**, which keeps bots
(not people) off the write API: a browser solves the widget once, and success is
remembered via a signed cookie. `TurnstileGateMiddleware` guards every `/v1/*` route
except the one open verify endpoint (see the [API reference](../reference/api.md)).

- `TURNSTILE_SECRET` is the widget's server-side secret from the Cloudflare dashboard.
- `SESSION_SECRET` signs the "solved the widget" cookie - **set a long random value in
  prod**, or the cookie can be forged.

## The Proactive Daemon

The proactive lane is an in-process background thread, off by default. When
`TRIGGER_DAEMON_ENABLED=true` it wakes every `TRIGGER_POLL_INTERVAL_S` seconds, syncs
new logs, and runs a proactive tick for every in-scope student.

- **Scope** is every student with an event in the last `TRIGGER_STUDENT_RECENCY_HOURS`.
- **Idle backoff**: quiet ticks grow the sleep toward `TRIGGER_IDLE_MAX_S`. The first
  sign of activity snaps it back to the base interval.
- **Dedup**: each `(student, session, trigger_type, run_index)` fires at most once ever
  (a `UNIQUE` on `agent_triggers`), so a student only hears from the agent again on
  genuinely new behavior.

!!! warning "One writer"
    The daemon assumes a **single instance**. It is also the sole owner of the Invite
    Hub ingest cursor (see [Ingestion](ingestion.md)). Run exactly one.

The trigger types and their firing rules live in
[Proactive triggers](../concepts/proactive-triggers.md).
