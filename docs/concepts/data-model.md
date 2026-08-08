---
description: The three Postgres schemas, the tables in each, and the ordered migrations that build them.
---

# Data Model

Everything the agent knows lives in Postgres, split across three schemas by what the data
is. The SQL files under `server/db/migrations/` are the source of truth, applied in
order.

| Schema | Holds |
|---|---|
| `event_logs` | parsed VEX events, detected triggers, and identity |
| `chat` | messages, their feedback, and the stream change counter |
| `current_state` | the derived per-session state snapshot |

## event_logs

**`parsed_events`** is the append-only record of what a student did in VEX, one row per
event. It carries the identity of the actor, the moment and kind of event, and the block
payload.

| Column | Notes |
|---|---|
| `session_id`, `student_id`, `class_code` | who and which session |
| `event_ts`, `event_type` | when, and what kind of event |
| `playground`, `program_type` | which task and program |
| `project_json`, `block_event_data_json`, `playground_data_json` | the block workspace and event payloads |
| `has_orphans`, `switch_block_count`, `error_message` | derived flags used by triggers |
| `source`, `source_log_id`, `source_received_at`, `source_queue` | provenance back to the Hub log |

**`agent_triggers`** records each detected behavior. A unique key on
`(student_id, session_id, trigger_type, run_index)` is the dedupe that makes a trigger
fire once. It also tracks `acted`, the `response_id` of the message it produced, and a
lifecycle of `acknowledged`, `resolved_at`, and `last_seen_at`.

**`switch_events`** logs identity switches, a casing flip or a changed class code.
**`student_identity`** maps a folded `canon_id` to the most recent spelling and class code
seen, so the same student is not split across near-duplicate ids.

## chat

**`messages`** is the conversation, one row per turn. Alongside the text and role it keeps
a `feedback_class`, a `response_id`, and an `origin` that marks whether a message was
`reactive` or `proactive`. **`message_feedback`** records a thumbs up or down and an
optional comment on a given response.

**`channel_rev`** is a single small counter per channel. The SSE stream reads one row to
learn a student's channel changed, rather than polling the messages table. This is what
keeps the live stream cheap.

## current_state

**`state_snapshots`** is the derived read model, one row per session and student enforced
by a unique constraint. It holds the computed picture of the session, `time_on_task_s`,
`action_level`, `progress_pct`, `direction`, `cognition`, and `persistence`, along with
the range of event ids it was computed from. Because it is a projection over
`parsed_events`, it can be dropped and rebuilt from the log at any time.

## The Migrations

Applied in filename order, drift-proof with no per-file list to maintain.

| File | Builds |
|---|---|
| `001_create_parsed_events` | the parsed event log |
| `002_create_state_snapshots` | the derived per-session snapshot |
| `003_add_playground_data_to_parsed_events` | playground payload on events |
| `004_create_messages` | the chat log |
| `005_create_message_feedback` | thumbs and comments |
| `006_create_agent_triggers` | detected triggers with the dedupe key |
| `007_agent_triggers_lifecycle` | acknowledge, resolve, and re-alert fields |
| `008_student_id_case_folding` | case and space folded student ids |
| `009_switch_events` | identity switch log |
| `010_channel_rev` | the O(1) stream change counter |
| `011_student_identity` | the canonical identity map |

Apply them against a running database with a short loop.

```bash
export DATABASE_URL=postgresql://vexagent:$POSTGRES_PASSWORD@127.0.0.1:5433/vexagent
for f in server/db/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
```
