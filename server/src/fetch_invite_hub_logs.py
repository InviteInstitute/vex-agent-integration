from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only when python-dotenv is unavailable
    load_dotenv = None

DEFAULT_BASE_URL = "https://inviteinstitutehub.org"
DEFAULT_OUTPUT_PATH = Path(__file__).with_name("invite_vex_logs.ndjson")
DEFAULT_STATE_PATH = Path(__file__).with_name("invite_hub_sync_state.json")
DEFAULT_PAGE_SIZE = 500
REQUEST_TIMEOUT_S = 60


def build_query_string(
    *,
    search: str | None = None,
    student_id: str | None = None,
    class_code: str | None = None,
    event_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    params: list[tuple[str, str]] = []
    if offset is not None:
        params.append(("offset", str(offset)))
    if limit is not None:
        params.append(("limit", str(limit)))
    if search:
        params.append(("search", search))
    if student_id:
        params.append(("studentID", student_id))
    if class_code:
        params.append(("classCode", class_code))
    if event_type:
        params.append(("eventType", event_type))
    if date_from:
        params.append(("dateFrom", date_from))
    if date_to:
        params.append(("dateTo", date_to))
    return parse.urlencode(params)


def load_local_env() -> None:
    if load_dotenv is not None:
        load_dotenv()
        return

    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        normalized = line.strip()
        if not normalized or normalized.startswith("#") or "=" not in normalized:
            continue
        key, value = normalized.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    accept: str = "application/json",
) -> bytes:
    print(f"[fetch_invite_hub_logs] {method} {url}", flush=True)
    headers = {
        "Accept": accept,
        "User-Agent": "senior-project-log-fetcher/1.0",
    }
    data: bytes | None = None
    if token:
        headers["Authorization"] = f"Token {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as response:
            return response.read()
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace").strip()
        if details:
            raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {details}") from exc
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    raw = request_bytes(url, method=method, token=token, payload=payload)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{method} {url} returned invalid JSON") from exc


def get_auth_token(base_url: str) -> str:
    env_token = os.getenv("INVITE_HUB_TOKEN")
    if env_token:
        print("[fetch_invite_hub_logs] Using INVITE_HUB_TOKEN from environment.", flush=True)
        return env_token

    username = os.getenv("INVITE_HUB_USERNAME")
    password = os.getenv("INVITE_HUB_PASSWORD")
    if not username or not password:
        raise RuntimeError(
            "Set INVITE_HUB_TOKEN or both INVITE_HUB_USERNAME and INVITE_HUB_PASSWORD."
        )

    payload = request_json(
        f"{base_url}/api/token/",
        method="POST",
        payload={"username": username, "password": password},
    )
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("Invite Hub login succeeded but no token was returned.")
    return token


def download_vex_logs(base_url: str, token: str, query_string: str) -> str:
    url = f"{base_url}/api/rabbitmq/download/vex-logs/"
    if query_string:
        url = f"{url}?{query_string}"
    raw = request_bytes(
        url,
        token=token,
        accept="application/x-ndjson, application/json, text/plain;q=0.9, */*;q=0.8",
    )
    return raw.decode("utf-8", errors="replace")


def fetch_vex_logs_paged(
    base_url: str,
    token: str,
    query_string: str,
    *,
    page_size: int,
    max_records: int | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0

    while True:
        page_query = build_query_string(offset=offset, limit=page_size)
        if query_string:
            page_query = f"{page_query}&{query_string}"
        url = f"{base_url}/api/rabbitmq/vex_logs/?{page_query}"

        payload = request_json(url, token=token)
        if not isinstance(payload, dict):
            raise RuntimeError("Paged VEX logs response was not an object.")

        batch = payload.get("results")
        if not isinstance(batch, list):
            raise RuntimeError("Paged VEX logs response did not include a results list.")

        dict_batch = [item for item in batch if isinstance(item, dict)]
        if len(dict_batch) != len(batch):
            raise RuntimeError("Paged VEX logs response included non-object records.")

        records.extend(dict_batch)
        if max_records is not None and len(records) >= max_records:
            return records[:max_records]
        if len(batch) < page_size:
            return records
        offset += page_size


def parse_source_log_id(record: dict[str, Any]) -> int:
    source_log_id = record.get("id")
    if not isinstance(source_log_id, int):
        raise RuntimeError("Fetched log record did not include an integer id.")
    return source_log_id


def parse_event_time(record: dict[str, Any]) -> datetime | None:
    """The event's received timestamp as an aware UTC datetime, or None. Prod's
    serializer shipped the key misspelled as 'recieved_at'; accept the corrected
    'received_at' too (matches lm-dashboard, which reads the same API)."""
    raw = record.get("recieved_at") or record.get("received_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read_sync_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Sync state file at {path} is not a JSON object.")
    return payload


def write_sync_state(
    path: Path, last_source_log_id: int, last_event_time: str | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_source_log_id": last_source_log_id,
        "last_event_time": last_event_time,  # ISO ts of the newest event; drives dateFrom
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def fetch_head_log_id(base_url: str, token: str, query_string: str) -> int | None:
    page_query = build_query_string(offset=0, limit=1)
    if query_string:
        page_query = f"{page_query}&{query_string}"
    payload = request_json(f"{base_url}/api/rabbitmq/vex_logs/?{page_query}", token=token)
    if not isinstance(payload, dict):
        raise RuntimeError("Head fetch response was not an object.")
    batch = payload.get("results")
    if not isinstance(batch, list):
        raise RuntimeError("Head fetch response did not include a results list.")
    if not batch:
        return None
    if not isinstance(batch[0], dict):
        raise RuntimeError("Head fetch response included a non-object record.")
    return parse_source_log_id(batch[0])


def fetch_vex_logs_incremental(
    base_url: str,
    token: str,
    query_string: str,
    *,
    page_size: int,
    last_source_log_id: int | None,
    date_from: str | None = None,
) -> list[dict[str, Any]]:
    # date_from: server-side dateFrom filter (lm-dashboard's approach) so a drain reads
    # only events at/after the cursor instead of paging all history. The existing
    # last_source_log_id filter below still dedupes the small overlap window.
    records: list[dict[str, Any]] = []
    offset = 0
    seen_ids: set[int] = set()

    while True:
        print(
            "[fetch_invite_hub_logs] Fetching incremental page",
            f"offset={offset}",
            f"page_size={page_size}",
            f"last_source_log_id={last_source_log_id}",
            f"date_from={date_from}",
            flush=True,
        )
        page_query = build_query_string(offset=offset, limit=page_size, date_from=date_from)
        if query_string:
            page_query = f"{page_query}&{query_string}"
        payload = request_json(f"{base_url}/api/rabbitmq/vex_logs/?{page_query}", token=token)
        if not isinstance(payload, dict):
            raise RuntimeError("Incremental VEX logs response was not an object.")

        batch = payload.get("results")
        if not isinstance(batch, list):
            raise RuntimeError("Incremental VEX logs response did not include a results list.")
        if not batch:
            print("[fetch_invite_hub_logs] No batch results returned.", flush=True)
            return records

        dict_batch: list[dict[str, Any]] = []
        batch_ids: list[int] = []
        for item in batch:
            if not isinstance(item, dict):
                raise RuntimeError("Incremental VEX logs response included a non-object record.")
            dict_batch.append(item)
            batch_ids.append(parse_source_log_id(item))

        is_descending = all(prev > curr for prev, curr in zip(batch_ids, batch_ids[1:]))
        is_ascending = all(prev < curr for prev, curr in zip(batch_ids, batch_ids[1:]))

        if is_descending:
            for item, source_log_id in zip(dict_batch, batch_ids):
                if last_source_log_id is not None and source_log_id <= last_source_log_id:
                    return records
                if source_log_id in seen_ids:
                    continue
                records.append(item)
                seen_ids.add(source_log_id)
        else:
            for item, source_log_id in sorted(
                zip(dict_batch, batch_ids),
                key=lambda pair: pair[1],
                reverse=True,
            ):
                if last_source_log_id is not None and source_log_id <= last_source_log_id:
                    continue
                if source_log_id in seen_ids:
                    continue
                records.append(item)
                seen_ids.add(source_log_id)

            if is_ascending and last_source_log_id is not None and max(batch_ids) <= last_source_log_id:
                offset += page_size
                if len(batch) < page_size:
                    return records
                continue

        if len(batch) < page_size:
            print(
                f"[fetch_invite_hub_logs] Final incremental batch received with {len(batch)} records.",
                flush=True,
            )
            return records
        offset += page_size


def write_text_output(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def serialize_records_as_ndjson(records: list[dict[str, Any]]) -> str:
    if not records:
        return ""
    return "".join(json.dumps(record) + "\n" for record in records)


def count_download_records(text: str) -> int:
    normalized = text.lstrip()
    if not normalized:
        return 0
    if normalized.startswith("["):
        payload = json.loads(normalized)
        if isinstance(payload, list):
            return len(payload)
    return sum(1 for line in text.splitlines() if line.strip())


def load_parse_helpers() -> tuple[Any, Any, Any]:
    try:
        from src.parse_event_logs import insert_rows, parse_records, parse_text_blob
    except ModuleNotFoundError:
        try:
            from server.src.parse_event_logs import insert_rows, parse_records, parse_text_blob
        except ModuleNotFoundError:
            from parse_event_logs import insert_rows, parse_records, parse_text_blob

    return insert_rows, parse_records, parse_text_blob


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch VEX logs from Invite Institute Hub and optionally insert them into Postgres."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path to save fetched logs as NDJSON or JSON text.",
    )
    parser.add_argument(
        "--method",
        choices=("download", "paged"),
        default="download",
        help="Use the bulk download endpoint or fetch paginated results.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help="Page size for paged mode.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Optional cap for paged mode.",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Fetch only records newer than the last_source_log_id stored in the sync state file.",
    )
    parser.add_argument(
        "--seed-head",
        action="store_true",
        help="Record the current newest upstream log id without downloading any logs.",
    )
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE_PATH),
        help="Path to the incremental sync state JSON file.",
    )
    parser.add_argument("--search", default=None, help="Free-text search filter.")
    parser.add_argument("--student-id", default=None, help="Filter by student ID.")
    parser.add_argument("--class-code", default=None, help="Filter by class code.")
    parser.add_argument("--event-type", default=None, help="Filter by event type.")
    parser.add_argument(
        "--date-from",
        default=None,
        help="Filter lower bound, e.g. 2026-03-01T00:00 or 2026-03-01T00:00:00Z.",
    )
    parser.add_argument(
        "--date-to",
        default=None,
        help="Filter upper bound, e.g. 2026-03-31T23:59 or 2026-03-31T23:59:59Z.",
    )
    parser.add_argument(
        "--insert",
        action="store_true",
        help="Parse the fetched logs and insert them into event_logs.parsed_events.",
    )
    args = parser.parse_args()

    if args.page_size < 1:
        raise SystemExit("--page-size must be at least 1.")
    if args.max_records is not None and args.max_records < 1:
        raise SystemExit("--max-records must be at least 1 when provided.")
    if args.incremental and args.max_records is not None:
        raise SystemExit("--max-records is not supported with --incremental.")

    load_local_env()
    base_url = os.getenv("INVITE_HUB_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    print(f"[fetch_invite_hub_logs] Base URL: {base_url}", flush=True)
    token = get_auth_token(base_url)
    print("[fetch_invite_hub_logs] Authentication complete.", flush=True)

    filter_query = build_query_string(
        search=args.search,
        student_id=args.student_id,
        class_code=args.class_code,
        event_type=args.event_type,
        date_from=args.date_from,
        date_to=args.date_to,
    )
    state_path = Path(args.state_file)

    if args.seed_head:
        head_log_id = fetch_head_log_id(base_url, token, filter_query)
        if head_log_id is None:
            print("No logs were available, so the sync state was not updated.")
            return
        write_sync_state(state_path, head_log_id)
        print(f"Seeded sync state at {state_path} with last_source_log_id={head_log_id}.")
        return

    output_path = Path(args.output)
    insert_rows_fn = None
    parse_records_fn = None
    parse_text_blob_fn = None
    if args.insert:
        insert_rows_fn, parse_records_fn, parse_text_blob_fn = load_parse_helpers()

    if args.incremental:
        state = read_sync_state(state_path)
        last_source_log_id = state.get("last_source_log_id")
        if last_source_log_id is not None and not isinstance(last_source_log_id, int):
            raise RuntimeError("Sync state last_source_log_id must be an integer.")

        raw_records = fetch_vex_logs_incremental(
            base_url,
            token,
            filter_query,
            page_size=args.page_size,
            last_source_log_id=last_source_log_id,
        )
        print(f"[fetch_invite_hub_logs] Incremental fetch returned {len(raw_records)} records.", flush=True)
        text = serialize_records_as_ndjson(list(reversed(raw_records)))
        write_text_output(output_path, text)
        fetched_count = len(raw_records)
        parsed_rows = parse_records_fn(raw_records, output_path.name) if args.insert else None

        if raw_records:
            newest_source_log_id = max(parse_source_log_id(record) for record in raw_records)
            write_sync_state(state_path, newest_source_log_id)
            print(
                f"Saved {fetched_count} new log records to {output_path} "
                f"and advanced sync state to {newest_source_log_id}."
            )
        else:
            print(
                f"No new log records were found after last_source_log_id={last_source_log_id}. "
                f"State file remains {state_path}."
            )
    elif args.method == "download":
        text = download_vex_logs(base_url, token, filter_query)
        write_text_output(output_path, text)
        fetched_count = count_download_records(text)
        parsed_rows = parse_text_blob_fn(text, output_path.name) if args.insert else None
        print(f"Saved {fetched_count} fetched log records to {output_path}.")
    else:
        raw_records = fetch_vex_logs_paged(
            base_url,
            token,
            filter_query,
            page_size=args.page_size,
            max_records=args.max_records,
        )
        text = serialize_records_as_ndjson(raw_records)
        write_text_output(output_path, text)
        fetched_count = len(raw_records)
        parsed_rows = parse_records_fn(raw_records, output_path.name) if args.insert else None
        print(f"Saved {fetched_count} fetched log records to {output_path}.")
    if parsed_rows is not None:
        inserted = insert_rows_fn(parsed_rows)
        print(f"Inserted {inserted} parsed rows into event_logs.parsed_events.")


if __name__ == "__main__":
    main()
