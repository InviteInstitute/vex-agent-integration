---
description: Every endpoint the FastAPI backend exposes, with request and response shapes and the bot gate.
---

# API Reference

The API runs at `http://127.0.0.1:8001` (container port `8000`). In production nginx
serves the React client at `/` and proxies these paths to the API. Student-facing routes
live under `/v1`, the operational tick under `/admin`, and the health check at the root.

**The bot gate.** Every `/v1/*` route is behind **Cloudflare Turnstile**
(`TurnstileGateMiddleware`): a browser must present the signed "solved the widget" cookie,
minted by `POST /v1/turnstile/verify/` (the one open `/v1` route). There's no student
login - see [Configuration](../guides/configuration.md#the-bot-gate-turnstile). `/healthz`
is unauthenticated. `/admin/*` sits outside the gate and is meant for internal use.

## Endpoints At A Glance

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/healthz` | health check (unauthenticated) |
| `POST` | `/v1/turnstile/verify/` | solve Turnstile, mint the gate cookie (the one open `/v1` route) |
| `GET`  | `/v1/ping` | trip the gate at page load (gated, `403` until solved) |
| `GET`  | `/v1/students/{id}/session` | resolve a student's latest session, syncing logs if needed |
| `POST` | `/v1/students/{id}/messages` | record an inbound student message |
| `POST` | `/v1/students/{id}/responses` | generate one grounded feedback reply |
| `POST` | `/v1/students/{id}/responses/{response_id}/feedback` | thumbs up/down on a reply |
| `GET`  | `/v1/students/{id}/stream` | the live Server-Sent Events stream of pushed messages |
| `GET`  | `/v1/research/config` | models, defaults, the live prompt template, and this session's token usage, for the research preview |
| `POST` | `/admin/tick` | run one proactive tick by hand (internal) |

---

## GET /healthz

Liveness check, and what `scripts/deploy.sh` gates on. Unauthenticated, at the root so
the static client can own `/`.

```json title="Response"
{ "status": "ok" }
```

---

## POST /v1/turnstile/verify/

The one open `/v1` route. The browser posts the Turnstile token. On success the server
sets the signed, httpOnly gate cookie the middleware then checks on every other `/v1`
call.

```json title="Request"
{ "token": "0.abc..." }
```

```json title="Response"
{ "ok": true }
```

A token that fails Cloudflare's siteverify returns `403`.

---

## GET /v1/ping

A tiny gated route the client hits once on mount, so the Turnstile gate trips at page
load instead of on the first real chat call. Returns `403` until the widget is solved.

```json title="Response"
{ "ok": true }
```

---

## GET /v1/students/{student_id}/session

Resolve the student's most recent session id. If none is found yet, it does a
cursor-neutral per-student log sync (see [Ingestion](../guides/ingestion.md#who-syncs))
and tries again.

```json title="Response"
{ "session_id": "…", "student_id": "…", "playground": "GO-Mars", "status": "resolved" }
```

Returns `404` with a "run the project once in VEX VR" message when the student still has
no telemetry.

---

## POST /v1/students/{student_id}/messages

Record an inbound student message (a typed question, or a help-button tap). This persists
the message. The grounded reply comes from the `responses` endpoint.

```json title="Request"
{ "session_id": null, "message": "why won't my robot turn?", "playground": null, "chat": "student" }
```

```json title="Response"
{
  "message_id": "…",
  "session_id": "…",
  "student_id": "…",
  "playground": "GO-Mars",
  "message": "why won't my robot turn?",
  "source": "chat",
  "status": "received"
}
```

`source` is `chat` for typed messages or `help_button` for a tap. `chat` says which
conversation the message belongs to: `student` (the default) or `research`, the research
preview's separate chat. Each chat keeps its own recent turns, which are what the agent
sees as "recent chat", and research-chat messages are stored with `origin = 'research'`.
`responses` takes the same `chat` field; a request with `overrides` is always the
research chat.

---

## POST /v1/students/{student_id}/responses

The core reactive endpoint: generate **one grounded feedback reply**. It refreshes the
student's newest events (cursor-neutral), builds the deterministic situation model, and
hands that plus the current program and recent chat to a single LLM pass. Both lanes -
this one and the proactive daemon - run the [same pipeline](../concepts/feedback-pipeline.md).

```json title="Request"
{
  "message_id": "…",
  "session_id": "…",
  "playground": "GO-Mars",
  "student_message": "why won't my robot turn?"
}
```

```json title="Response"
{
  "response_id": "…",
  "session_id": "…",
  "student_id": "…",
  "playground": "GO-Mars",
  "message_id": "…",
  "response_text": "Look at your turn block - the amount is 0, so it spins in place…",
  "llm_model": "gpt-oss-20b",
  "llm_prompt": "…",
  "status": "received"
}
```

If the student's run is still active or they're on the wrong playground, the reply is a
short instruction to stop or switch first, rather than feedback on stale code.

The response also carries `llm_tokens` (what this reply's LLM calls spent) and
`session_tokens` (`{"used": …, "limit": …}` for this browser session). Once the session
or the site is out of tokens the endpoint returns `429` with a plain `detail` message,
before doing any work. `student_message` is capped at 2,000 characters (`422` past it).
See [Token budgets](../guides/configuration.md#token-budgets).

**Research overrides.** The request may carry `overrides` to try other agent settings.
Every field is optional; a field left out keeps the production default. The reply is
stored with `origin = 'research'`, and it counts against the session's token budget like
any other.

```json title="Request with overrides"
{
  "session_id": "…",
  "student_message": "why won't my robot turn?",
  "overrides": {
    "model": "gemma-4-31b-it",
    "prompt_template": "You tutor a middle schooler. Program:\n{current_program}\nThey asked: {student_message}",
    "temperature": 0.3,
    "max_tokens": 300,
    "trim_reply": false
  }
}
```

---

## GET /v1/research/config

What the research preview's Agent tab needs: the models the gateway serves, the
production defaults, the live prompt template with its placeholders, and this browser
session's token usage. If the gateway can't list models, `models` holds just the default
and `models_error` says why.

```json title="Response"
{
  "defaults": { "model": "qwen3.8-27b", "max_tokens": 160, "trim_reply": true },
  "models": ["gemma-4-31b-it", "glm-5.3", "qwen3.8-27b"],
  "models_error": null,
  "prompt_template": "You are an educational feedback assistant for VEXcode VR…",
  "placeholders": { "task": "The playground's task description.", "…": "…" },
  "session_tokens": { "used": 12340, "limit": 150000 }
}
```

---

## POST /v1/students/{student_id}/responses/{response_id}/feedback

Record a student's thumbs up/down on a reply, with an optional comment. Stored against
the message that carried `response_id`.

```json title="Request"
{ "thumb": "up", "comment": "that fixed it!" }
```

```json title="Response"
{ "student_id": "…", "response_id": "…", "thumb": "up", "comment": "that fixed it!", "status": "received" }
```

---

## GET /v1/students/{student_id}/stream

The live delivery channel: one long-lived **Server-Sent Events** connection. Proactive
messages the daemon pushes (and any reply saved for this student) arrive here, so the
client shows them without polling. The stream sends periodic keep-alives.

```text title="Response stream (text/event-stream)"
event: assistant_message
data: {"message_id": 42, "message_text": "Nice recovery - that edit changed things.", "trigger_type": "resilience", …}

: keep-alive
```

A fresh connection delivers only messages pushed after it opens (it starts from the
newest message id), not the whole history.

---

## POST /admin/tick

Run **one proactive tick** for a single student/session by hand - the same pass the
daemon runs on a loop. It detects any triggers, generates a proactive message for each
new one, and returns what it found. Used for the [Quickstart](../quickstart.md) and for
debugging. It sits outside the bot gate.

```json title="Request"
{ "student_id": "…", "session_id": "…" }
```

```json title="Response"
{ "detected": [ { "trigger_type": "wheel_spin", "run_index": 6 } ], "acted": [ … ] }
```

See [Proactive triggers](../concepts/proactive-triggers.md) for the trigger types and
their firing rules.
