# Pedagogical AI Agent

## Environment Variables

### Frontend (`client/.env.local`)

Copy [client/.env.example](client/.env.example) to `client/.env.local` and set:

- `VITE_API_BASE_URL`

Example:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000/v1
```

### Backend (repo root `.env` or deployment env vars)

Copy [.env.example](.env.example) to a repo root `.env` for local development, or set the same variables in your deployment platform:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `NAVIGATOR_MODEL`
- `BACKEND_CORS_ORIGINS`
- `INVITE_HUB_BASE_URL`
- `INVITE_HUB_USERNAME`
- `INVITE_HUB_PASSWORD`
- `TRIGGER_DAEMON_ENABLED` (proactive daemon, off by default)
- `TRIGGER_POLL_INTERVAL_S`
- `TRIGGER_STUDENT_RECENCY_HOURS` (scope to students active in last N hours; default 24)
- `TRIGGER_IDLE_MAX_S` (idle-backoff ceiling; default 30s)
- `TRIGGER_DISABLED` (comma-separated trigger types to detect-but-not-act-on)

Example:

```bash
DATABASE_URL=postgresql://USERNAME:PASSWORD@localhost:5432/DBNAME
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.ai.it.ufl.edu/
NAVIGATOR_MODEL=gpt-oss-20b
BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
INVITE_HUB_BASE_URL=https://inviteinstitutehub.org
INVITE_HUB_USERNAME=YOUR_USERNAME
INVITE_HUB_PASSWORD=YOUR_PASSWORD

# Proactive trigger daemon. Scope is every student with telemetry; when on it
# proactively messages real students. scripts/start.sh follows this flag.
TRIGGER_DAEMON_ENABLED=true
TRIGGER_POLL_INTERVAL_S=5
```

## Running

The backend is a Python package (`vex_agent`) under `server/`. Two ways to run it:

### Docker Compose (recommended)

Brings up Postgres + the API together. Migrations under `server/db/migrations/` are the
source of truth for the schema.

```bash
cp .env.example .env      # fill in secrets; POSTGRES_PASSWORD is required
docker compose up --build
```

- API: `http://127.0.0.1:8001` (container port 8000)
- Postgres: `127.0.0.1:5433` (container port 5432)

Apply migrations once against the running DB (see the loop below), pointing `DATABASE_URL`
at `127.0.0.1:5433`.

### Bare metal (local dev)

1. Backend:
   ```bash
   cd server
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e '.[dev]'          # deps from pyproject.toml; adds pytest for tests
   uvicorn vex_agent.app:app --reload --log-level info   # :8000
   ```
2. Client:
   ```bash
   cd client
   cp .env.example .env.local        # VITE_API_BASE_URL, e.g. http://127.0.0.1:8000/v1
   npm install && npm run dev         # :5173
   ```

macOS users can use `scripts/start.sh` / `scripts/stop.sh` (optional convenience:
brew Postgres + auto-detect local Ollama).

## Database migrations

Apply every migration in order (drift-proof — no per-file list to keep updated):

```bash
export $(grep -v '^#' .env | xargs)
for f in server/db/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
```

Load a fixture session (uses the installed console script; `pip install -e .` first):

```bash
vex-parse-logs --input server/tests/fixtures/raw_logs/01_error_flagging_a.ndjson --insert
```

## Fetch VEX Logs From Invite Institute Hub

Store your Invite Hub credentials in the repo root `.env`:

- `INVITE_HUB_BASE_URL=https://inviteinstitutehub.org`
- `INVITE_HUB_USERNAME=YOUR_USERNAME`
- `INVITE_HUB_PASSWORD=YOUR_PASSWORD`

Then fetch the latest VEX logs and save them locally:

- `vex-fetch-logs`

Fetch and immediately parse + insert into Postgres:

- `vex-fetch-logs --insert`

## Navigator
- Go to https://docs.rc.ufl.edu/training/NaviGator_Toolkit/ and follow instructions to set up API key.
- For deployment, use `OPENAI_API_KEY` and `OPENAI_BASE_URL` environment variables.
- `server/navigator_api_keys.json` should only be used as a local fallback.

### Local Development With Ollama

You can point the agent at a local [Ollama](https://ollama.com) instead of NaviGator. Set:

```bash
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
NAVIGATOR_MODEL=llama3.2:latest
```

Any instruct model you have pulled works. Avoid reasoning models that emit `<think>` tags, since the one-sentence trimming keeps the reasoning instead of the answer.

## Proactive Trigger Agent

The agent can reach out on its own. It watches the VEX log stream, measures how a student's code changes between runs, and detects behavioral triggers (wheel-spinning, resilience, explorer, step-by-step, inactive). When one fires, it pushes a short piece of feedback without waiting for the student to ask. Design notes are in [docs/superpowers/specs/2026-07-14-proactive-triggers-design.md](docs/superpowers/specs/2026-07-14-proactive-triggers-design.md).

Proactive messages reuse the normal feedback pipeline, so they share the same pedagogy as replies to a typed question. They are saved to `chat.messages` with `origin = 'proactive'` and delivered to the browser over Server-Sent Events.

### Ported from lm-dashboard

The trigger engine (`server/vex_agent/triggers/`) is vendored from [lm-dashboard](https://github.com/InviteInstitute/lm-dashboard) and kept in sync. The following modules were ported/aligned:

- **`triggers/constants.py`** — trigger thresholds + APTED edit costs + episode-segmentation constants. `ITERATIVE_EDIT_MIN = 0` (any real edit counts toward Step-by-Step).
- **`triggers/detectors.py`** — the pure momentary trigger pass (wheel_spin, resilience, explorer, iterative).
- **`triggers/distance.py`** + **`triggers/ast_builder.py`** + **`triggers/run_sequence.py`** — APTED tree-edit distance over Blockly workspace ASTs.
- **`triggers/episode_engine/`** — CODE/RUN/RESET episode segmentation with INACTIVE_PAUSE and POST_RUN_PAUSE detection (new; enriches the cognition classifier and the LLM grounding).
- **`triggers/smart_delta.py`** — renders the student's current workspace as `[Active]/[Orphaned]` pseudo-code for the LLM (replaces the raw-log-dump grounding; addresses the spike's "hallucination from thin grounding" learning).
- **`triggers/humanize.py`** + **`triggers/vex_blocks.json`** — readable program listing with parameter values (drive distances, etc.) that the edit-distance AST drops.
- **`triggers/switches.py`** — identity-switch detection (casing flip, classCode change).
- **Inactive trigger lifecycle** — re-alert after `RE_ALERT_SECONDS` (600s) so a persistently-idle student resurfaces, plus resolve-on-recovery (migration 007).
- **Daemon hardening** — debounced run-distance cache, recency window on scope (`TRIGGER_STUDENT_RECENCY_HOURS`), idle/failure backoff with UNHEALTHY logging, `TRIGGER_DISABLED` runtime toggle.
- **`channel_rev` O(1) SSE signaling** — the stream reads 1 row instead of polling `chat.messages` every 2s (migration 010).

### Turning It On

The daemon is off by default. In your repo root `.env`:

```bash
TRIGGER_DAEMON_ENABLED=true
TRIGGER_POLL_INTERVAL_S=5
```

Restart the backend and the daemon starts with it. `scripts/start.sh` reads this flag from `.env` (it does not force it), so set `TRIGGER_DAEMON_ENABLED=true` there to run it. Its scope is **every student with telemetry** in `parsed_events`, so when on it proactively messages real students. It will not repeat a message, because each specific trigger (student, session, trigger type, run) fires at most once, so a student only hears from the agent again when genuinely new behavior trips a trigger.

### Trying It Without The Daemon

Run one pass by hand for a single session, no timer needed:

```bash
curl -X POST http://127.0.0.1:8000/admin/tick \
  -H "Content-Type: application/json" \
  -d '{"student_id":"STUDENT_ID","session_id":"SESSION_ID"}'
```

The response lists the triggers it detected and the messages it pushed.

### Watching The Stream

The browser subscribes automatically once a student is set. To watch it from the terminal:

```bash
curl -N http://127.0.0.1:8000/v1/students/STUDENT_ID/stream
```

## Deployment

### Frontend on Vercel

Root directory:
- `client`

Environment variable:

```bash
VITE_API_BASE_URL=https://YOUR-RENDER-BACKEND.onrender.com/v1
```

### Backend on Render

Root directory:
- `server`

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn vex_agent.app:app --host 0.0.0.0 --port $PORT
```

Environment variables:

```bash
DATABASE_URL=postgresql://...
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.ai.it.ufl.edu/
NAVIGATOR_MODEL=gpt-oss-20b
BACKEND_CORS_ORIGINS=https://YOUR-FRONTEND.vercel.app
```

### Database on Supabase

- Create a Supabase project
- Use the Supabase Postgres connection string as `DATABASE_URL`
- Run the migration files before starting the deployed backend
