import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from vex_agent.data.db import get_conn

_last_skip_summary: dict[str, int] = {}


def parse_iso_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    # normalize trailing Z for Python's fromisoformat compatibility
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return value
    return dt.astimezone(UTC).isoformat()


def parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def parse_json_string_or_none(value: Any) -> Any:
    parsed = parse_json_string(value)
    if isinstance(parsed, str):
        return None
    return parsed


def require_non_null(record_id: Any, field_name: str, value: Any) -> Any:
    if value is None:
        raise ValueError(f"Record {record_id} is missing required field: {field_name}")
    return value


def extract_payload(raw_record: dict[str, Any]) -> dict[str, Any]:
    # Prefer wrapped raw payloads from ingest pipelines, but allow direct event objects too.
    wrapped_payload = raw_record.get("raw_message")
    if wrapped_payload is None:
        wrapped_payload = raw_record.get("content")

    if wrapped_payload is None:
        payload = raw_record
    else:
        payload = parse_json_string(wrapped_payload)

    if not isinstance(payload, dict):
        raise ValueError(f"Record {raw_record.get('id')} has invalid payload JSON")
    return payload


def build_parsed_event(raw_record: dict[str, Any], source: str) -> dict[str, Any]:
    record_id = raw_record.get("id")
    payload = extract_payload(raw_record)
    source_received_at = parse_iso_timestamp(
        raw_record.get("received_at", raw_record.get("recieved_at"))
    )

    session_id = require_non_null(record_id, "sessionID", payload.get("sessionID"))
    student_id = require_non_null(record_id, "studentID", payload.get("studentID"))
    event_ts = require_non_null(
        record_id, "timestamp", parse_iso_timestamp(payload.get("timestamp"))
    )
    event_type = require_non_null(record_id, "eventType", payload.get("eventType"))

    return {
        "session_id": session_id,
        "student_id": student_id,
        "class_code": payload.get("classCode"),
        "event_ts": event_ts,
        "event_type": event_type,
        "program_type": payload.get("programType"),
        "playground": payload.get("playground"),
        "project_json": parse_json_string_or_none(payload.get("project")),
        "block_event_data_json": parse_json_string_or_none(payload.get("blockEventData")),
        "playground_data_json": parse_json_string_or_none(payload.get("playgroundData")),
        "has_orphans": payload.get("hasOrphans"),
        "switch_block_count": payload.get("switchBlockCount"),
        "error_message": payload.get("errorMessage"),
        "source_log_id": record_id if isinstance(record_id, int) else None,
        "source_received_at": source_received_at,
        "source_queue": raw_record.get("queue_name") or raw_record.get("queue"),
        "source": source,
        "created_at": datetime.now(UTC).isoformat(),
    }


def parse_records(records: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    parsed_rows: list[dict[str, Any]] = []
    skipped_reasons: dict[str, int] = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"Record {index} from {source} is not an object")
        try:
            parsed_rows.append(build_parsed_event(record, source))
        except ValueError as error:
            reason = str(error)
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

    global _last_skip_summary
    _last_skip_summary = skipped_reasons
    if skipped_reasons:
        skipped_count = sum(skipped_reasons.values())
        print(
            f"Skipped {skipped_count} malformed records from {source}.",
            file=sys.stderr,
        )
        for reason, count in sorted(
            skipped_reasons.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            print(f"- {count}x {reason}", file=sys.stderr)
    return parsed_rows


def get_last_skip_summary() -> dict[str, int]:
    return dict(_last_skip_summary)


def parse_ndjson_text(text: str, source: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        normalized = line.strip()
        if not normalized:
            continue
        try:
            row = json.loads(normalized)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid NDJSON at line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"NDJSON line {line_number} is not an object")
        records.append(row)
    return parse_records(records, source)


def parse_text_blob(text: str, source: str) -> list[dict[str, Any]]:
    normalized = text.lstrip()
    if not normalized:
        return []
    if normalized.startswith("["):
        records = json.loads(normalized)
        if not isinstance(records, list):
            raise ValueError(f"Expected JSON array in {source}")
        return parse_records(records, source)
    return parse_ndjson_text(text, source)


def parse_file(input_path: Path) -> list[dict[str, Any]]:
    source = input_path.name
    suffix = input_path.suffix.lower()
    text = input_path.read_text(encoding="utf-8")

    if suffix in {".ndjson", ".jsonl"}:
        return parse_ndjson_text(text, source)

    records = json.loads(text)
    if not isinstance(records, list):
        raise ValueError(f"Expected JSON array in {input_path}")
    return parse_records(records, source)


def insert_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    sql = """
    INSERT INTO event_logs.parsed_events (
        session_id,
        student_id,
        class_code,
        event_ts,
        event_type,
        program_type,
        playground,
        project_json,
        block_event_data_json,
        playground_data_json,
        has_orphans,
        switch_block_count,
        error_message,
        source_log_id,
        source_received_at,
        source_queue,
        source
    )
    VALUES (
        %(session_id)s,
        %(student_id)s,
        %(class_code)s,
        %(event_ts)s,
        %(event_type)s,
        %(program_type)s,
        %(playground)s,
        %(project_json)s,
        %(block_event_data_json)s,
        %(playground_data_json)s,
        %(has_orphans)s,
        %(switch_block_count)s,
        %(error_message)s,
        %(source_log_id)s,
        %(source_received_at)s,
        %(source_queue)s,
        %(source)s
    )
    ON CONFLICT (source_log_id) DO NOTHING
    """

    payloads = [
        {
            "session_id": row["session_id"],
            "student_id": row["student_id"],
            "class_code": row["class_code"],
            "event_ts": row["event_ts"],
            "event_type": row["event_type"],
            "program_type": row["program_type"],
            "playground": row["playground"],
            "project_json": Json(row["project_json"]) if row["project_json"] is not None else None,
            "block_event_data_json": Json(row["block_event_data_json"])
            if row["block_event_data_json"] is not None
            else None,
            "playground_data_json": Json(row["playground_data_json"])
            if row["playground_data_json"] is not None
            else None,
            "has_orphans": row["has_orphans"],
            "switch_block_count": row["switch_block_count"],
            "error_message": row["error_message"],
            "source_log_id": row["source_log_id"],
            "source_received_at": row["source_received_at"],
            "source_queue": row["source_queue"],
            "source": row["source"],
        }
        for row in rows
    ]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, payloads)
    return len(payloads)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse raw event logs into parsed_events records.")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to JSON file containing raw log records",
    )
    parser.add_argument(
        "--insert",
        action="store_true",
        help="Insert parsed rows into event_logs.parsed_events using DATABASE_URL",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    parsed_rows = parse_file(input_path)
    if args.insert:
        inserted = insert_rows(parsed_rows)
        print(f"Inserted {inserted} rows into event_logs.parsed_events.")
        return

    print(json.dumps(parsed_rows[:3], indent=2))
    print(f"Parsed {len(parsed_rows)} records from {input_path}.")


if __name__ == "__main__":
    main()
