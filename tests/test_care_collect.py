from datetime import date, timedelta

import pytest

from signals.settings import RegionConfig
from signals.verticals.care.collect import (
    ASC_DIRECTORATE,
    CareScope,
    NotBackfilledError,
    plan_backfill,
    run_backfill,
    run_sync,
)
from tests.fakes import NOW, REGIONS, loc


def test_scope_queries():
    assert CareScope(REGIONS).list_queries() == [
        ({"inspectionDirectorate": ASC_DIRECTORATE, "region": "London"}, False),
        ({"inspectionDirectorate": ASC_DIRECTORATE}, True),
    ]
    assert CareScope({"l": RegionConfig(cqc_region="London"), "l2": RegionConfig(cqc_region="London")}).list_queries() == [
        ({"inspectionDirectorate": ASC_DIRECTORATE, "region": "London"}, False),
    ]
    assert CareScope({}).list_queries() == [({"inspectionDirectorate": ASC_DIRECTORATE}, False)]
    la = CareScope({"kent": RegionConfig(local_authorities=["Medway", "Kent"])}).list_queries()
    assert la == [({"inspectionDirectorate": ASC_DIRECTORATE, "localAuthority": ["Kent", "Medway"]}, False)]


def test_location_in_scope():
    scope = CareScope(REGIONS)
    assert scope.location_in_scope(loc("x", "London", "SW1A 1AA"))
    assert scope.location_in_scope(loc("x", "East", "RM16 1AA"))
    assert not scope.location_in_scope(loc("x", "North West", "FY4 2RF"))
    assert not scope.location_in_scope(loc("x", "London", "SE1 7PB", directorate="Primary medical services"))


def test_plan_lists_scope_and_estimates(fake, cqc, store):
    plan = plan_backfill(cqc, store, CareScope(REGIONS), days=90, now=NOW)
    # London list: L1, L2, L5. Full list filtered by postcode: L3 (IG) and L5 (E1); not L4 (FY).
    assert plan.location_ids == ["L1", "L2", "L5", "L3"]
    assert plan.list_calls == 2
    assert plan.estimated_ch_calls == 13
    assert plan.estimated_cqc_calls == 4 + 2
    assert fake.detail_calls("locations") == []
    assert any("Estimated duration" in line for line in plan.describe())


def test_backfill_stores_sanitised_baseline_and_sets_cursors(fake, cqc, ch, ch_calls, store):
    plan = plan_backfill(cqc, store, CareScope(REGIONS), days=14, now=NOW)
    stats = run_backfill(plan, cqc, ch, store)

    assert stats.failures == []
    assert stats.counts["location_new"] == 3
    assert stats.counts["location_not_found"] == 1  # L5 is listed but 404s, and was never stored
    assert "location_gone" not in stats.counts
    # Providers only for registered locations: P1 (L1, L3), not P2 (L2 is deregistered).
    assert fake.detail_calls("providers") == ["P1"]
    assert stats.counts["company_new"] == 3
    assert len(ch_calls) == 3  # 14 days + today in weekly slices
    assert ch_calls[0]["incorporated_from"] == "2026-09-08"

    stored = store.get("cqc", "location", "L1").payload
    assert "contacts" not in stored["regulatedActivities"][0]  # personal names stripped
    assert store.get_cursor("cqc", "changes") == "2026-09-22T12:00:00Z"
    assert store.get_cursor("companies_house", "incorporations") == "2026-09-22"
    run = store.conn.execute("SELECT status, stats FROM runs").fetchone()
    assert run["status"] == "ok" and '"location_new":3' in run["stats"]


def test_backfill_resumes_and_skips_fresh_records(fake, cqc, ch, store, clock):
    run_backfill(plan_backfill(cqc, store, CareScope(REGIONS), days=7, now=NOW), cqc, ch, store)
    fake.requests.clear()

    clock["now"] = NOW + timedelta(hours=2)
    plan = plan_backfill(cqc, store, CareScope(REGIONS), days=7, now=clock["now"])
    assert plan.fresh_location_ids == {"L1", "L2", "L3"}
    assert plan.locations_to_fetch == ["L5"]
    run_backfill(plan, cqc, ch, store)
    assert fake.detail_calls("locations") == ["L5"]
    assert fake.detail_calls("providers") == []


def test_backfill_records_failures_and_carries_on(fake, cqc, ch, store):
    fake.fail = {"L1"}
    stats = run_backfill(plan_backfill(cqc, store, CareScope(REGIONS), days=7, now=NOW), cqc, ch, store)
    assert len(stats.failures) == 1 and "L1" in stats.failures[0]
    assert store.has("cqc", "location", "L3")
    assert store.conn.execute("SELECT status FROM runs").fetchone()[0] == "partial"


def test_sync_requires_backfill(cqc, ch, store):
    with pytest.raises(NotBackfilledError):
        run_sync(cqc, ch, store, CareScope(REGIONS), now=NOW)


def test_sync_keeps_in_scope_and_tracked_changes(fake, cqc, ch, ch_calls, store, clock):
    run_backfill(plan_backfill(cqc, store, CareScope(REGIONS), days=7, now=NOW), cqc, ch, store)
    fake.requests.clear()
    ch_calls.clear()

    later = NOW + timedelta(days=7)
    clock["now"] = later
    fake.locations["L1"] = loc("L1", "London", "SE1 7PB", currentRatings={"overall": {"rating": "Inadequate"}})
    fake.locations["L6"] = loc("L6", "London", "W1D 3QU", provider="P3")  # new, in scope, new provider
    fake.locations["L7"] = loc("L7", "London", "SE1 1AA", directorate="Primary medical services")
    fake.locations["L3"] = loc("L3", "East", "IG10 1AA")  # unchanged payload
    del fake.locations["L2"]  # tracked, now gone
    fake.changes = {"location": ["L1", "L2", "L3", "L4", "L6", "L7"], "provider": ["P1", "P9"]}

    stats = run_sync(cqc, ch, store, CareScope(REGIONS), now=later)

    assert stats.counts["location_changed"] == 1  # L1
    assert stats.counts["location_unchanged"] == 1  # L3
    assert stats.counts["location_new"] == 1  # L6
    assert stats.counts["location_gone"] == 1  # L2
    assert stats.counts["location_out_of_scope"] == 2  # L4 (North West), L7 (not adult social care)
    assert not store.has("cqc", "location", "L4")
    # P1 is tracked and changed; P3 is new via L6; P9 changed but isn't tracked.
    assert fake.detail_calls("providers") == ["P1", "P3"]
    assert len(store.history("cqc", "location", "L1")) == 2
    assert store.get("cqc", "location", "L2").gone_at == later

    changes_req = next(r for r in fake.requests if "/changes/location" in r.url.path)
    assert changes_req.url.params["startTimestamp"] == "2026-09-22T12:00:00Z"
    assert changes_req.url.params["endTimestamp"] == "2026-09-29T12:00:00Z"
    assert ch_calls[0]["incorporated_from"] == str(date(2026, 9, 15))  # 7-day overlap
    assert store.get_cursor("cqc", "changes") == "2026-09-29T12:00:00Z"


def test_sync_holds_cursor_back_on_failure(fake, cqc, ch, store, clock):
    run_backfill(plan_backfill(cqc, store, CareScope(REGIONS), days=7, now=NOW), cqc, ch, store)
    fake.changes = {"location": ["L1"], "provider": []}
    fake.fail = {"L1"}
    stats = run_sync(cqc, ch, store, CareScope(REGIONS), now=NOW + timedelta(days=7))
    assert stats.failures
    assert store.get_cursor("cqc", "changes") == "2026-09-22T12:00:00Z"
