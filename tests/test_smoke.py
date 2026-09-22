import json
from datetime import datetime, timezone

import httpx
from typer.testing import CliRunner

from signals.cli import app
from signals.http import RateLimiter
from signals.smoke import run_smoke
from signals.sources.companies_house.client import CompaniesHouseClient
from signals.sources.cqc.client import CqcClient
from tests.conftest import load_fixture, no_sleep


def _cqc_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path.removeprefix("/v1/")
    if path.startswith("changes/"):
        return httpx.Response(200, json=load_fixture("synthetic/cqc_changes_location.json"))
    if path == "locations":
        return httpx.Response(200, json={"total": 1, "totalPages": 1, "locations": [{"locationId": "1-900000002"}]})
    if path == "locations/1-900000001":
        return httpx.Response(200, json=load_fixture("synthetic/cqc_location_rated_ri.json"))
    if path == "locations/1-900000002":
        return httpx.Response(200, json=load_fixture("synthetic/cqc_location_never_inspected.json"))
    if path.startswith("providers/"):
        prov = load_fixture("synthetic/cqc_provider_limited.json")
        return httpx.Response(200, json={**prov, "providerId": path.split("/")[1]})
    return httpx.Response(404)


def test_smoke_runs_offline_and_saves_sanitised_fixtures(tmp_path):
    cqc = CqcClient("k", "https://cqc.test/v1", RateLimiter(100, 1), transport=httpx.MockTransport(_cqc_handler), sleep=no_sleep)
    ch = CompaniesHouseClient(
        "k", "https://ch.test", RateLimiter(100, 1),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=load_fixture("synthetic/ch_advanced_search.json"))),
        sleep=no_sleep,
    )
    report = run_smoke(cqc, ch, n=5, fixtures_dir=tmp_path, now=datetime(2026, 9, 21, tzinfo=timezone.utc))

    assert report.problems == []
    assert any("CQC fetched 2 locations" in line for line in report.lines)
    saved = json.loads((tmp_path / "cqc" / "location_1-900000001.json").read_text())
    assert "Jane" not in json.dumps(saved)
    provider = json.loads((tmp_path / "cqc" / "provider_1-800000001.json").read_text())
    assert "John" not in json.dumps(provider)
    assert (tmp_path / "companies_house" / "advanced_search.json").exists()


def test_smoke_cli_without_keys_exits_cleanly():
    result = CliRunner().invoke(app, ["smoke"])
    assert result.exit_code == 2
    assert "CQC_API_KEY is not set" in result.output
