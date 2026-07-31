"""Always-on background daemon for the proactive push lane (spec §5.2, §8).

Runs in a thread (not an asyncio task) because run_proactive_tick's psycopg / urllib /
openai calls are blocking and would stall the event loop. Each tick: sync logs, then
for every student with recent telemetry, run a proactive tick on their latest session.

SCOPE: the daemon acts on every student it has RECENT telemetry for (all_students
with a recency window, default 24h). Re-messaging is bounded not by a timer but by
trigger dedup: each (student, session, trigger_type, run_index) fires at most once ever
(agent_triggers UNIQUE), so a student only hears from the agent again when genuinely NEW
behavior trips a trigger. Gated off by default (TRIGGER_DAEMON_ENABLED); when on it
messages real students, so enabling it is a deliberate, authorized act.

BACKOFF (ported from lm-dashboard/app/pipeline/daemon.py): transient tick failures
(prod hiccup, LLM error) get exponential backoff with a UNHEALTHY log after 5 in a
row; idle ticks (nothing acted on, nothing synced) grow the sleep toward
TRIGGER_IDLE_MAX_S so quiet stretches don't hammer prod. The first sign of activity
snaps the interval back to the base. Unlike lm-dashboard (a supervised process), this
is a background thread with no supervisor to restart it, so non-transient errors are
logged and continued rather than re-raised -- a dead thread would silently stop the
push lane until app restart.
"""
import logging
import os
import random
import threading

from vex_agent.services.proactive import run_proactive_tick
from vex_agent.data.db import get_latest_session_id_for_student, all_students
from vex_agent.services.logsync import sync_invite_hub_logs

log = logging.getLogger("trigger_daemon")

# --- failure backoff tuning (ported from lm-dashboard) ---
_MAX_BACKOFF_S = 30.0
_UNHEALTHY_AFTER = 5


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def daemon_enabled() -> bool:
    return _env_flag("TRIGGER_DAEMON_ENABLED", False)


def poll_interval_s() -> float:
    # Ported from lm-dashboard's PIPELINE_INTERVAL, but not matched 1:1: that
    # daemon only ingests each tick, while this one also walks every in-scope
    # student and can fire an LLM call, so a single busy tick already takes
    # several seconds on its own. 5s reacts ~4x faster than the old flat 20s
    # without the daemon racing ahead of its own tick duration.
    return float(os.getenv("TRIGGER_POLL_INTERVAL_S", "5"))


def idle_max_s() -> float:
    """Ceiling for idle backoff (ported from lm-dashboard's PIPELINE_IDLE_MAX).
    Defaults to 30s -- real headroom above the base interval, so quiet stretches
    actually back off instead of the old default (== base, a no-op ceiling)."""
    return float(os.getenv("TRIGGER_IDLE_MAX_S", "30"))


def student_recency_hours() -> float:
    """Only chase students with an event in the last N hours. Bounds the first-tick
    inactive blast (spec §8). Default 24."""
    return float(os.getenv("TRIGGER_STUDENT_RECENCY_HOURS", "24"))


def in_scope_students() -> set[str]:
    """Scope = every student the agent has RECENT telemetry for. Runs the agent for
    everyone with an event in the recency window, not just students who have used the
    chat."""
    return set(all_students(recency_hours=student_recency_hours()))


def run_daemon_tick() -> dict:
    """One pass over every student with recent telemetry. Returns {scoped, acted}."""
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
    """The tick loop with idle + failure backoff (ported from lm-dashboard)."""
    base = poll_interval_s()
    ceiling = idle_max_s()
    log.info("trigger daemon started (interval=%ss, idle_max=%ss, recency=%sh)",
             base, ceiling, student_recency_hours())

    fails = 0       # consecutive tick failures
    idle = 0        # consecutive idle ticks (nothing to do)
    while not _stop.is_set():
        busy = False
        try:
            result = run_daemon_tick()
            acted = result.get("acted", [])
            busy = bool(acted)
            if acted:
                log.info("tick: acted on %d trigger(s) across %d student(s)",
                         len(acted), result.get("scoped", 0))
            fails = 0  # success resets the failure counter
        except Exception as error:
            fails += 1
            delay = min(_MAX_BACKOFF_S, 0.5 * (2 ** min(fails, 6))) + random.uniform(0, 0.5)
            log.warning("daemon tick failed (%d consecutive): %s -- backoff %.1fs",
                        fails, error, delay)
            if fails >= _UNHEALTHY_AFTER:
                log.error("UNHEALTHY: %d consecutive daemon tick failures", fails)
            _stop.wait(delay)
            continue

        # Idle backoff: while activity is flowing, sleep the base interval; once a
        # tick finds nothing to do, grow the wait exponentially toward idle_max so
        # quiet stretches don't keep hammering prod. The first sign of activity
        # snaps the interval straight back to responsive.
        idle = 0 if busy else idle + 1
        target = base if busy else min(ceiling, base * (2 ** min(idle, 6)))
        _stop.wait(target)


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
