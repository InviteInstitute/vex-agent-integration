# Proactive Trigger-Driven Agent — Design Spec

**Date:** 2026-07-14
**Repo:** InviteInstitute/vex-agent-integration (fork of VEX-pedagogical-policies-project)
**Status:** Delivered — all slices implemented and merged (2026-07-14). See §14.

## 1. Goal

Today the pedagogical agent is **pull-based**: it only speaks when a student sends a
message (`POST /v1/students/{id}/responses`). This feature adds a **push lane**: the
agent detects behavioral **triggers** from the live VEX log stream and reaches out
**proactively** — with no student message — reusing the same pedagogy pipeline.

The trigger definitions are vendored from `lm-dashboard` (Approach A, below), where they
already drive a teacher's "who needs help" board. Here they drive the agent itself.

## 2. Decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Interaction model | **Proactive push** | Agent acts on triggers unprompted. |
| Where the loop runs | **Background daemon in FastAPI** | Silent/idle students never poll in, so a request-driven model can't see them. |
| Delivery to student | **SSE**, backed by a DB poll (see §7) | Real-time to the client without in-process pub/sub complexity. |
| Distance calc | **Full APTED port** (vendored) | All 5 triggers get true magnitude; free for wheel_spin (equality short-circuits before APTED runs). |
| Message generation | **Reuse pipeline; trigger sets the feedback class** | One pedagogy path, proactive and reactive. |
| Trigger scope v1 | **Scaffold all 5; only `wheel_spin` acts** | Detect+persist all five; route only wheel_spin to the agent. Others flip on with a one-line map entry. |
| Integration strategy | **A — vendor the dashboard's pure modules** | Small, proven, already speaks our data contract; no coupling to either heavy repo's runtime. |

## 3. The five triggers (vendored definitions)

Defined on each run's integer `edit_distance` (APTED tree-edit distance over the run's
Blockly workspace AST). Thresholds from `lm-dashboard/app/constants.py`:

- **wheel_spin** — ≥ 6 consecutive zero-edit runs (re-running identical code). *v1: acted on.*
- **resilience** — a real edit right after ≥ 4 zeros (recovered from stuck). *scaffold.*
- **explorer** — a single run with edit_distance ≥ 13 (big rewrite). *scaffold.*
- **iterative** (Step-by-Step) — ≥ 6 runs with edit_distance > 1 (steady edits). *scaffold.*
- **inactive** — no event for ≥ 240s. Sustained (per-tick sweep), needs no distance. *scaffold.*

## 4. Architecture

```
                 ┌────────── existing PULL lane (unchanged) ──────────┐
 student types → /v1/.../responses → snapshot → feedback classes → LLM → reply
                 └────────────────────────────────────────────────────┘

                 ┌────────── new PUSH lane ───────────────────────────┐
 Invite Hub ─poll→ parsed_events(DB) → trigger engine → daemon dedupe+scope+cooldown
  (incremental, reused)               (APTED per run)          │
                                                    wheel_spin fires
                                                               ▼
                                       generate_proactive_response (reuses pipeline)
                                                               ▼
                                       chat.messages + agent_triggers (DB)
                                                               ▼
                                       SSE /v1/students/{id}/stream → client EventSource
                 └────────────────────────────────────────────────────┘
```

## 5. Components

### 5.1 New package `server/src/triggers/` (vendored, Approach A)
- `ast_builder.py` — `xml_to_block_ast`, `extract_workspace_xml`. Copied verbatim; already
  matches our `project_json["workspace"]` shape.
- `distance.py` — APTED tree-edit distance + Blockly edit-cost config + XML-pair memo cache
  (`cached_edit_distance` short-circuits identical XML to 0 without building a tree).
- `constants.py` — thresholds + APTED costs + `TRIGGER_LABELS`.
- `run_sequence.py` — `compute_run_edit_distances(events)`: RUN events → workspace XML → AST →
  per-run distance vs previous, per contiguous playground stretch.
- `detectors.py` — `detect_run_triggers` / `detect_run_triggers_by_playground` (pure; emit all 5).
- New dependency: `apted>=1.0`.

### 5.2 Daemon `server/src/trigger_daemon.py`
Background **thread** launched from FastAPI lifespan (thread, not asyncio task — the sync
psycopg/urllib/openai calls would block the event loop). Each tick (`TRIGGER_POLL_INTERVAL_S`,
default 20s):
1. `sync_invite_hub_logs()` — reuse existing incremental pull.
2. **Scope filter (hard requirement, §8):** keep only students who have used this agent's chat (`students_in_chat`).
3. Per in-scope session with new RUN events → `compute_run_edit_distances` → `detect_run_triggers_by_playground`.
4. Sweep sustained `inactive` (scaffold).
5. **Dedupe** against `agent_triggers` on `(student_id, session_id, trigger_type, run_index)`. This is also
   what bounds re-messaging — each specific trigger fires at most once ever, so no timer/cooldown is needed.
6. New in-scope **wheel_spin** rows → generate → persist assistant message → student's SSE picks it up.
   Other trigger types: persist the `agent_triggers` row only (detected, not acted on).

> **Revised after delivery:** the per-student cooldown was removed in favour of the dedup bound above,
> and scope was widened to **every student with telemetry** (`all_students`, all distinct `student_id`
> in `parsed_events`) — the daemon now runs the agent for everyone, not an allowlist/class/chat subset.
> The `PROACTIVE_*` env vars below are retired.

Gated by `TRIGGER_DAEMON_ENABLED` (default **off** — dev/import never hammers prod).

### 5.3 Generation `generate_proactive_response(student_id, session_id, trigger)`
- `TRIGGER_TO_FEEDBACK_CLASS` (seeded by the spike): `wheel_spin → {REASSURE, DIAGNOSE}`.
- **Grounding (spike learning §9):** run the SAME robot-behavior LLM pass the pull flow uses
  over the session's real logs, so the message is grounded in actual robot behavior. Do **not**
  pass a trigger-fact-only summary — that hallucinates.
- **No fake student message:** `student_message=""`; the trigger enters as a **neutral behavioral
  fact** ("has run the same code 6 times without changing it"), never the internal label.
- Reuse `build_feedback_prompt_from_classes` → `generate_main_llm_response` → sanitizer (§9) →
  `enforce_student_response_length`.

### 5.4 Delivery — SSE
- `GET /v1/students/{student_id}/stream` → `text/event-stream`. Handler polls `chat.messages`
  for new `origin='proactive'` rows for that student every ~2s and emits `assistant_message`
  events. No pub/sub, no cross-thread bridge. Browser `EventSource` auto-reconnects.
- Client: one `EventSource` in `App.jsx`; on message, append to the existing chat panel.
  > ponytail: swap DB-poll → in-process pub/sub only past ~50 concurrent students.

## 6. Data model (migration `006`)
- `event_logs.agent_triggers`: `id, student_id, session_id, trigger_type, run_index,
  detail_json, fired_at, acted bool, response_id uuid null`,
  `UNIQUE(student_id, session_id, trigger_type, run_index)`.
- `chat.messages`: add `origin text default 'reactive'` (values `reactive` | `proactive`) so
  analysis can separate the two, and the SSE poll can filter.

## 7. Config (new env vars)
- `TRIGGER_DAEMON_ENABLED` (default `false`)
- `TRIGGER_POLL_INTERVAL_S` (default `20`)
- ~~`PROACTIVE_COOLDOWN_S`~~ — retired (dedup bounds re-messaging).
- ~~`PROACTIVE_STUDENT_ALLOWLIST` / `PROACTIVE_CLASS_CODE`~~ — retired; scope is now the chat roster (see §8).

## 8. Safety / trust boundary (NOT optional)
`sync_invite_hub_logs()` pulls **every** prod event across all classes, and (per the researcher's
call) the daemon's scope is now **every student with telemetry** (`all_students`). So when
`TRIGGER_DAEMON_ENABLED=true` the daemon proactively messages real students across all synced
classes — enabling it is therefore a deliberate, authorized act, not a default. Re-messaging is
bounded by the `agent_triggers` dedup (§5.2 step 5): each specific trigger fires at most once, so an
oscillating student (stuck → tiny edit re-arms → stuck) hears from the agent again only on genuinely
new behavior, no timer required. **Open consideration:** with no recency filter, the first tick fires
`inactive` for every historically idle student at once; add a `parsed_events.event_ts` window to
`all_students` if that blast radius matters.

## 9. Spike learnings (server/poc_proactive_trigger.py)
The walking-skeleton spike proved the chain end-to-end and surfaced three design changes,
all folded in above:
1. **Trigger-name leak** — feeding the human label "Wheel-spinning" made the model tell the
   student "it's normal to spin the wheel repeatedly." → Feed a neutral behavioral fact, not the label.
2. **Hallucination from thin grounding** — trigger-fact-only context made the model invent
   speed/turning advice. → The proactive path must run the real log-grounded robot-behavior pass.
3. **Label/quote leaks + high variance on `llama3.2`** — outputs like `"Encouragement:"` and
   wrapping quotes survive trimming. → Add an output sanitizer (strip leading labels/quotes)
   before `enforce_student_response_length`; consider a stronger model for production.

## 10. KEEPER vs THROWAWAY (from the spike)
- **Keeper:** `detect_run_triggers` (pure), the trigger→feedback-class seed table, "trigger as
  telemetry not a fake message" pattern.
- **Throwaway:** the faked `edit_distance` sequence (real v1 computes it via APTED).

## 11. Testing (lift the dashboard's — they're pure)
- `test_detectors.py`: known edit_distance sequence → wheel_spin at 6th zero, resilience on recovery, re-arm.
- `test_distance.py`: identical workspace XML → 0; one changed block → > 0.
- `test_dedupe.py`: same `(student, session, type, run_index)` never fires twice.
- `test_sanitizer.py`: label/quote-leaked model output → clean one sentence.

## 12. Delivery plan — vertical slices (feature by feature)
Each slice is demoable end-to-end, riskiest-first:
1. **Slice 0 (done):** spike — detector → mapping → Ollama, one script.
2. **Slice 1:** real APTED distance + `wheel_spin` → proactive row in DB (manual `POST /admin/tick`, no timer). *Validates grounding + sanitizer against real sessions.*
3. **Slice 2:** SSE delivery — client shows a proactively-pushed message live.
4. **Slice 3:** always-on daemon + scope allowlist + cooldown.
5. **Slice 4:** graduate `resilience` + `inactive` (cheap: no/low distance) to acting.
6. **Slice 5:** `explorer` + `iterative`.

## 13. Deferred (tracked, not v1)
- Suppress-while-actively-chatting.
- In-process pub/sub for SSE at scale.
- Sanitizer robustness for model meta-preambles (issue #22).

## 14. Delivered (2026-07-14)

All slices merged to `main`. Every non-trivial change landed with tests; the full
suite is **54 passing**.

| Slice | PRs | What shipped |
|---|---|---|
| Foundation | #1, #16 | Spec + spike; vendored trigger engine (`server/src/triggers/`, APTED). |
| 1 | #17, #18, #19, #20, #21, #23 | Migration 006; EventRecord→distance adapter; detect+dedupe-persist; output sanitizer; wheel_spin generation (grounded, no label leak); `POST /admin/tick`. |
| 2 | #24, #25 | SSE endpoint (DB-poll backed); client `EventSource`. |
| 3 | #26 | Always-on daemon (lifespan thread) + fail-closed allowlist scoping + per-student cooldown. |
| 4 | #27 | Graduated `resilience` + `inactive` (sustained/time-based). |
| 5 | #28 | Graduated `explorer` + `iterative`. All five triggers now act. |

**Follow-ups (open):** #22 (sanitizer meta-preamble robustness; also see the §9.3 note
on a stronger production model).

**Enabling in production:** set `TRIGGER_DAEMON_ENABLED=true` and scope with
`PROACTIVE_STUDENT_ALLOWLIST` or `PROACTIVE_CLASS_CODE` (empty = acts on nobody).
