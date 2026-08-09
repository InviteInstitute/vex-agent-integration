"""DB-backed test for the newly-wired identity-switch tracker (services/identity).

Seeds a casing flip in parsed_events, runs the tracker, and asserts one switch_events
row is written and that re-running is idempotent. Skips without DATABASE_URL."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a live DATABASE_URL")


def _insert_event(session_id, student_id, event_ts):
    from vex_agent.data.db import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO event_logs.parsed_events
                    (session_id, student_id, class_code, event_ts, event_type, source)
                VALUES (%s, %s, 'AAA', %s, 'runProject', 'test')
                """,
                (session_id, student_id, event_ts),
            )
        conn.commit()


def test_casing_switch_detected_recorded_and_idempotent():
    from vex_agent.data.db import canon_id, get_conn
    from vex_agent.services.identity import track_identity_switches

    session_id = str(uuid4())
    lower = f"cobra_{uuid4().hex[:8]}"  # unique per run -> no cross-test collision
    upper = lower.capitalize()  # same canon, different casing
    canon = canon_id(lower)
    t1 = datetime.now(UTC) - timedelta(minutes=5)
    t2 = t1 + timedelta(minutes=1)

    try:
        _insert_event(session_id, lower, t1)
        # first sight of the student establishes last-seen; no switch yet
        assert track_identity_switches(lower, session_id) == []

        _insert_event(session_id, upper, t2)
        # a newer event under a different casing -> exactly one casing switch
        assert ("casing", lower, upper) in track_identity_switches(upper, session_id)
        # re-running records nothing new (forward-only pointer + ON CONFLICT)
        assert track_identity_switches(upper, session_id) == []

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM event_logs.switch_events "
                    "WHERE student_id=%s AND switch_kind='casing'",
                    (canon,),
                )
                assert cur.fetchone()[0] == 1
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM event_logs.switch_events WHERE student_id=%s", (canon,))
                cur.execute("DELETE FROM event_logs.student_identity WHERE canon_id=%s", (canon,))
                cur.execute(
                    "DELETE FROM event_logs.parsed_events WHERE session_id=%s", (session_id,)
                )
            conn.commit()
