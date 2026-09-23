from datetime import date, datetime, timedelta, timezone

from signals.core.feed import Week
from signals.core.runner import run_week
from signals.core.source import RawRecord
from signals.verticals.care.collect import CareScope, plan_backfill, run_backfill, run_sync
from signals.verticals.care.feeds import CareVertical
from signals.verticals.care.watch import merge_profile, watch_candidates
from tests.fakes import REGIONS as COLLECT_REGIONS
from tests.test_care_feeds import REGIONS, location

AGENT = "WC2H 9JQ"
T0 = datetime(2026, 7, 1, 9, tzinfo=timezone.utc)


def company(number, postcode=AGENT, created="2026-06-20", status="active", name=None):
    return {
        "company_number": number, "company_name": name or f"CLIENT {number} CARE LTD", "company_type": "ltd",
        "company_status": status, "date_of_creation": created, "sic_codes": ["88100"],
        "registered_office_address": {"address_line_1": "71-75 Shelton Street", "locality": "London",
                                      "postal_code": postcode},
    }


def put(store, payload, at=T0, source="companies_house", entity_type="company", entity_id=None):
    store.save_record(RawRecord(source, entity_type, entity_id or payload["company_number"], at, payload))


def agent_clients(store, n=5, at=T0):
    for i in range(n):
        put(store, company(f"1900000{i}"), at)


def test_merge_profile_only_records_real_changes():
    stored = company("1")
    same_place = {"registered_office_address": {"premises": "71-75", "address_line_1": "Shelton Street",
                                                "postal_code": "wc2h 9jq"}, "company_status": "active"}
    assert merge_profile(stored, same_place) == stored
    moved = {"registered_office_address": {"premises": "Unit 2", "address_line_1": "Example Road",
                                           "locality": "Ilford", "postal_code": "IG1 1AA"},
             "company_status": "active"}
    merged = merge_profile(stored, moved)
    assert merged["registered_office_address"] == {"address_line_1": "Unit 2 Example Road", "locality": "Ilford",
                                                   "postal_code": "IG1 1AA"}
    assert merge_profile(stored, {"company_status": "dissolved"})["company_status"] == "dissolved"


def test_watch_candidates(store):
    agent_clients(store)
    put(store, company("OLD", created="2025-01-01"))  # incorporated too long ago
    put(store, company("GONE", status="dissolved"))
    put(store, company("LOCAL", postcode="IG1 1AA"))  # not at a shared address
    put(store, company("FRESH"), at=T0 + timedelta(days=20))  # checked recently
    now = T0 + timedelta(days=30)
    due = [e.entity_id for e in watch_candidates(store, now)]
    assert due == [f"1900000{i}" for i in range(5)]
    assert len(watch_candidates(store, now, limit=2)) == 2


def test_sync_rechecks_watched_companies(fake, cqc, ch, ch_calls, ch_profiles, store, clock):
    clock["now"] = T0
    run_backfill(plan_backfill(cqc, store, CareScope(COLLECT_REGIONS), days=7, now=T0), cqc, ch, store)
    agent_clients(store, 6)
    ch_profiles["19000000"] = {"registered_office_address": {"address_line_1": "1 Real Road", "postal_code": "E1 6AN"},
                               "company_status": "active"}
    ch_profiles["19000001"] = {"registered_office_address": {"premises": "71-75", "address_line_1": "Shelton Street",
                                                             "postal_code": AGENT}, "company_status": "active"}
    ch_calls.clear()

    later = T0 + timedelta(days=30)
    clock["now"] = later
    stats = run_sync(cqc, ch, store, CareScope(COLLECT_REGIONS), now=later)

    assert sorted(c["path"] for c in ch_calls if c["path"].startswith("/company/")) == [
        f"/company/1900000{i}" for i in range(6)]
    assert stats.counts["company_rechecked"] == 6  # four are 404s: counted, nothing stored
    assert stats.counts["company_moved"] == 1
    assert stats.failures == []
    assert len(store.history("companies_house", "company", "19000001")) == 1  # same postcode, new format: no change
    assert store.get("companies_house", "company", "19000000").payload["registered_office_address"]["postal_code"] == "E1 6AN"
    # Checked companies aren't due again for 28 days.
    assert "19000001" not in {e.entity_id for e in watch_candidates(store, later + timedelta(days=1))}


def _located(store, week):
    return {lead.entity_key: lead for lead in run_week(CareVertical(store, CareScope(REGIONS)), store, week,
                                                      now=datetime(2026, 9, 21, tzinfo=timezone.utc))["company_located"].leads}


def test_moved_company_becomes_a_regional_lead(store):
    agent_clients(store, 6)
    put(store, location("L-E1", postcode="E1 7AA"), source="cqc", entity_type="location", entity_id="L-E1")
    moved = company("19000000", postcode="E1 6AN")
    moved["registered_office_address"]["address_line_1"] = "1 Real Road"
    put(store, moved, at=datetime(2026, 9, 16, 8, tzinfo=timezone.utc))

    leads = _located(store, Week(date(2026, 9, 20)))
    lead = leads["companies_house:company:19000000"]
    assert lead.trigger_key == "moved:E16AN"
    assert lead.event_date == date(2026, 9, 16)
    assert lead.regions == ("london", "east-london")
    assert lead.data["located_by"] == "moved registered office"
    assert lead.data["previous_postcode"] == AGENT
    assert len(leads) == 1  # companies still at the agent aren't located


def test_company_registering_with_cqc_becomes_a_regional_lead(store):
    agent_clients(store, 6)
    put(store, {"providerId": "P-NEW", "name": "Client 19000003 Care Ltd", "companiesHouseNumber": "19000003",
                "ownershipType": "Organisation", "registrationDate": "2026-09-15", "region": "London",
                "localAuthority": "Hackney", "postalCode": "E8 1AA", "postalAddressLine1": "2 Mare Street"},
        source="cqc", entity_type="provider", entity_id="P-NEW")
    lead = _located(store, Week(date(2026, 9, 20)))["companies_house:company:19000003"]
    assert lead.trigger_key == "cqc:P-NEW"
    assert lead.event_date == date(2026, 9, 15)
    assert lead.regions == ("london", "east-london")
    assert lead.data["located_by"] == "registered with CQC"
    assert lead.data["inferred_local_authority"] == "Hackney"
    assert lead.data["cqc_provider_postcode"] == "E8 1AA"
