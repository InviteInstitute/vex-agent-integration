"""DB-backed dedupe test for agent_triggers persistence (issue #5).

Skips when DATABASE_URL is unset. Run from server/ with env loaded:
    set -a; . ../.env; set +a
    PYTHONPATH=. ../.venv/bin/python -m pytest tests/test_agent_triggers_db.py
"""
import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs a live DATABASE_URL"
)


def test_insert_dedupes_on_run_index():
    from vex_agent.db import insert_agent_trigger_if_new, get_conn

    session_id = str(uuid4())
    student_id = f"test_{uuid4().hex[:8]}"
    try:
        first = insert_agent_trigger_if_new(
            student_id=student_id, session_id=session_id,
            trigger_type="wheel_spin", run_index=6, detail={"value": "6 identical reruns"},
        )
        second = insert_agent_trigger_if_new(
            student_id=student_id, session_id=session_id,
            trigger_type="wheel_spin", run_index=6, detail={"value": "6 identical reruns"},
        )
        assert first is not None      # first fire inserts
        assert second is None         # same (student, session, type, run_index) is deduped
        # a different run_index is a distinct fire
        third = insert_agent_trigger_if_new(
            student_id=student_id, session_id=session_id,
            trigger_type="wheel_spin", run_index=12, detail=None,
        )
        assert third is not None
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM event_logs.agent_triggers WHERE student_id = %s",
                    (student_id,),
                )


def test_latest_inactive_and_resolve_lifecycle():
    # the re-alert lifecycle: latest_inactive_trigger finds the most recent fire,
    # resolve_open_inactive_triggers closes open ones when the student recovers.
    from vex_agent.db import (
        insert_agent_trigger_if_new, latest_inactive_trigger,
        resolve_open_inactive_triggers, get_conn,
    )

    session_id = str(uuid4())
    student_id = f"test_{uuid4().hex[:8]}"
    try:
        # first inactive fire at run_index -1
        assert latest_inactive_trigger(student_id, session_id) is None
        insert_agent_trigger_if_new(
            student_id=student_id, session_id=session_id,
            trigger_type="inactive", run_index=-1, detail={"value": "idle 5m"},
        )
        row = latest_inactive_trigger(student_id, session_id)
        assert row is not None and row[0] == -1

        # re-alert at run_index -2 (a distinct dedupe key, so it inserts)
        second = insert_agent_trigger_if_new(
            student_id=student_id, session_id=session_id,
            trigger_type="inactive", run_index=-2, detail={"value": "idle 15m"},
        )
        assert second is not None
        row = latest_inactive_trigger(student_id, session_id)
        assert row[0] == -2  # the most recent fire

        # student recovers -> resolve all open inactive triggers
        resolved = resolve_open_inactive_triggers(student_id, session_id)
        assert resolved == 2  # both -1 and -2 were open
        # resolving again is a no-op (nothing open)
        assert resolve_open_inactive_triggers(student_id, session_id) == 0
    finally:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM event_logs.agent_triggers WHERE student_id = %s",
                    (student_id,),
                )
