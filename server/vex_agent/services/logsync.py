from __future__ import annotations

import os
from datetime import timedelta

# Rewind the dateFrom cursor a hair so an event landing on the boundary is never
# skipped; the last_source_log_id filter (and the ON CONFLICT idempotency on
# source_log_id) drop the re-fetched duplicates.
SYNC_OVERLAP_SECONDS = 2

from vex_agent.data.db import get_ingest_cursor, save_ingest_cursor
from vex_agent.ingest.fetch_invite_hub_logs import (
    DEFAULT_BASE_URL,
    DEFAULT_PAGE_SIZE,
    build_query_string,
    clear_cached_token,
    fetch_vex_logs_incremental,
    get_auth_token,
    load_local_env,
    parse_event_time,
    parse_source_log_id,
)
from vex_agent.ingest.parse_event_logs import insert_rows, parse_records


def sync_invite_hub_logs(*, student_id: str | None = None, advance_cursor: bool = True) -> int:
    """Pull new Invite Hub logs into parsed_events, incrementally from the DB cursor
    (event_logs.ingest_cursor, migration 013 -- replaced the old bind-mounted JSON
    file that drifted from its mount path and drove the duplicate mess in 012).

    The cursor is the single source of truth for how far ingestion has progressed.
    Only full-catalog syncs advance it: the trigger daemon and the boot warm-up call
    with advance_cursor=True (the default). Per-student freshness fetches from the
    request path pass advance_cursor=False -- they pull one student's newest events
    for immediate feedback but must NOT move the global cursor, or they'd skip other
    students' unsynced rows. Inserts are idempotent (ON CONFLICT on source_log_id),
    so a cursor-neutral fetch can never create duplicates.
    """
    load_local_env()
    base_url = os.getenv("INVITE_HUB_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    token = get_auth_token(base_url)

    cursor = get_ingest_cursor()
    last_source_log_id = cursor.get("last_source_log_id")
    last_event_dt = cursor.get("last_event_time")  # tz-aware datetime | None

    # Filter server-side by the timestamp cursor (lm-dashboard's dateFrom trick) so a
    # drain reads only new events, not the whole history. Rewind by the overlap window.
    date_from = None
    if last_event_dt is not None:
        date_from = (last_event_dt - timedelta(seconds=SYNC_OVERLAP_SECONDS)).isoformat()

    query_string = build_query_string(student_id=student_id)
    try:
        raw_records = fetch_vex_logs_incremental(
            base_url,
            token,
            query_string,
            page_size=DEFAULT_PAGE_SIZE,
            last_source_log_id=last_source_log_id,
            date_from=date_from,
        )
    except RuntimeError as exc:
        # The cached token (get_auth_token) is a static key reused across calls;
        # if the Hub ever actually rejects it, drop the cache and log in fresh once.
        if "HTTP 401" not in str(exc) and "HTTP 403" not in str(exc):
            raise
        clear_cached_token()
        token = get_auth_token(base_url)
        raw_records = fetch_vex_logs_incremental(
            base_url,
            token,
            query_string,
            page_size=DEFAULT_PAGE_SIZE,
            last_source_log_id=last_source_log_id,
            date_from=date_from,
        )
    if not raw_records:
        return 0

    parsed_rows = parse_records(raw_records, "invite_hub_incremental")
    insert_rows(parsed_rows)

    if advance_cursor:
        newest_source_log_id = max(parse_source_log_id(record) for record in raw_records)
        event_times = [parse_event_time(record) for record in raw_records]
        newest = max((t for t in event_times if t is not None), default=last_event_dt)
        save_ingest_cursor(newest_source_log_id, newest)
    return len(raw_records)
