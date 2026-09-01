"""Wires the vendored identity-switch detector (triggers/switches.py) onto the live
proactive tick. Previously the detector, the switch_events table (009), and
db.record_switch existed but nothing on a live path called them.

Each tick, compare a student's newest event identity (spelling + classCode) against the
canonical last-seen state (011 student_identity) and record any casing/class switch. The
last-seen pointer only advances forward in event time, which makes this idempotent and
stops the two spellings of one student from oscillating a switch every tick.

# ponytail: student-level, event-time granularity (latest event vs last-seen). A switch
# is caught on the tick after the new spelling's event lands, not intra-batch at ingest.
# Upgrade path: move detection into the ingest loop for per-event immediacy if needed.
"""

import logging
from uuid import UUID

from learner_models import detect_switches

from vex_agent.data.db import (
    canon_id,
    get_identity_state,
    latest_identity,
    record_switch,
    upsert_identity_state,
)

log = logging.getLogger(__name__)


def track_identity_switches(student_id: str, session_id: str) -> list[tuple]:
    """Detect + persist identity switches for a student's newest event. Returns the
    switches recorded this call (possibly empty)."""
    curr = latest_identity(student_id)
    if curr is None:
        return []
    curr_id, curr_class, curr_ts = curr
    canon = canon_id(curr_id)
    state = get_identity_state(canon)

    recorded: list[tuple] = []
    if state is not None:
        prev_id, prev_class, prev_ts = state
        if curr_ts > prev_ts:
            for kind, from_value, to_value in detect_switches(
                prev_id, prev_class, curr_id, curr_class
            ):
                record_switch(
                    student_id=canon,
                    session_id=UUID(session_id),
                    switch_kind=kind,
                    from_value=from_value,
                    to_value=to_value,
                )
                recorded.append((kind, from_value, to_value))
                log.info("identity switch (%s) for %s: %r -> %r", kind, canon, from_value, to_value)

    upsert_identity_state(canon=canon, student_id=curr_id, class_code=curr_class, event_ts=curr_ts)
    return recorded
