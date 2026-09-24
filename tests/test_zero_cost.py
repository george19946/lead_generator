"""Companies-only mode, the email teaser and the prospect list."""

from datetime import date

from typer.testing import CliRunner

from signals.cli import app
from signals.core.feed import Week
from signals.core.regions import PostcodeLookup
from signals.db.store import Store
from signals.settings import RegionConfig
from signals.sources.companies_house.models import ChCompany
from signals.verticals.care.collect import CareScope
from signals.verticals.care.digest import email_teaser, sample_leads
from signals.verticals.care.feeds import CareVertical
from signals.verticals.care.policy import (
    COMPANIES_ONLY_NOTE,
    apply_companies_only,
    lift_companies_only,
)
from signals.verticals.care.prospects import build_rows, search
from tests.test_care_feeds import LOCATIONS, PROVIDERS, T0, location, save

runner = CliRunner()


def _store(path=":memory:"):
    store = Store.open(path)
    for loc in LOCATIONS:
        save(store, "cqc", "location", loc["locationId"], loc)
    for pid, prov in PROVIDERS.items():
        save(store, "cqc", "provider", pid, prov)
    return store


def test_companies_only_erases_and_blocks_sole_traders():
    with _store() as store:
        store.suppress("P-OPTED-OUT", "asked to be removed", T0)  # a real opt-out
        assert store.get("cqc", "location", "L-NEW")  # the sole trader's location
        assert apply_companies_only(store, T0) == 1
        assert store.get("cqc", "provider", "P-SOLE") is None
        assert store.get("cqc", "location", "L-NEW") is None
        assert store.get("cqc", "provider", "P-LTD")  # companies stay
        # Not stored again, even when re-fetched.
        save(store, "cqc", "location", "L-NEW", location("L-NEW", provider="P-SOLE"))
        assert store.get("cqc", "location", "L-NEW") is None
        assert apply_companies_only(store, T0) == 0
        # Turning the mode off lifts only its own blocks, never a real opt-out.
        assert lift_companies_only(store) == 1
        assert [s[0] for s in store.suppressed()] == ["P-OPTED-OUT"]


def test_cli_applies_companies_only(tmp_path):
    (tmp_path / "signals.yaml").write_text("database: data/test.db\nregions:\n  london:\n    cqc_region: London\n")
    (tmp_path / "data").mkdir()
    _store(str(tmp_path / "data" / "test.db")).close()
    result = runner.invoke(app, ["suppress"])
    assert result.exit_code == 0, result.output
    assert "Companies-only mode: removed 1 sole traders" in result.output
    (tmp_path / "signals.yaml").write_text(
        "database: data/test.db\ncompanies_only: false\nregions:\n  london:\n    cqc_region: London\n")
    result = runner.invoke(app, ["suppress"])
    assert "included again (1)" in result.output and "backfill --only-new" in result.output
    with Store.open(tmp_path / "data" / "test.db") as store:
        assert not any(note == COMPANIES_ONLY_NOTE for _, _, note in store.suppressed())


def test_email_teaser_names_only_organisations():
    regions = {"london": RegionConfig(cqc_region="London", include_large_groups=True)}
    with _store() as store:
        save(store, "cqc", "location", "L-AGED", location("L-AGED", rating="Good", rating_date="2019-05-02"))
        save(store, "cqc", "location", "L-AGED-SOLE", location("L-AGED-SOLE", provider="P-SOLE", rating="Good",
                                                             rating_date="2018-05-02"))
        weeks = [Week(date(2026, 9, 13)), Week(date(2026, 9, 20))]
        leads = sample_leads(CareVertical(store, CareScope(regions), as_of=T0.date()), weeks, "london",
                             regions["london"])
        text = email_teaser(leads, weeks)
    assert "Due for inspection now: 2 services" in text  # counted, but...
    assert "Home L-AGED-SOLE" not in text  # ...a sole trader is never named
    assert "Home L-AGED (Tower Hamlets): last rated Good on 2019-05-02" in text
    assert "Home L-RI (Tower Hamlets): Requires improvement on 2026-09-16, was Good" in text
    assert "For example, Home L-AGED in Tower Hamlets" in text


class FakeCh:
    def __init__(self, items):
        self.items, self.calls = items, []

    def search_by_name(self, phrase, *, company_types, start_index=0, **_):
        self.calls.append((phrase, start_index))
        return {"items": self.items if phrase == "care consultancy" else []}

    @property
    def request_count(self):
        return len(self.calls)


def _company(number, name, postcode="E1 6AN", created="2025-01-01"):
    return {"company_number": number, "company_name": name, "company_type": "ltd", "date_of_creation": created,
            "sic_codes": ["70229"], "registered_office_address": {"postal_code": postcode}}


def test_prospects_are_care_consultancies_in_your_regions_first():
    ch = FakeCh([
        _company("1", "SUNRISE CARE CONSULTANCY LTD", created="2024-01-01"),
        _company("2", "NEW CQC ADVISORY LTD", created="2026-09-01"),
        _company("3", "FAR AWAY CARE CONSULTANTS LTD", postcode="LS1 1AA", created="2026-09-10"),
        _company("4", "TREE CARE CONSULTANCY LTD"),  # not our kind of care
        _company("5", "QUALITY CARE HOMES LTD"),  # a care provider, not a consultancy
    ])
    companies, requests = search(ch)
    assert requests == len(ch.calls) and len(companies) == 5
    scope = CareScope({"london": RegionConfig(postcode_areas=["E"])})
    rows, skipped = build_rows(companies, PostcodeLookup(), scope)
    assert skipped == 2
    assert [r["company_number"] for r in rows] == ["2", "1", "3"]  # London first, newest first
    assert rows[0]["regions"] == "london" and rows[0]["approved"] == "" and rows[2]["regions"] == ""
    only, _ = build_rows(companies, PostcodeLookup(), scope, region="london")
    assert [r["company_number"] for r in only] == ["2", "1"]
    assert ChCompany.model_validate(ch.items[0]).url.endswith("/company/1")
