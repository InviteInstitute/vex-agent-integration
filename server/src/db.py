import os
from uuid import UUID

import psycopg
from psycopg.types.json import Json
from dotenv import load_dotenv

load_dotenv()  # once at import, not on every query


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


def all_students() -> list[str]:
    """Every student the agent has telemetry for -- the daemon's scope when it runs
    for everyone (not just the chat roster). Sourced from synced parsed_events.
    ponytail: all-time; add a `WHERE event_ts > NOW() - INTERVAL '1 day'` window if
    the daemon should only chase currently-active students, not every historical id."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT student_id FROM event_logs.parsed_events")
            return [row[0] for row in cur.fetchall()]
