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
    from src.db import insert_agent_trigger_if_new, get_conn

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
