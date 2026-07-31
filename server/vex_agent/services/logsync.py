from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

# Rewind the dateFrom cursor a hair so an event landing on the boundary is never
# skipped; the last_source_log_id filter drops the re-fetched duplicates.
SYNC_OVERLAP_SECONDS = 2

from vex_agent.ingest.fetch_invite_hub_logs import (
    DEFAULT_BASE_URL,
    DEFAULT_PAGE_SIZE,
    DEFAULT_STATE_PATH,
    build_query_string,
    clear_cached_token,
    fetch_vex_logs_incremental,
    get_auth_token,
    load_local_env,
    parse_source_log_id,
    parse_event_time,
    read_sync_state,
    write_sync_state,
)
from vex_agent.ingest.parse_event_logs import insert_rows, parse_records


def sync_invite_hub_logs(*, student_id: str | None = None) -> int:
    load_local_env()
    base_url = os.getenv("INVITE_HUB_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    token = get_auth_token(base_url)
    state_path = Path(DEFAULT_STATE_PATH)
    state = read_sync_state(state_path)
    last_source_log_id = state.get("last_source_log_id")
    if last_source_log_id is not None and not isinstance(last_source_log_id, int):
        raise RuntimeError("Sync state last_source_log_id must be an integer.")

    # Filter server-side by the timestamp cursor (lm-dashboard's dateFrom trick) so a
    # drain reads only new events, not the whole history. Rewind by the overlap window.
    last_event_time = state.get("last_event_time")
    date_from = None
    if isinstance(last_event_time, str) and last_event_time:
        cursor = datetime.fromisoformat(last_event_time) - timedelta(seconds=SYNC_OVERLAP_SECONDS)
        date_from = cursor.isoformat()

    query_string = build_query_string(student_id=student_id)
    try:
        raw_records = fetch_vex_logs_incremental(
            base_url, token, query_string,
            page_size=DEFAULT_PAGE_SIZE, last_source_log_id=last_source_log_id, date_from=date_from,
        )
    except RuntimeError as exc:
        # The cached token (get_auth_token) is a static key reused across calls;
        # if the Hub ever actually rejects it, drop the cache and log in fresh once.
        if "HTTP 401" not in str(exc) and "HTTP 403" not in str(exc):
            raise
        clear_cached_token()
        token = get_auth_token(base_url)
        raw_records = fetch_vex_logs_incremental(
            base_url, token, query_string,
            page_size=DEFAULT_PAGE_SIZE, last_source_log_id=last_source_log_id, date_from=date_from,
        )
    if not raw_records:
        return 0

    parsed_rows = parse_records(raw_records, "invite_hub_incremental")
    insert_rows(parsed_rows)
    newest_source_log_id = max(parse_source_log_id(record) for record in raw_records)
    event_times = [parse_event_time(record) for record in raw_records]
    newest = max((t for t in event_times if t is not None), default=None)
    newest_event_time = newest.isoformat() if newest else last_event_time
    write_sync_state(state_path, newest_source_log_id, newest_event_time)
    return len(raw_records)
