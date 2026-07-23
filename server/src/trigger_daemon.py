"""Always-on background daemon for the proactive push lane (spec §5.2, §8).

Runs in a thread (not an asyncio task) because run_proactive_tick's psycopg / urllib /
openai calls are blocking and would stall the event loop. Each tick: sync logs, then
for every student using the chat, run a proactive tick on their latest session.

SCOPE: the daemon acts on EVERY student it has telemetry for (all_students, i.e. every
distinct student_id in parsed_events). Re-messaging is bounded not by a timer but by
trigger dedup: each (student, session, trigger_type, run_index) fires at most once ever
(agent_triggers UNIQUE), so a student only hears from the agent again when genuinely NEW
behavior trips a trigger. Gated off by default (TRIGGER_DAEMON_ENABLED); when on it
messages real students, so enabling it is a deliberate, authorized act.
"""
import logging
import os
import threading

from src.trigger_service import run_proactive_tick
from src.db import get_latest_session_id_for_student, all_students
from src.log_sync import sync_invite_hub_logs

log = logging.getLogger("trigger_daemon")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def daemon_enabled() -> bool:
    return _env_flag("TRIGGER_DAEMON_ENABLED", False)


def poll_interval_s() -> float:
    return float(os.getenv("TRIGGER_POLL_INTERVAL_S", "20"))


def in_scope_students() -> set[str]:
    """Scope = every student the agent has telemetry for. Runs the agent for everyone,
    not just students who have used the chat."""
    return set(all_students())


def run_daemon_tick() -> dict:
    """One pass over every student with telemetry. Returns {scoped, acted}."""
    students = in_scope_students()
    if not students:  # no telemetry yet -> do nothing, don't even hit prod
        return {"scoped": 0, "acted": []}

    try:
        sync_invite_hub_logs()
    except Exception as error:  # a prod hiccup shouldn't kill the tick
        log.warning("Invite Hub sync failed this tick: %s", error)

    acted = []
    for student in students:
        session_id = get_latest_session_id_for_student(student)
        if not session_id:
            continue
        try:
            result = run_proactive_tick(student, session_id)
        except Exception as error:
            log.warning("proactive tick failed for %s: %s", student, error)
            continue
        acted.extend(result["acted"])
    return {"scoped": len(students), "acted": acted}


# --- lifecycle: a daemon thread driven off the FastAPI lifespan ---
_stop = threading.Event()
_thread: threading.Thread | None = None


def _loop() -> None:
    log.info("trigger daemon started (interval=%ss)", poll_interval_s())
    while not _stop.is_set():
        try:
            run_daemon_tick()
        except Exception as error:
            log.exception("daemon tick error: %s", error)
        _stop.wait(poll_interval_s())


def start_daemon() -> None:
    global _thread
    if not daemon_enabled():
        log.info("trigger daemon disabled (set TRIGGER_DAEMON_ENABLED=true to run)")
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="trigger-daemon", daemon=True)
    _thread.start()


def stop_daemon() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=2)
