import csv
from datetime import date

import pytest

from signals.core.runner import run_week
from signals.db.store import Store
from signals.settings import RegionConfig
from signals.verticals.care.collect import CareScope
from signals.verticals.care.digest import write_week
from signals.verticals.care.feeds import CareVertical, DueForInspectionFeed, add_years
from tests.test_care_feeds import T0, WEEK, location, save

REGIONS = {"london": RegionConfig(cqc_region="London")}
AS_OF = T0.date()  # Mon 21 Sep 2026

PROVIDERS = {
    "P-IND": {"providerId": "P-IND", "name": "Solo Care Ltd", "ownershipType": "Organisation",
              "companiesHouseNumber": "1111111", "locationIds": ["L-DUE-RATED"]},
    "P-MULTI": {"providerId": "P-MULTI", "name": "Three Homes Ltd", "ownershipType": "Organisation",
                "companiesHouseNumber": "2222222", "locationIds": ["L-DUE-OLD", "X-1", "X-2"]},
    "P-BRAND": {"providerId": "P-BRAND", "name": "Big Group CC12 Ltd", "ownershipType": "Organisation",
                "companiesHouseNumber": "3333333", "locationIds": ["L-BRAND"], "brandId": "BD1",
                "brandName": "BRAND Big Group"},
    "P-BIG": {"providerId": "P-BIG", "name": "Many Branches Ltd", "ownershipType": "Organisation",
              "companiesHouseNumber": "4444444"},
}

LOCATIONS = [
    # Rating turned 4 years old during the week (Mon 14 to Sun 20 Sep 2026): a weekly lead.
    location("L-DUE-RATED", provider="P-IND", rating="Good", rating_date="2022-09-15"),
    # Due long ago: only in the full list.
    location("L-DUE-OLD", provider="P-MULTI", rating="Requires improvement", rating_date="2019-03-01"),
    # A year since registering, never inspected: due on 2026-09-16.
    location("L-DUE-UNRATED", provider="P-OTHER", registered="2025-09-16"),
    location("L-RECENT", provider="P-OTHER", rating="Good", rating_date="2024-01-10"),  # not due
    location("L-REINSPECTED", provider="P-OTHER", rating="Good", rating_date="2019-01-01",
             last_inspection="2026-08-01"),  # inspected since: report on its way
    location("L-SOON", provider="P-OTHER", rating="Good", rating_date="2022-09-25"),  # due after the as-of date
    location("L-NEW", provider="P-OTHER", registered="2026-03-01"),  # unrated, but not a year yet
    location("L-BRAND", provider="P-BRAND", rating="Inadequate", rating_date="2022-09-16"),
    *[location(f"L-BIG-{n}", provider="P-BIG", rating="Good", rating_date="2018-01-01") for n in range(10)],
]


@pytest.fixture
def store():
    with Store.open(":memory:") as s:
        for loc in LOCATIONS:
            save(s, "cqc", "location", loc["locationId"], loc)
        for pid, prov in PROVIDERS.items():
            save(s, "cqc", "provider", pid, prov)
        yield s


def care(store, regions=REGIONS):
    return CareVertical(store, CareScope(regions), as_of=AS_OF)


def _csv(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_add_years_handles_leap_day():
    assert add_years(date(2024, 2, 29), 4) == date(2028, 2, 29)
    assert add_years(date(2020, 2, 29), 1) == date(2021, 2, 28)


def test_due_for_inspection_feed(store):
    leads = {lead.entity_key.split(":")[-1]: lead for lead in DueForInspectionFeed(care(store).data).leads()}
    assert set(leads) == {"L-DUE-RATED", "L-DUE-OLD", "L-DUE-UNRATED", "L-BRAND"} | {f"L-BIG-{n}" for n in range(10)}
    rated = leads["L-DUE-RATED"]
    assert rated.event_date == date(2026, 9, 15)
    assert rated.trigger_key == "due:rated:2022-09-15"
    assert rated.data["due_reason"] == "last rated Good on 2022-09-15"
    unrated = leads["L-DUE-UNRATED"]
    assert unrated.event_date == date(2026, 9, 16)
    assert unrated.data["due_reason"] == "never inspected, registered 2025-09-16"
    assert unrated.data["rating"] is None


def test_provider_groups(store):
    data = care(store).data
    assert data.provider_group("P-IND") == "independent"  # one location ever
    assert data.provider_group("P-MULTI") == "multi-site"  # three listed (some may be closed)
    assert data.provider_group("P-BRAND") == "large group"  # a CQC brand, even with one location
    assert data.provider_group("P-BIG") == "large group"  # ten registered locations
    assert data.provider_group(None) is None


def test_weekly_due_leads_and_full_list(store, tmp_path):
    vertical = care(store)
    result = run_week(vertical, store, WEEK, now=T0)["due_for_inspection"]
    # The weekly list: what became due in the week (plus the 14-day grace), not the long-standing backlog.
    assert {lead.entity_key for lead in result.leads} == {
        "cqc:location:L-DUE-RATED", "cqc:location:L-DUE-UNRATED", "cqc:location:L-BRAND"}
    folder = write_week(store, vertical, WEEK, REGIONS, tmp_path)[0].parent
    weekly = _csv(folder / "due_for_inspection.csv")
    # The large group is left out by default.
    assert [r["CQC location ID"] for r in weekly] == ["L-DUE-RATED", "L-DUE-UNRATED"]
    assert weekly[0]["Provider size"] == "independent"
    full = _csv(folder / "due_for_inspection_all.csv")
    assert [r["CQC location ID"] for r in full] == ["L-DUE-OLD", "L-DUE-RATED", "L-DUE-UNRATED"]  # oldest first
    assert full[0]["Years since rating or registration"] == "7.6"
    assert full[0]["Provider size"] == "multi-site"
    html = (folder / "digest.html").read_text()
    assert "Now due for inspection" in html and 'href="due_for_inspection_all.csv"' in html
    assert "1 leads from large groups" in html  # L-BRAND this week; the backlog isn't counted


def test_region_can_include_large_groups(store, tmp_path):
    regions = {"london": RegionConfig(cqc_region="London", include_large_groups=True)}
    vertical = care(store, regions)
    run_week(vertical, store, WEEK, now=T0)
    folder = write_week(store, vertical, WEEK, regions, tmp_path)[0].parent
    weekly = {r["CQC location ID"]: r for r in _csv(folder / "due_for_inspection.csv")}
    assert weekly["L-BRAND"]["Provider size"] == "large group"
    assert len(_csv(folder / "due_for_inspection_all.csv")) == 14
    assert "leads from large groups" not in (folder / "digest.html").read_text()


def test_site_shows_due_list_and_area_limits(store, tmp_path):
    from signals.core.feed import Week
    from signals.settings import BusinessConfig
    from signals.site.build import build_site, site_data
    from signals.verticals.care.digest import sample_leads

    weeks = [Week(date(2026, 9, 13)), WEEK]
    leads = sample_leads(care(store), weeks, "london", REGIONS["london"])
    business = BusinessConfig(legal_name="Example Ltd", address="1 Road", email="hi@example.com",
                              places_per_area=2, exclusive_price=249)
    data = site_data(business, "london", weeks, leads)
    assert data.due_total == 3 and data.counts["due_for_inspection"] == 2  # large groups left out
    assert ("3", "Due for inspection") in [(v, label) for v, label, _ in data.stats()]
    assert [r["reason"] for r in data.examples["due_for_inspection"]] == [
        "last rated Requires improvement in 2019", "last rated Good in 2022"]  # unknown legal form: never shown
    build_site(data, tmp_path, today=AS_OF)
    index = (tmp_path / "index.html").read_text()
    assert "Only 2 consultancies per area" in index and "£249 a" in index and "Due for inspection" in index
    assert "Only 2 consultancies per area" in (tmp_path / "sales-sheet.html").read_text()
    sample = (tmp_path / "sample.html").read_text()
    assert "7.6 years" in sample and "Three Homes" not in sample

    build_site(site_data(BusinessConfig(places_per_area=0, exclusive_price=None), "london", weeks, leads),
               tmp_path, today=AS_OF)
    index = (tmp_path / "index.html").read_text()
    assert "per area, first come" not in index and "exclusive plan" not in index
