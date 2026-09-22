from datetime import datetime, timedelta, timezone

import pytest

from signals.core.source import RawRecord
from signals.db.schema import SCHEMA_VERSION
from signals.db.store import SaveResult, SchemaVersionError, Store

T0 = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def rec(entity_id="1-1", payload=None, at=T0, entity_type="location"):
    return RawRecord("cqc", entity_type, entity_id, at, payload if payload is not None else {"name": "A"})


@pytest.fixture
def store():
    with Store.open(":memory:") as s:
        yield s


def test_open_creates_schema_and_is_idempotent(tmp_path):
    path = tmp_path / "sub" / "signals.db"
    with Store.open(path) as s:
        s.save_record(rec())
    with Store.open(path) as s:
        assert s.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert s.get("cqc", "location", "1-1").payload == {"name": "A"}


def test_refuses_newer_schema(tmp_path):
    path = tmp_path / "signals.db"
    Store.open(path).close()
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    conn.close()
    with pytest.raises(SchemaVersionError):
        Store.open(path)


def test_snapshots_only_written_when_payload_changes(store):
    assert store.save_record(rec(at=T0)) is SaveResult.NEW
    assert store.save_record(rec(at=T0 + timedelta(days=7))) is SaveResult.UNCHANGED
    assert store.save_record(rec(payload={"name": "B"}, at=T0 + timedelta(days=14))) is SaveResult.CHANGED

    entity = store.get("cqc", "location", "1-1")
    assert entity.payload == {"name": "B"}
    assert entity.first_seen_at == T0
    assert entity.last_fetched_at == entity.last_changed_at == T0 + timedelta(days=14)
    assert [s.payload["name"] for s in store.history("cqc", "location", "1-1")] == ["A", "B"]


def test_key_order_does_not_count_as_a_change(store):
    store.save_record(rec(payload={"a": 1, "b": 2}))
    assert store.save_record(rec(payload={"b": 2, "a": 1}, at=T0 + timedelta(days=1))) is SaveResult.UNCHANGED


def test_snapshot_as_of_gives_week_on_week_view(store):
    store.save_record(rec(payload={"rating": "Good"}, at=T0))
    store.save_record(rec(payload={"rating": "Inadequate"}, at=T0 + timedelta(days=7)))
    assert store.snapshot_as_of("cqc", "location", "1-1", T0 - timedelta(seconds=1)) is None
    assert store.snapshot_as_of("cqc", "location", "1-1", T0 + timedelta(days=6)).payload == {"rating": "Good"}
    assert store.snapshot_as_of("cqc", "location", "1-1", T0 + timedelta(days=7)).payload == {"rating": "Inadequate"}


def test_mark_gone_and_reappear(store):
    assert not store.mark_gone("cqc", "location", "nope", T0)
    store.save_record(rec())
    assert store.mark_gone("cqc", "location", "1-1", T0 + timedelta(days=1))
    assert store.get("cqc", "location", "1-1").gone_at == T0 + timedelta(days=1)
    assert [e.entity_id for e in store.iter_entities("cqc", "location")] == []
    assert [e.entity_id for e in store.iter_entities("cqc", "location", include_gone=True)] == ["1-1"]
    store.save_record(rec(at=T0 + timedelta(days=2)))
    assert store.get("cqc", "location", "1-1").gone_at is None


def test_fetched_since(store):
    store.save_record(rec("old", at=T0))
    store.save_record(rec("new", at=T0 + timedelta(days=2)))
    assert store.fetched_since("cqc", "location", T0 + timedelta(days=1)) == {"new"}


def test_cursors_and_runs(store):
    assert store.get_cursor("cqc", "changes") is None
    store.set_cursor("cqc", "changes", "2026-09-01T00:00:00Z")
    store.set_cursor("cqc", "changes", "2026-09-08T00:00:00Z")
    assert store.get_cursor("cqc", "changes") == "2026-09-08T00:00:00Z"

    run_id = store.start_run("backfill", {"days": 90}, T0)
    store.finish_run(run_id, "ok", {"location_new": 3}, T0 + timedelta(minutes=5))
    row = store.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    assert row["status"] == "ok" and row["finished_at"] == "2026-09-01T12:05:00Z"


def test_counts(store):
    store.save_record(rec("a"))
    store.save_record(rec("b"))
    store.save_record(RawRecord("companies_house", "company", "123", T0, {"company_name": "X"}))
    counts = store.counts()
    assert counts["cqc/location"] == 2 and counts["companies_house/company"] == 1 and counts["snapshots"] == 3


def test_lead_events_are_unique_per_trigger(store):
    sql = (
        "INSERT OR IGNORE INTO lead_events (vertical, feed, entity_key, trigger_key, week_ending, created_at, data)"
        " VALUES ('care', 'poor_ratings', 'cqc:location:1-1', 'Inadequate@2026-09-01', '2026-09-06', 'x', '{}')"
    )
    store.conn.execute(sql)
    store.conn.execute(sql)
    assert store.counts()["lead_events"] == 1


def test_purge_keeps_current_versions(store):
    old, new, cutoff = T0, T0 + timedelta(days=400), T0 + timedelta(days=365)
    store.save_record(rec("kept", {"v": 1}, at=old))
    store.save_record(rec("kept", {"v": 2}, at=new))
    store.save_record(rec("stale-but-current", {"v": 1}, at=old))
    store.save_record(rec("gone", {"v": 1}, at=old))
    store.mark_gone("cqc", "location", "gone", old + timedelta(days=1))
    store.start_run("backfill", {}, old)  # still running: kept
    finished = store.start_run("backfill", {}, old)
    store.finish_run(finished, "ok", {}, old)

    removed = store.purge(cutoff)

    assert removed == {"entities": 1, "snapshots": 1, "lead_events": 0, "runs": 1}
    assert [s.payload for s in store.history("cqc", "location", "kept")] == [{"v": 2}]
    assert len(store.history("cqc", "location", "stale-but-current")) == 1
    assert store.get("cqc", "location", "gone") is None and store.history("cqc", "location", "gone") == []
