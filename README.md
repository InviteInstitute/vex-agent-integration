# Pedagogical AI Agent

## Environment Variables

### Frontend (`client/.env.local`)

Copy [client/.env.example](/Users/tiffanyvuu/Documents/College/Semester8/CIS4914/senior-project/client/.env.example) to `client/.env.local` and set:

- `VITE_API_BASE_URL`

Example:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000/v1
```

### Backend (repo root `.env` or deployment env vars)

Copy [.env.example](/Users/tiffanyvuu/Documents/College/Semester8/CIS4914/senior-project/.env.example) to a repo root `.env` for local development, or set the same variables in your deployment platform:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `NAVIGATOR_MODEL`
- `BACKEND_CORS_ORIGINS`
- `INVITE_HUB_BASE_URL`
- `INVITE_HUB_USERNAME`
- `INVITE_HUB_PASSWORD`

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
```

## Running Client and Server
1. Client:
   - `cd client`
   - `cp .env.example .env.local`
   - `npm install`
   - `npm run dev`
2. Server:
   - create a repo root `.env` from [.env.example](/Users/tiffanyvuu/Documents/College/Semester8/CIS4914/senior-project/.env.example), or export the backend env vars
   - `cd server`
   - `source .venv/bin/activate`
   - `uvicorn src.app:app --reload --log-level info`

## Local DB Setup (Team Workflow)

Use local Postgres per team member, and apply the same migration files.

1. Create and activate a virtual environment:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
2. Install shared dependencies:
   - `pip install -r server/requirements.txt`
3. Create your own `.env` at repo root:
   - `cp .env.example .env`
4. Run migrations:
   - `export $(grep -v '^#' .env | xargs)`
   - `psql "$DATABASE_URL" -f server/db/migrations/001_create_parsed_events.sql`
   - `psql "$DATABASE_URL" -f server/db/migrations/002_create_state_snapshots.sql`
   - `psql "$DATABASE_URL" -f server/db/migrations/003_add_playground_data_to_parsed_events.sql`
   - `psql "$DATABASE_URL" -f server/db/migrations/004_create_messages.sql`
   - `psql "$DATABASE_URL" -f server/db/migrations/005_create_message_feedback.sql`
   - `psql "$DATABASE_URL" -f server/db/migrations/006_create_agent_triggers.sql`
5. Load parsed logs:
   - `python3 server/src/parse_event_logs.py --input server/tests/fixtures/raw_logs/01_error_flagging_a.ndjson --insert`

## Fetch VEX Logs From Invite Institute Hub

Store your Invite Hub credentials in the repo root `.env`:

- `INVITE_HUB_BASE_URL=https://inviteinstitutehub.org`
- `INVITE_HUB_USERNAME=YOUR_USERNAME`
- `INVITE_HUB_PASSWORD=YOUR_PASSWORD`

Then fetch the latest VEX logs and save them locally:

- `python3 server/src/fetch_invite_hub_logs.py`

Fetch and immediately parse + insert into Postgres:

- `python3 server/src/fetch_invite_hub_logs.py --insert`

## Navigator
- Go to https://docs.rc.ufl.edu/training/NaviGator_Toolkit/ and follow instructions to set up API key.
- For deployment, use `OPENAI_API_KEY` and `OPENAI_BASE_URL` environment variables.
- `server/navigator_api_keys.json` should only be used as a local fallback.

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
uvicorn src.app:app --host 0.0.0.0 --port $PORT
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
