from datetime import date, datetime, timedelta, timezone

import pytest

from signals.core.feed import Week
from signals.core.runner import run_week
from signals.core.source import RawRecord
from signals.db.store import Store
from signals.settings import RegionConfig
from signals.verticals.care.collect import ASC_DIRECTORATE, CareScope
from signals.verticals.care.feeds import CareVertical, rating_change
from tests.conftest import load_fixture

T0 = datetime(2026, 9, 21, 9, tzinfo=timezone.utc)  # the Monday after the week
WEEK = Week(date(2026, 9, 20))  # Mon 14 to Sun 20 Sep 2026
REGIONS = {"london": RegionConfig(cqc_region="London"), "east-london": RegionConfig(postcode_areas=["E", "IG", "RM"])}


def location(location_id, *, region="London", postcode="E1 6AN", provider="P-LTD", registered="2020-01-01",
             status="Registered", rating=None, rating_date=None, historic=(), last_inspection=None, **extra):
    payload = {
        "locationId": location_id, "providerId": provider, "name": f"Home {location_id}",
        "registrationStatus": status, "registrationDate": registered, "inspectionDirectorate": ASC_DIRECTORATE,
        "region": region, "localAuthority": "Tower Hamlets" if region == "London" else "Elsewhere",
        "postalCode": postcode, "postalAddressLine1": "1 Example Road", "postalAddressTownCity": "London",
        "gacServiceTypes": [{"name": "Homecare agencies"}], "careHome": "N",
        "historicRatings": [{"reportDate": d, "overall": {"rating": r}} for r, d in historic],
        **extra,
    }
    if rating:
        payload["currentRatings"] = {"overall": {"rating": rating, "reportDate": rating_date}}
    if last_inspection:
        payload["lastInspection"] = {"date": last_inspection}
    return payload


PROVIDERS = {
    "P-LTD": {"providerId": "P-LTD", "name": "Example Care Group Limited", "ownershipType": "Organisation",
              "companiesHouseNumber": "1234567", "postalCode": "E1 6AN", "region": "London",
              "localAuthority": "Tower Hamlets", "mainPhoneNumber": "02070000000"},
    "P-SOLE": {"providerId": "P-SOLE", "name": "Example Homecare Services", "ownershipType": "Individual",
               "postalCode": "IG1 1AA", "region": "London", "localAuthority": "Redbridge"},
}

LOCATIONS = [
    location("L-NEW", registered="2026-09-15", provider="P-SOLE", postcode="IG1 1AA"),  # never inspected, new
    location("L-OLD-NEVER", registered="2026-05-01"),  # never inspected, not new
    location("L-RI", rating="Requires Improvement", rating_date="2026-09-16", historic=[("Good", "2023-05-02")]),
    location("L-INAD-OLD", rating="Inadequate", rating_date="2025-01-01"),
    location("L-GOOD", rating="Good", rating_date="2026-09-16"),
    location("L-DEREG", registered="2026-09-15", status="Deregistered"),
    location("L-NORTH", region="North West", postcode="FY4 2RF", registered="2026-09-15"),
    location("L-INSPECTED", registered="2026-06-01", last_inspection="2026-09-10"),  # report not out yet
    location("L-PMS", registered="2026-09-15", inspectionDirectorate="Primary medical services"),
]


def companies():
    items = load_fixture("synthetic/ch_advanced_search.json")["items"]
    extra = [
        {"company_number": "01234567", "company_name": "EXAMPLE CARE GROUP LTD", "company_type": "ltd",
         "date_of_creation": "2026-09-15", "sic_codes": ["87300"],
         "registered_office_address": {"postal_code": "E1 6AN"}},
        {"company_number": "16000099", "company_name": "OLD CARE LTD", "company_type": "ltd",
         "date_of_creation": "2026-06-01", "sic_codes": ["87300"], "registered_office_address": {"postal_code": "E1 6AN"}},
    ]
    return items + extra


def save(store, source, entity_type, entity_id, payload, at=T0):
    store.save_record(RawRecord(source, entity_type, entity_id, at, payload))


@pytest.fixture
def store():
    with Store.open(":memory:") as s:
        for loc in LOCATIONS:
            save(s, "cqc", "location", loc["locationId"], loc)
        for pid, prov in PROVIDERS.items():
            save(s, "cqc", "provider", pid, prov)
        for company in companies():
            save(s, "companies_house", "company", company["company_number"], company)
        yield s


def run(store, week=WEEK, regions=REGIONS):
    return run_week(CareVertical(store, CareScope(regions)), store, week, now=T0)


def by_key(result):
    return {lead.entity_key: lead for lead in result.leads}


def test_never_inspected_reports_new_registrations_only(store):
    result = run(store)["never_inspected"]
    assert set(by_key(result)) == {"cqc:location:L-NEW"}
    # The full current list (for never_inspected_all.csv) includes older ones and out-of-region ones.
    assert result.qualifying == 3  # L-NEW, L-OLD-NEVER, L-NORTH
    lead = by_key(result)["cqc:location:L-NEW"]
    assert lead.regions == ("london", "east-london")
    assert lead.trigger_key == "registered:2026-09-15"
    assert lead.data["provider_name"] == "Example Homecare Services"
    assert lead.data["legal_form"] == "sole trader"
    assert lead.data["suggested_channel"] == "post only"  # sole trader, no phone number


def test_poor_ratings(store):
    result = run(store)["poor_ratings"]
    assert set(by_key(result)) == {"cqc:location:L-RI"}
    assert result.qualifying == 2
    lead = by_key(result)["cqc:location:L-RI"]
    assert lead.trigger_key == "Requires improvement:2026-09-16"
    assert lead.data["rating"] == "Requires improvement"
    assert lead.data["previous_rating"] == "Good"
    assert lead.data["rating_change"] == "downgrade"
    assert lead.data["provider_company_number"] == "01234567"
    assert lead.data["legal_form"] == "limited company"
    assert lead.data["suggested_channel"] == "email OK"


def test_assessment_framework_rating_and_previous(store):
    raw = load_fixture("synthetic/cqc_location_assessment_only.json")
    save(store, "cqc", "location", raw["locationId"], raw)
    lead = by_key(run(store)["poor_ratings"])[f"cqc:location:{raw['locationId']}"]
    assert lead.data["rating"] == "Inadequate"
    assert lead.data["rating_framework"] == "assessment"
    assert lead.event_date == date(2026, 9, 17)
    assert (lead.data["previous_rating"], lead.data["previous_rating_date"]) == ("Good", "2022-02-10")


def test_previous_rating_from_snapshots_and_undated_rating(store):
    save(store, "cqc", "location", "L-SNAP", location("L-SNAP", rating="Good", rating_date="2024-01-01"), T0 - timedelta(days=30))
    undated = location("L-SNAP", rating="Inadequate")
    save(store, "cqc", "location", "L-SNAP", undated, datetime(2026, 9, 18, tzinfo=timezone.utc))
    lead = by_key(run(store)["poor_ratings"])["cqc:location:L-SNAP"]
    assert lead.trigger_key == "Inadequate:undated"
    assert lead.event_date == date(2026, 9, 18)  # first seen in our snapshots
    assert (lead.data["previous_rating"], lead.data["rating_change"]) == ("Good", "downgrade")


def test_new_companies_linking_and_regions(store):
    result = run(store)["new_companies"]
    leads = by_key(result)
    # Not reported: the Manchester LLP (no customer region), EC1A 1BB (no CQC data in that district or area
    # to infer a region from), and OLD CARE LTD (incorporated before the week and grace period).
    assert set(leads) == {"companies_house:company:16000001", "companies_house:company:01234567"}
    assert result.qualifying == 5
    exact = leads["companies_house:company:01234567"].data
    assert (exact["cqc_registered"], exact["cqc_provider_id"], exact["cqc_match"]) == ("yes", "P-LTD", "companies house number")
    assert exact["inferred_cqc_region"] == "London"
    fuzzy = leads["companies_house:company:16000001"].data  # EXAMPLE HOMECARE SERVICES LTD, IG1 1AA
    assert (fuzzy["cqc_registered"], fuzzy["cqc_provider_id"], fuzzy["cqc_match"]) == ("possible", "P-SOLE", "name+postcode")
    assert leads["companies_house:company:16000001"].regions == ("london", "east-london")
    assert exact["legal_form"] == "limited company" and exact["suggested_channel"] == "email OK"


def test_shared_registered_office_gets_no_region(store):
    for n in range(5):
        save(store, "companies_house", "company", f"1700000{n}", {
            "company_number": f"1700000{n}", "company_name": f"AGENT CLIENT {n} CARE LTD", "company_type": "ltd",
            "date_of_creation": "2026-09-16", "sic_codes": ["88100"],
            "registered_office_address": {"address_line_1": "20 Wenlock Road", "postal_code": "E1 6AN"}})
    result = run(store)["new_companies"]
    assert not any(key.startswith("companies_house:company:1700000") for key in by_key(result))
    # E1 6AN is now shared by 7 companies (5 agent clients, EXAMPLE CARE GROUP LTD, OLD CARE LTD), so all drop.
    assert "companies_house:company:01234567" not in by_key(result)
    # They are listed nationally instead, once each, as "location unknown".
    unknown = run(store)["location_unknown"]
    assert {key for key in by_key(unknown)} >= {f"companies_house:company:1700000{n}" for n in range(5)}
    lead = by_key(unknown)["companies_house:company:17000000"]
    assert lead.regions == ("national",)
    assert lead.data["shared_registered_office"] is True and lead.data["companies_at_postcode"] == 7
    assert lead.data["inferred_cqc_region"] is None
    assert lead.data["sic_description"] == "domiciliary / social work without accommodation"


def test_runs_are_idempotent_and_leads_are_reported_once(store):
    first = run(store)
    assert first["poor_ratings"].recorded == 1
    again = run(store)
    assert again["poor_ratings"].recorded == 0
    assert [lead.entity_key for lead in again["poor_ratings"].leads] == [lead.entity_key for lead in first["poor_ratings"].leads]

    # Next week: L-RI (16 Sep) is still inside the grace window but was already reported.
    later = run(store, WEEK.previous().previous().previous().previous())  # an older week: nothing recorded
    assert all(r.leads == [] for r in later.values())
    next_week = run(store, Week(date(2026, 9, 27)))
    assert next_week["poor_ratings"].leads == []

    # A re-rating is a new trigger, so it is reported again.
    save(store, "cqc", "location", "L-RI", location("L-RI", rating="Inadequate", rating_date="2026-09-24",
                                                     historic=[("Requires improvement", "2026-09-16"), ("Good", "2023-05-02")]))
    lead = by_key(run(store, Week(date(2026, 9, 27)))["poor_ratings"])["cqc:location:L-RI"]
    assert lead.data["previous_rating"] == "Requires improvement"
    assert lead.data["rating_change"] == "downgrade"


def test_late_published_event_is_caught_within_grace(store):
    run(store)
    # Registered on the 12th (before the week) but only appears in our data after the week was run.
    save(store, "cqc", "location", "L-LATE", location("L-LATE", registered="2026-09-12"))
    result = run(store, Week(date(2026, 9, 27)))["never_inspected"]
    assert set(by_key(result)) == {"cqc:location:L-LATE"}


def test_all_england_scope_tags_everything(store):
    result = run(store, regions={})["never_inspected"]
    assert set(by_key(result)) == {"cqc:location:L-NEW", "cqc:location:L-NORTH"}
    assert all(lead.regions == ("england",) for lead in result.leads)


def test_week_helpers():
    assert Week.last_completed(date(2026, 9, 21)) == Week(date(2026, 9, 20))  # Monday
    assert Week.last_completed(date(2026, 9, 20)) == Week(date(2026, 9, 13))  # Sunday: week not over
    assert Week.last_completed(date(2026, 9, 23)) == Week(date(2026, 9, 20))
    assert WEEK.start == date(2026, 9, 14)
    assert WEEK.end_datetime == datetime(2026, 9, 21, tzinfo=timezone.utc)


def test_rating_change():
    assert rating_change(None, "Inadequate") == "first rating"
    assert rating_change("Good", "Inadequate") == "downgrade"
    assert rating_change("Inadequate", "Requires improvement") == "improved but still poor"
    assert rating_change("Requires improvement", "Requires improvement") == "no change"
    assert rating_change("Insufficient evidence to rate", "Inadequate") == "unknown"


@pytest.mark.parametrize(
    ("name", "flag"),
    [
        ("DIAMOND CUT CHILDRENS CARE HOME LTD", "children's services (Ofsted, not CQC)"),
        ("OPEN ARMS CHILDREN'S SERVICES LTD", "children's services (Ofsted, not CQC)"),
        ("KEMY SOLUTIONS RECRUITMENT LTD", "recruitment / staffing"),
        ("BRIGHT CARE TRAINING ACADEMY LTD", "training / consultancy"),
        ("SAFEPLACE CARE LTD", None),
        ("CHILDSWORTH HOMECARE LTD", None),  # whole words only
        (None, None),
    ],
)
def test_name_flags(name, flag):
    from signals.verticals.care.flags import name_flag

    assert name_flag(name) == flag
