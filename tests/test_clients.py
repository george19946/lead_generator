import base64
from datetime import date, datetime, timezone

import httpx

from signals.http import RateLimiter
from signals.sources.companies_house.client import CompaniesHouseClient
from signals.sources.cqc.client import SUBSCRIPTION_HEADER, CqcClient
from tests.conftest import load_fixture, no_sleep


def _cqc(handler) -> CqcClient:
    return CqcClient(
        "cqc-key", "https://cqc.test/public/v1", RateLimiter(100, 1),
        transport=httpx.MockTransport(handler), sleep=no_sleep,
    )


def _ch(handler) -> CompaniesHouseClient:
    return CompaniesHouseClient(
        "ch-key", "https://ch.test", RateLimiter(100, 1),
        transport=httpx.MockTransport(handler), sleep=no_sleep,
    )


def test_cqc_sends_subscription_header_and_timestamps():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=load_fixture("synthetic/cqc_changes_location.json"))

    start = datetime(2026, 9, 14, tzinfo=timezone.utc)
    end = datetime(2026, 9, 21, 1, 2, 3, tzinfo=timezone.utc)
    ids = list(_cqc(handler).iter_changes("location", start, end))

    assert ids == ["1-900000001", "1-900000002"]
    req = seen[0]
    assert req.headers[SUBSCRIPTION_HEADER] == "cqc-key"
    assert req.url.path == "/public/v1/changes/location"
    assert req.url.params["startTimestamp"] == "2026-09-14T00:00:00Z"
    assert req.url.params["endTimestamp"] == "2026-09-21T01:02:03Z"


def test_cqc_changes_paginates_and_dedupes():
    pages = {
        "1": {"changes": ["a", "b"], "page": 1, "totalPages": 2},
        "2": {"changes": ["b", "c"], "page": 2, "totalPages": 2},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params["page"]])

    now = datetime(2026, 9, 21, tzinfo=timezone.utc)
    assert list(_cqc(handler).iter_changes("provider", now, now)) == ["a", "b", "c"]


def test_cqc_pagination_falls_back_to_next_page_uri():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(200, json={
            "locations": [{"locationId": f"L{page}"}],
            "nextPageUri": "/locations?page=2" if page == 1 else None,
        })

    summaries = list(_cqc(handler).iter_location_summaries(inspectionDirectorate="Adult social care"))
    assert [s["locationId"] for s in summaries] == ["L1", "L2"]


def test_cqc_get_location_404_returns_none():
    assert _cqc(lambda r: httpx.Response(404)).get_location("1-x") is None


def test_ch_uses_basic_auth_with_key_as_username():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=load_fixture("synthetic/ch_advanced_search.json"))

    result = _ch(handler).advanced_search(
        sic_codes=["87100", "88100"], incorporated_from=date(2026, 9, 14), incorporated_to=date(2026, 9, 20)
    )
    assert result["hits"] == 3
    req = seen[0]
    assert req.headers["Authorization"] == "Basic " + base64.b64encode(b"ch-key:").decode()
    assert req.url.path == "/advanced-search/companies"
    assert req.url.params["sic_codes"] == "87100,88100"
    assert req.url.params["incorporated_from"] == "2026-09-14"
    assert req.url.params["incorporated_to"] == "2026-09-20"


def test_ch_404_means_no_results():
    client = _ch(lambda r: httpx.Response(404))
    assert list(client.iter_incorporations(["87100"], date(2026, 9, 1), date(2026, 9, 7))) == []


def test_ch_slices_by_week_and_pages_with_start_index():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.params
        requests.append((p["incorporated_from"], p["incorporated_to"], p["start_index"]))
        start = int(p["start_index"])
        prefix = p["incorporated_from"]
        items = [{"company_number": f"{prefix}-{i}"} for i in range(start, min(start + 2, 3))]
        return httpx.Response(200, json={"hits": 3, "items": items})

    client = _ch(handler)
    got = list(client.iter_incorporations(["87100"], date(2026, 9, 1), date(2026, 9, 10), page_size=2))
    assert len(got) == 6  # 3 per slice, 2 slices
    assert requests == [
        ("2026-09-01", "2026-09-07", "0"), ("2026-09-01", "2026-09-07", "2"),
        ("2026-09-08", "2026-09-10", "0"), ("2026-09-08", "2026-09-10", "2"),
    ]


def test_ch_splits_range_when_hits_exceed_result_window():
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.params
        if p["incorporated_from"] != p["incorporated_to"]:
            return httpx.Response(200, json={"hits": 20_000, "items": [{"company_number": "ignored"}]})
        return httpx.Response(200, json={"hits": 1, "items": [{"company_number": p["incorporated_from"]}]})

    got = list(_ch(handler).iter_incorporations(["87100"], date(2026, 9, 1), date(2026, 9, 4)))
    assert [c["company_number"] for c in got] == ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]
