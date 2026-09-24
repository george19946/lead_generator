"""Shared test setup. Tests must never touch live APIs: real network I/O raises."""

from __future__ import annotations

import json
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from signals.db.store import Store
from signals.http import RateLimiter
from signals.sources.companies_house.client import CompaniesHouseClient
from signals.sources.companies_house.source import CompaniesHouseSource
from signals.sources.cqc.client import CqcClient
from signals.sources.cqc.source import CqcSource
from signals.verticals.care import CARE_SIC_CODES
from tests.fakes import NOW, FakeCqc

FIXTURES = Path(__file__).parent / "fixtures"


class LiveNetworkError(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise LiveNetworkError("tests must not make real network calls; use httpx.MockTransport")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep a developer's real keys, config and ~/Signals out of tests: the data home is the test's tmp dir."""
    monkeypatch.delenv("CQC_API_KEY", raising=False)
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    monkeypatch.delenv("SIGNALS_CONFIG", raising=False)
    monkeypatch.setenv("SIGNALS_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)


def load_fixture(relative: str) -> Any:
    return json.loads((FIXTURES / relative).read_text())


@pytest.fixture
def fixture() -> Callable[[str], Any]:
    return load_fixture


def no_sleep(_: float) -> None:
    pass


# --- Sources wired to fake APIs (collection and CLI tests) ------------------------

@pytest.fixture
def fake():
    return FakeCqc()


@pytest.fixture
def clock():
    state = {"now": NOW}
    return state


@pytest.fixture
def cqc(fake, clock):
    client = CqcClient("k", "https://cqc.test/public/v1", RateLimiter(1000, 1),
                       transport=httpx.MockTransport(fake.handler), sleep=no_sleep)
    return CqcSource(client, clock=lambda: clock["now"])


@pytest.fixture
def ch_calls():
    return []


@pytest.fixture
def ch_profiles():
    """Company profiles served at /company/{number} by the fake Companies House (else 404)."""
    return {}


@pytest.fixture
def ch(ch_calls, ch_profiles, clock):
    def handler(request):
        ch_calls.append({"path": request.url.path, **dict(request.url.params)})
        if request.url.path.startswith("/company/"):
            number = request.url.path.rsplit("/", 1)[1]
            return httpx.Response(200, json=ch_profiles[number]) if number in ch_profiles else httpx.Response(404)
        return httpx.Response(200, json=load_fixture("synthetic/ch_advanced_search.json"))

    client = CompaniesHouseClient("k", "https://ch.test", RateLimiter(1000, 1),
                                  transport=httpx.MockTransport(handler), sleep=no_sleep)
    return CompaniesHouseSource(client, CARE_SIC_CODES, clock=lambda: clock["now"])


@pytest.fixture
def store():
    with Store.open(":memory:") as s:
        yield s
