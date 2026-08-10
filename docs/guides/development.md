---
description: The Makefile command vocabulary, the ruff and prettier code style, running the tests, and what CI checks on every pull request.
---

# Development

This repo and [lm-dashboard](https://github.com/InviteInstitute/lm-dashboard) share one
dev setup, so switching between them costs nothing. A **Makefile** gives both the same
command vocabulary, **ruff** and **prettier** own code style, and **GitHub Actions** runs
the same checks on every pull request.

## Set Up

You need Python 3.12, Node 20, and a local Postgres for the backend tests. Install the
backend (editable, with the dev extras) and the client dependencies in one step:

```bash
make install
```

That runs `pip install -e '.[dev]'` in `server/` and `npm install` in `client/`. Run it
inside an activated virtualenv so the console scripts and `ruff` land on your `PATH`.

## The Makefile

`make` (or `make help`) lists every target. It is a thin wrapper over the compose files
and `scripts/`, so each target does exactly what running those by hand would.

| Target | What it does |
|---|---|
| `make dev` | start the local stack (API with reload, Vite on `:5173`), Ctrl-C to stop |
| `make down` | stop the local stack |
| `make logs` / `make ps` | follow logs / show stack status |
| `make test` | backend (pytest) and client (vitest) tests |
| `make lint` | ruff lint over the backend |
| `make format` | ruff (backend) and prettier (client), writing changes |
| `make format-check` | the same checks without writing, as CI runs them |
| `make build` | build the client into `client/dist` |
| `make deploy` | the guarded prod rollout, then a client rebuild |

!!! tip "Docker that needs sudo"
    The docker targets honor a `COMPOSE` variable. On a host where docker needs sudo,
    run e.g. `make dev COMPOSE='sudo docker compose'`.

## Code Style

**Ruff** is the single source of truth for Python linting and formatting. Its config
lives in `server/pyproject.toml` and is kept identical to lm-dashboard. The rule set is
pyflakes, import sorting, pyupgrade, and bugbear. Line length is left to the formatter,
which the codebase favors dense over wrapped.

**Prettier** formats the client (JSX and CSS), configured in `client/.prettierrc.json`,
and an `.editorconfig` at the repo root keeps indentation and line endings consistent
across editors.

```bash
make format         # write changes
make format-check   # check only, the way CI does
```

!!! note "Blame stays readable"
    The one-time bulk reformats are recorded in `.git-blame-ignore-revs`. Point git at it
    so `git blame` skips them: `git config blame.ignoreRevsFile .git-blame-ignore-revs`.

## Tests

The backend suite lives in `server/tests/` and the client suite in `client/src`.

```bash
make test
```

Most backend tests are pure and run with no database. The tests that need one **skip**
unless `DATABASE_URL` is set, and a couple of integration tests also need the sample runs
loaded. To run the full suite the way CI does, point `DATABASE_URL` at a throwaway
Postgres, apply the migrations, and seed the fixtures first:

```bash
export DATABASE_URL=postgresql://vexagent:vexagent@127.0.0.1:5433/vexagent
for f in server/db/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
for f in server/tests/fixtures/raw_logs/*.ndjson; do vex-parse-logs --input "$f" --insert; done
cd server && pytest -q
```

The client suite runs under vitest and includes a smoke test that mounts the whole app,
so a React or Vite incompatibility fails loudly.

## Continuous Integration

`.github/workflows/ci.yml` runs on every push to `main` and every pull request, in two
jobs that mirror the make targets:

- **backend** - installs the package, runs `ruff check` and `ruff format --check`, then
  builds the schema from the migrations against a throwaway Postgres, seeds the fixtures,
  and runs pytest.
- **frontend** - runs the prettier check, the vitest suite, and a production build.

A green run means lint, formatting, both test suites, and the client build are all intact.
