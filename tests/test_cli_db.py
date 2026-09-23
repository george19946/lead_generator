from datetime import timedelta

import httpx
import pytest
import typer
from typer.testing import CliRunner

from signals import cli
from signals.cli import app, parse_age
from signals.db.store import Store
from signals.http import RateLimiter
from signals.sources.companies_house.client import CompaniesHouseClient
from signals.sources.companies_house.source import CompaniesHouseSource
from signals.sources.cqc.client import CqcClient
from signals.sources.cqc.source import CqcSource
from signals.verticals.care import CARE_SIC_CODES
from tests.conftest import no_sleep

runner = CliRunner()

CONFIG = """
database: data/test.db
regions:
  london:
    cqc_region: London
"""


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "signals.yaml"
    path.write_text(CONFIG)
    return path


@pytest.fixture
def fake_sources(monkeypatch, fake, clock):
    """Each command gets new clients on the same fake API (commands close their clients)."""

    def make(settings):
        cqc = CqcClient("k", "https://cqc.test/public/v1", RateLimiter(1000, 1),
                        transport=httpx.MockTransport(fake.handler), sleep=no_sleep)
        ch = CompaniesHouseClient("k", "https://ch.test", RateLimiter(1000, 1),
                                  transport=httpx.MockTransport(lambda r: httpx.Response(404)), sleep=no_sleep)
        return CqcSource(cqc, clock=lambda: clock["now"]), CompaniesHouseSource(ch, CARE_SIC_CODES)

    monkeypatch.setattr(cli, "_make_sources", make)
    return fake


def test_init_creates_database(config, tmp_path):
    result = runner.invoke(app, ["init", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "data" / "test.db").exists()
    assert "Database ready" in result.output


def test_backfill_dry_run_prints_estimate_and_fetches_no_details(config, fake_sources):
    result = runner.invoke(app, ["backfill", "--dry-run", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert "In-scope CQC locations: 3" in result.output
    assert "Estimated duration" in result.output
    assert fake_sources.detail_calls("locations") == []


def test_backfill_asks_before_fetching(config, fake_sources):
    result = runner.invoke(app, ["backfill", "--config", str(config)], input="n\n")
    assert result.exit_code == 1
    assert fake_sources.detail_calls("locations") == []


def test_backfill_then_sync(config, fake_sources, tmp_path):
    result = runner.invoke(app, ["backfill", "--yes", "--days", "7", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert "location_new 2" in result.output
    with Store.open(tmp_path / "data" / "test.db") as store:
        assert store.has("cqc", "location", "L1")

    result = runner.invoke(app, ["sync", "--config", str(config)])
    assert result.exit_code == 0, result.output


def test_sync_before_backfill_fails_clearly(config, fake_sources):
    result = runner.invoke(app, ["sync", "--config", str(config)])
    assert result.exit_code == 2
    assert "backfill" in result.output


def test_purge(config):
    result = runner.invoke(app, ["purge", "--older-than", "30d", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert "older than 30 days" in result.output


def test_parse_age():
    assert parse_age("365d") == timedelta(days=365)
    assert parse_age("52w") == timedelta(weeks=52)
    assert parse_age("30") == timedelta(days=30)
    with pytest.raises(typer.BadParameter):
        parse_age("1y")


def test_run_without_sync_prints_the_week(config, fake_sources, tmp_path):
    runner.invoke(app, ["backfill", "--yes", "--days", "7", "--config", str(config)])
    result = runner.invoke(app, ["run", "--no-sync", "--week-ending", "2026-09-20", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert "Week Mon 14 Sep to Sun 20 Sep 2026" in result.output
    assert "never_inspected:" in result.output and "poor_ratings:" in result.output


def test_run_rejects_unknown_vertical(config):
    result = runner.invoke(app, ["run", "--no-sync", "--vertical", "dentists", "--config", str(config)])
    assert result.exit_code != 0
