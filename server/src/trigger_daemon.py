"""Always-on background daemon for the proactive push lane (spec §5.2, §8).

Runs in a thread (not an asyncio task) because run_proactive_tick's psycopg / urllib /
openai calls are blocking and would stall the event loop. Each tick: sync logs, then
for every IN-SCOPE student not in cooldown, run a proactive tick on their latest
session.

SAFETY (not optional): the daemon acts only on an allowlist and never on the whole
prod firehose. An empty/unset allowlist means it acts on NOBODY (fail closed). A
per-student cooldown stops an oscillating student from being messaged repeatedly.
Gated off by default (TRIGGER_DAEMON_ENABLED).
"""
import logging
import os
import threading
from datetime import datetime, timezone

from src.trigger_service import run_proactive_tick
from src.db import (
    get_latest_session_id_for_student, last_proactive_message_at, students_in_class,
)
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


def cooldown_s() -> float:
    return float(os.getenv("PROACTIVE_COOLDOWN_S", "240"))


def in_scope_students() -> set[str]:
    """Fail-closed allowlist: the union of PROACTIVE_STUDENT_ALLOWLIST (a comma list)
    and the roster of PROACTIVE_CLASS_CODE. Empty/unset -> empty set -> act on nobody.
    The daemon NEVER defaults to 'everyone in prod'."""
    students: set[str] = set()
    raw_allowlist = os.getenv("PROACTIVE_STUDENT_ALLOWLIST", "")
    students.update(s.strip() for s in raw_allowlist.split(",") if s.strip())
    class_code = os.getenv("PROACTIVE_CLASS_CODE", "").strip()
    if class_code:
        students.update(students_in_class(class_code))
    return students


def is_in_cooldown(last_at, now: datetime, cooldown_seconds: float) -> bool:
    """True if a proactive message went out within the cooldown window."""
    if last_at is None:
        return False
    return (now - last_at).total_seconds() < cooldown_seconds


def run_daemon_tick() -> dict:
    """One pass over the in-scope roster. Returns {scoped, skipped_cooldown, acted}."""
    students = in_scope_students()
    if not students:  # fail-closed: nobody scoped -> do nothing, don't even hit prod
        return {"scoped": 0, "skipped_cooldown": 0, "acted": []}

    try:
        sync_invite_hub_logs()
    except Exception as error:  # a prod hiccup shouldn't kill the tick
        log.warning("Invite Hub sync failed this tick: %s", error)

    now = datetime.now(timezone.utc)
    cooldown = cooldown_s()
    acted, skipped = [], 0
    for student in students:
        if is_in_cooldown(last_proactive_message_at(student), now, cooldown):
            skipped += 1
            continue
        session_id = get_latest_session_id_for_student(student)
        if not session_id:
            continue
        try:
            result = run_proactive_tick(student, session_id)
        except Exception as error:
            log.warning("proactive tick failed for %s: %s", student, error)
            continue
        acted.extend(result["acted"])
    return {"scoped": len(students), "skipped_cooldown": skipped, "acted": acted}


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
