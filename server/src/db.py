import os
from uuid import UUID

import psycopg
from psycopg.types.json import Json
from dotenv import load_dotenv


def get_conn() -> psycopg.Connection:
    load_dotenv()
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
    """Proactive messages for a student with id > after_id, oldest first. Backs the
    SSE poll (idx_messages_origin_student_created_at supports the filter)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, message_text, response_id, created_at
                FROM chat.messages
                WHERE student_id = %s AND origin = 'proactive' AND id > %s
                ORDER BY id ASC
                """,
                (student_id, after_id),
            )
            return [
                {
                    "id": row[0],
                    "message_text": row[1],
                    "response_id": str(row[2]) if row[2] else None,
                    "created_at": row[3].isoformat() if row[3] else None,
                }
                for row in cur.fetchall()
            ]


def last_proactive_message_at(student_id: str):
    """Timestamp of the most recent proactive message to a student, or None.
    Backs the daemon's per-student cooldown."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(created_at)
                FROM chat.messages
                WHERE student_id = %s AND origin = 'proactive'
                """,
                (student_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None


def students_in_class(class_code: str) -> list[str]:
    """Distinct student ids seen in a class, for allowlist-by-class scoping."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT student_id
                FROM event_logs.parsed_events
                WHERE class_code = %s
                """,
                (class_code,),
            )
            return [row[0] for row in cur.fetchall()]
