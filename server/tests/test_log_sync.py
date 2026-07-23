"""Covers the incremental-sync cursor logic (the lm-dashboard dateFrom port): the
fetch sends dateFrom, sync state round-trips the timestamp cursor, and the timestamp
parser tolerates prod's misspelling. Pure -- request_json is monkeypatched, no network."""
from src import fetch_invite_hub_logs as fh


def test_incremental_fetch_passes_datefrom(monkeypatch):
    seen = {}

    def fake_request_json(url, token=None):
        seen["url"] = url
        return {"results": []}  # empty -> loop returns immediately

    monkeypatch.setattr(fh, "request_json", fake_request_json)
    fh.fetch_vex_logs_incremental(
        "http://h", "t", "", page_size=500, last_source_log_id=10,
        date_from="2026-07-21T00:00:00+00:00",
    )
    assert "dateFrom=" in seen["url"]


def test_incremental_fetch_omits_datefrom_when_none(monkeypatch):
    seen = {}
    monkeypatch.setattr(fh, "request_json",
                        lambda url, token=None: seen.update(url=url) or {"results": []})
    fh.fetch_vex_logs_incremental("http://h", "t", "", page_size=500, last_source_log_id=None)
    assert "dateFrom=" not in seen["url"]


def test_sync_state_roundtrips_event_time(tmp_path):
    p = tmp_path / "state.json"
    fh.write_sync_state(p, 42, "2026-07-21T18:00:00+00:00")
    state = fh.read_sync_state(p)
    assert state["last_source_log_id"] == 42
    assert state["last_event_time"] == "2026-07-21T18:00:00+00:00"


def test_parse_event_time_tolerates_misspelling_and_z():
    assert fh.parse_event_time({"recieved_at": "2026-07-21T18:00:00Z"}).tzinfo is not None
    assert fh.parse_event_time({"received_at": "2026-07-21T18:00:00+00:00"}) is not None
    assert fh.parse_event_time({}) is None
    assert fh.parse_event_time({"recieved_at": "not-a-date"}) is None
