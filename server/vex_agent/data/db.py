import os
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from dotenv import load_dotenv

# Domain models + pure mappers this data layer returns/persists (one-way data -> domain;
# metrics has no app-level top-level imports, so this can't cycle at import time).
from vex_agent.domain.metrics import (
    CurrentStateSnapshot,
    EventRecord,
    canonical_playground_from_payload,
    parse_dt,
)

load_dotenv()  # once at import, not on every query


def canon_id(sid: str | None) -> str:
    """Canonical identity key for a studentID: whitespace- and case-folded (ported
    from lm-dashboard). studentIDs are handles sometimes typed in different casing
    (cobra3 vs Cobra3); folding here makes the system treat those spellings as one."""
    return (sid or "").strip().lower()


def get_conn() -> psycopg.Connection:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(database_url)


def insert_agent_trigger_if_new(
    *,
    student_id: str,
    session_id: str,
    trigger_type: str,
    run_index: int,
    detail: dict | None = None,
) -> int | None:
    """Insert a detected trigger, deduped on (student, session, type, run_index).
    Returns the new row id, or None when the trigger already existed. Detection is
    deterministic, so re-running a pass over the same events never double-fires."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO event_logs.agent_triggers (
                    student_id, session_id, trigger_type, run_index, detail_json
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (student_id, session_id, trigger_type, run_index)
                DO NOTHING
                RETURNING id
                """,
                (student_id, session_id, trigger_type, run_index,
                 Json(detail) if detail is not None else None),
            )
            row = cur.fetchone()
            return row[0] if row else None


def mark_agent_trigger_acted(*, trigger_id: int, response_id: UUID) -> None:
    """Record that the agent acted on a trigger and which proactive response it produced."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE event_logs.agent_triggers
                SET acted = TRUE, response_id = %s
                WHERE id = %s
                """,
                (response_id, trigger_id),
            )


def latest_inactive_trigger(student_id: str, session_id: str) -> tuple[int, datetime] | None:
    """The most recent inactive trigger row for a session: (run_index, fired_at).
    Used by the re-alert logic to decide whether a new inactive fire is due yet
    (RE_ALERT_SECONDS since fired_at) or should be suppressed. Returns None when
    the session has never had an inactive fire."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_index, fired_at
                FROM event_logs.agent_triggers
                WHERE student_id = %s AND session_id = %s AND trigger_type = 'inactive'
                ORDER BY fired_at DESC, id DESC
                LIMIT 1
                """,
                (student_id, session_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return (row[0], row[1])


def resolve_open_inactive_triggers(student_id: str, session_id: str) -> int:
    """Close every open (resolved_at IS NULL) inactive trigger for a session. Called
    when the student is no longer idle (they recovered). Returns the count resolved."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE event_logs.agent_triggers
                SET resolved_at = NOW()
                WHERE student_id = %s AND session_id = %s
                  AND trigger_type = 'inactive' AND resolved_at IS NULL
                """,
                (student_id, session_id),
            )
            return cur.rowcount


def insert_message(
    *,
    session_id: UUID,
    student_id: str,
    role: str,
    message_text: str,
    feedback_class: str | None = None,
    response_id: UUID | None = None,
    origin: str = "reactive",
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat.messages (
                    session_id,
                    student_id,
                    role,
                    message_text,
                    feedback_class,
                    response_id,
                    origin
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    student_id,
                    role,
                    message_text,
                    feedback_class,
                    response_id,
                    origin,
                ),
            )


def insert_message_feedback(
    *,
    message_id: int,
    student_id: str,
    thumb: str,
    comment: str | None = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat.message_feedback (
                    message_id,
                    student_id,
                    thumb,
                    comment
                )
                VALUES (%s, %s, %s, %s)
                """,
                (message_id, student_id, thumb, comment),
            )


def get_message_id_for_response(*, response_id: UUID, student_id: str) -> int | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM chat.messages
                WHERE response_id = %s
                  AND student_id = %s
                  AND role = 'assistant'
                LIMIT 1
                """,
                (response_id, student_id),
            )
            row = cur.fetchone()
            return row[0] if row else None


def get_latest_session_id_for_student(student_id: str) -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT session_id
                FROM event_logs.parsed_events
                WHERE student_id = %s
                ORDER BY event_ts DESC, id DESC
                LIMIT 1
                """,
                (student_id,),
            )
            row = cur.fetchone()
            return str(row[0]) if row else None


def latest_proactive_message_id(student_id: str) -> int:
    """The newest proactive-message id for a student, or 0 if none. The SSE stream
    starts here so a fresh connection delivers only messages pushed after it opens,
    not the whole history."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(MAX(id), 0)
                FROM chat.messages
                WHERE student_id = %s AND origin = 'proactive'
                """,
                (student_id,),
            )
            return cur.fetchone()[0]


def get_proactive_messages_after(student_id: str, after_id: int) -> list[dict]:
    """Proactive messages for a student with id > after_id, oldest first, each carrying
    the trigger that caused it. The shared response_id links a message to its
    agent_triggers row; LEFT JOIN so a message with no matching trigger still comes
    through (trigger_type = None). Backs the SSE poll."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.id, m.message_text, m.response_id, m.created_at,
                       t.trigger_type, t.detail_json->>'value' AS trigger_why
                FROM chat.messages m
                LEFT JOIN event_logs.agent_triggers t ON t.response_id = m.response_id
                WHERE m.student_id = %s AND m.origin = 'proactive' AND m.id > %s
                ORDER BY m.id ASC
                """,
                (student_id, after_id),
            )
            return [
                {
                    "id": row[0],
                    "message_text": row[1],
                    "response_id": str(row[2]) if row[2] else None,
                    "created_at": row[3].isoformat() if row[3] else None,
                    "trigger_type": row[4],
                    "trigger_why": row[5],
                }
                for row in cur.fetchall()
            ]


def all_students(recency_hours: float | None = None) -> list[str]:
    """Every student the agent has telemetry for -- the daemon's scope when it runs
    for everyone (not just the chat roster). Sourced from synced parsed_events.

    recency_hours: when set, only students with an event within the last N hours
    are returned. This bounds the daemon's first-tick blast radius (spec §8). The
    daemon passes TRIGGER_STUDENT_RECENCY_HOURS (default 24); pass None for the
    all-time view.

    Returns DISTINCT spellings as stored (NOT case-folded) so each casing variant
    the daemon sees maps back to the same student_id rows. Use canon_id() to fold
    when you need one key per student."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            if recency_hours is not None:
                cur.execute(
                    "SELECT DISTINCT student_id FROM event_logs.parsed_events "
                    "WHERE event_ts > NOW() - (%s * INTERVAL '1 hour')",
                    (recency_hours,),
                )
            else:
                cur.execute("SELECT DISTINCT student_id FROM event_logs.parsed_events")
            return [row[0] for row in cur.fetchall()]


def record_switch(
    *, student_id: str, session_id: str, switch_kind: str, from_value: str | None, to_value: str | None,
) -> None:
    """Persist an identity switch (casing flip or classCode change) to switch_events.
    Vendored table from lm-dashboard; additive -- the agent does not act on this yet,
    but researchers can query the log."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO event_logs.switch_events
                    (student_id, session_id, switch_kind, from_value, to_value)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (student_id, session_id, switch_kind, from_value, to_value)
                DO NOTHING
                """,
                (student_id, session_id, switch_kind, from_value, to_value),
            )


def latest_identity(student_id: str) -> tuple[str, str | None, datetime] | None:
    """The (student_id spelling, class_code, event_ts) of this spelling's most recent
    event, or None if it has no telemetry."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT student_id, class_code, event_ts
                FROM event_logs.parsed_events
                WHERE student_id = %s
                ORDER BY event_ts DESC, id DESC
                LIMIT 1
                """,
                (student_id,),
            )
            row = cur.fetchone()
            return (row[0], row[1], row[2]) if row else None


def get_identity_state(canon: str) -> tuple[str, str | None, datetime] | None:
    """Last-seen (student_id, class_code, event_ts) for a canonical student, or None."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT last_student_id, last_class_code, last_event_ts
                FROM event_logs.student_identity
                WHERE canon_id = %s
                """,
                (canon,),
            )
            row = cur.fetchone()
            return (row[0], row[1], row[2]) if row else None


def upsert_identity_state(
    *, canon: str, student_id: str, class_code: str | None, event_ts: datetime,
) -> None:
    """Advance a canonical student's last-seen identity -- forward in event time only,
    so re-processing an older or equal event can't move the pointer backward."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO event_logs.student_identity
                    (canon_id, last_student_id, last_class_code, last_event_ts)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (canon_id) DO UPDATE SET
                    last_student_id = EXCLUDED.last_student_id,
                    last_class_code = EXCLUDED.last_class_code,
                    last_event_ts = EXCLUDED.last_event_ts,
                    updated_at = NOW()
                WHERE event_logs.student_identity.last_event_ts < EXCLUDED.last_event_ts
                """,
                (canon, student_id, class_code, event_ts),
            )


def proactive_rev() -> int:
    """The current revision counter for the 'proactive' channel (O(1) read). The SSE
    stream uses this as a cheap "did anything change?" gate before polling
    chat.messages. Vendored from lm-dashboard's channel_rev pattern."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT rev FROM chat.channel_rev WHERE channel = 'proactive'")
            row = cur.fetchone()
            return row[0] if row else 0


def to_event_record(row: dict[str, Any]) -> EventRecord:
    playground_data_json = (
        row.get("playground_data_json") if isinstance(row.get("playground_data_json"), dict) else None
    )
    return EventRecord(
        id=row.get("id"),
        session_id=str(row["session_id"]),
        student_id=str(row["student_id"]),
        event_ts=parse_dt(row["event_ts"]),
        event_type=str(row["event_type"]),
        playground=canonical_playground_from_payload(
            row.get("playground"),
            row.get("project_json"),
            playground_data_json,
        ),
        project_json=row.get("project_json") if isinstance(row.get("project_json"), dict) else None,
        block_event_data_json=row.get("block_event_data_json")
        if isinstance(row.get("block_event_data_json"), dict)
        else None,
        playground_data_json=playground_data_json,
        error_message=row.get("error_message"),
    )


def fetch_events_from_db(student_id: str, session_id: str) -> list[EventRecord]:
    sql = """
    SELECT
        id,
        session_id,
        student_id,
        event_ts,
        event_type,
        playground,
        project_json,
        block_event_data_json,
        playground_data_json,
        error_message
    FROM event_logs.parsed_events
    WHERE student_id = %(student_id)s
      AND session_id = %(session_id)s
    ORDER BY event_ts, id
    """
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, {"student_id": student_id, "session_id": session_id})
            rows = cur.fetchall()
    events = [to_event_record(dict(row)) for row in rows]
    return [event for event in events if event.playground is not None]


def upsert_snapshot(snapshot: CurrentStateSnapshot) -> None:
    sql = """
    INSERT INTO current_state.state_snapshots (
        session_id,
        student_id,
        time_on_task_s,
        action_level,
        progress_pct,
        direction,
        cognition,
        persistence,
        computed_from_event_id_min,
        computed_from_event_id_max,
        created_at
    )
    VALUES (
        %(session_id)s,
        %(student_id)s,
        %(time_on_task_s)s,
        %(action_level)s,
        %(progress_pct)s,
        %(direction)s,
        %(cognition)s,
        %(persistence)s,
        %(computed_from_event_id_min)s,
        %(computed_from_event_id_max)s,
        %(created_at)s
    )
    ON CONFLICT (session_id, student_id)
    DO UPDATE SET
        time_on_task_s = EXCLUDED.time_on_task_s,
        action_level = EXCLUDED.action_level,
        progress_pct = EXCLUDED.progress_pct,
        direction = EXCLUDED.direction,
        cognition = EXCLUDED.cognition,
        persistence = EXCLUDED.persistence,
        computed_from_event_id_min = EXCLUDED.computed_from_event_id_min,
        computed_from_event_id_max = EXCLUDED.computed_from_event_id_max,
        created_at = EXCLUDED.created_at
    """
    payload = snapshot.to_dict()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, payload)
