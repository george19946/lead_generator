import csv
from datetime import date

import pytest

from signals.core.feed import Week
from signals.core.runner import run_week
from signals.db.store import Store
from signals.output.model import Column
from signals.output.writers import write_csv
from signals.settings import RegionConfig
from signals.verticals.care.collect import CareScope
from signals.verticals.care.digest import write_sample, write_week
from signals.verticals.care.feeds import CareVertical
from tests.test_care_feeds import LOCATIONS, PROVIDERS, REGIONS, T0, WEEK, companies, location, save

AGENT_POSTCODE = "WC2H 9JQ"


@pytest.fixture
def store():
    with Store.open(":memory:") as s:
        for loc in LOCATIONS:
            save(s, "cqc", "location", loc["locationId"], loc)
        # A name that must be HTML-escaped.
        save(s, "cqc", "location", "L-ESC", location("L-ESC", registered="2026-09-16", name="<b>Bold & Co</b>"))
        for pid, prov in PROVIDERS.items():
            save(s, "cqc", "provider", pid, prov)
        for company in companies():
            save(s, "companies_house", "company", company["company_number"], company)
        for n in range(5):  # a formation agent's clients
            number = f"1800000{n}"
            save(s, "companies_house", "company", number, {
                "company_number": number, "company_name": f"AGENT CLIENT {n} CARE LTD", "company_type": "ltd",
                "date_of_creation": "2026-09-16", "sic_codes": ["88100", "78200"],
                "registered_office_address": {"address_line_1": "71-75 Shelton Street", "postal_code": AGENT_POSTCODE}})
        yield s


def _run_and_write(store, tmp_path, regions=REGIONS):
    care = CareVertical(store, CareScope(regions))
    run_week(care, store, WEEK, now=T0)
    return write_week(store, care, WEEK, regions, tmp_path)


def _csv(path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_write_csv_uses_bom_and_plain_cells(tmp_path):
    path = write_csv(tmp_path / "x.csv", [Column("a", "A"), Column("b", "B"), Column("c", "C")],
                     [{"a": True, "b": None, "c": 3}, {"a": False, "b": "x, y", "c": "é"}])
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8-sig").splitlines() == ["A,B,C", "yes,,3", 'no,"x, y",é']


def test_week_outputs_per_region(store, tmp_path):
    paths = _run_and_write(store, tmp_path)
    assert [p.parent.name for p in paths] == ["london", "east-london"]
    folder = tmp_path / "care" / "2026-09-20" / "london"
    assert sorted(p.name for p in folder.iterdir()) == [
        "company_located.csv", "digest.html", "due_for_inspection.csv", "due_for_inspection_all.csv",
        "location_unknown.csv", "never_inspected.csv", "never_inspected_all.csv", "new_companies.csv",
        "poor_ratings.csv",
    ]
    poor = _csv(folder / "poor_ratings.csv")
    assert [(r["Location"], r["Rating"], r["Previous rating"], r["Change"]) for r in poor] == [
        ("Home L-RI", "Requires improvement", "Good", "downgrade")]
    assert poor[0]["Contact rule"] == "email OK"
    never = {r["CQC location ID"] for r in _csv(folder / "never_inspected.csv")}
    assert never == {"L-NEW", "L-ESC"}
    never_all = _csv(folder / "never_inspected_all.csv")
    assert {r["CQC location ID"] for r in never_all} == {"L-NEW", "L-ESC", "L-OLD-NEVER"}
    assert next(r for r in never_all if r["CQC location ID"] == "L-OLD-NEVER")["Days registered"] == "142"
    unknown = _csv(folder / "location_unknown.csv")
    assert len(unknown) == 5 and unknown[0]["New care companies at this postcode"] == "5"
    assert unknown[0]["Activity (SIC)"] == "domiciliary / social work without accommodation; temporary staffing agency"
    # East London gets only its own leads, plus the same national list.
    east = tmp_path / "care" / "2026-09-20" / "east-london"
    assert {r["CQC location ID"] for r in _csv(east / "never_inspected.csv")} == {"L-NEW", "L-ESC"}  # IG1, E1
    assert _csv(east / "poor_ratings.csv")[0]["Postcode"] == "E1 6AN"
    assert len(_csv(east / "location_unknown.csv")) == 5


def test_digest_html(store, tmp_path):
    html = _run_and_write(store, tmp_path)[0].read_text()
    assert "<title>Care leads: London</title>" in html
    assert "Week Mon 14 Sep to Sun 20 Sep 2026" in html
    assert "&lt;b&gt;Bold &amp; Co&lt;/b&gt;" in html and "<b>Bold" not in html
    assert 'href="poor_ratings.csv"' in html
    assert "Contains CQC data" in html
    assert "Now located in your region" in html and 'href="company_located.csv"' in html
    assert "https://www.cqc.org.uk/location/L-RI" in html


def test_outputs_are_deterministic(store, tmp_path):
    first = {p.name: p.read_bytes() for p in _run_and_write(store, tmp_path)[0].parent.iterdir()}
    second = {p.name: p.read_bytes() for p in _run_and_write(store, tmp_path)[0].parent.iterdir()}
    assert first == second


def test_region_can_opt_out_of_location_unknown(store, tmp_path):
    regions = {"london": RegionConfig(cqc_region="London", location_unknown=False)}
    folder = _run_and_write(store, tmp_path, regions)[0].parent
    assert _csv(folder / "location_unknown.csv") == []


def test_sample_records_nothing(store, tmp_path):
    care = CareVertical(store, CareScope(REGIONS))
    weeks = [Week(date(2026, 9, 13)), WEEK]
    path = write_sample(care, weeks, "london", REGIONS["london"], tmp_path)
    assert path.parent.name == "london_2026-09-07_to_2026-09-20"
    assert store.counts()["lead_events"] == 0
    assert "Sample: 2 weeks" in path.read_text()
    assert {r["CQC location ID"] for r in _csv(path.parent / "poor_ratings.csv")} == {"L-RI"}
