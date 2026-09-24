from datetime import date

from typer.testing import CliRunner

from signals.cli import app
from signals.core.feed import Week
from signals.settings import BusinessConfig, load_business
from signals.site.build import anonymise, build_site, district, mask_name, site_data
from signals.verticals.care.collect import CareScope
from signals.verticals.care.digest import sample_leads
from signals.verticals.care.feeds import CareVertical
from tests.test_care_feeds import REGIONS
from tests.test_digest import store  # noqa: F401  (the digest tests' populated store fixture)

runner = CliRunner()
WEEKS = [Week(date(2026, 9, 13)), Week(date(2026, 9, 20))]
BUSINESS = BusinessConfig(brand="Care Signals", legal_name="Example Ltd", address="1 Road, London", email="hi@example.com",
                          ico_registration="ZA000000", price_per_region=149, trial="First 4 weeks free.")


def test_mask_name_keeps_generic_words():
    assert mask_name("Sunrise Meadows Care Ltd") == "S•••••• M•••••• Care Ltd"
    assert mask_name("THE OAKS NURSING HOME") == "THE O••• NURSING HOME"
    assert mask_name(None) == ""
    assert district("SE1 7PB") == "SE1" and district(None) == ""


def _leads(store):  # noqa: F811
    return sample_leads(CareVertical(store, CareScope(REGIONS)), WEEKS, "london", REGIONS["london"])


def test_anonymise_leaves_out_people_and_masks_the_rest(store):  # noqa: F811
    leads = _leads(store)
    examples = anonymise(leads)
    # L-NEW's provider is a sole trader: never shown. L-ESC's provider is a limited company: shown, masked.
    assert [r["name"] for r in examples["never_inspected"]] == [mask_name("<b>Bold & Co</b>")]
    assert examples["poor_ratings"][0]["name"] == mask_name("Home L-RI") == "Home L-R•" and examples["poor_ratings"][0]["district"] == "E1"
    shown = str(examples)
    for secret in ("02070000000", "E1 6AN", "1 Example Road", "P-LTD", "http"):
        assert secret not in shown


def test_build_site_pages(store, tmp_path):  # noqa: F811
    data = site_data(BUSINESS, "london", WEEKS, _leads(store))
    paths = build_site(data, tmp_path / "site", today=date(2026, 9, 24))
    assert sorted(p.name for p in paths) == ["index.html", "opt-out.html", "privacy.html", "sales-sheet.html",
                                             "sample.html", "styles.css"]
    index = (tmp_path / "site" / "index.html").read_text()
    assert "London, the last 2 weeks" in index and "£149" in index and "mailto:hi@example.com" in index
    privacy = (tmp_path / "site" / "privacy.html").read_text()
    assert "Example Ltd" in privacy and "ZA000000" in privacy and "24 September 2026" in privacy
    assert 'class="todo"' not in privacy
    sample = (tmp_path / "site" / "sample.html").read_text()
    assert "&lt;b&gt;" not in sample or "B•••" in sample  # names escaped and masked
    assert "02070000000" not in sample and "Example Care Group" not in sample


def test_missing_details_are_highlighted(tmp_path):
    data = site_data(BusinessConfig(), "london", WEEKS, None)
    build_site(data, tmp_path, today=date(2026, 9, 24))
    privacy = (tmp_path / "privacy.html").read_text()
    assert 'class="todo"' in privacy and "your legal name" in privacy
    assert "Live from the registers" not in (tmp_path / "index.html").read_text()  # no numbers without data
    assert BusinessConfig().missing() == ["legal_name", "email"]


def test_site_command(tmp_path):
    (tmp_path / "business.yaml").write_text("brand: Test Leads\nemail: a@b.co\n")
    (tmp_path / "signals.yaml").write_text("regions:\n  london:\n    cqc_region: London\n")
    assert load_business().brand == "Test Leads"
    result = runner.invoke(app, ["site"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "site" / "index.html").exists()
    assert "Before publishing, fill in legal_name" in result.output and "No database yet" in result.output
    assert runner.invoke(app, ["site", "--region", "atlantis"]).exit_code != 0
