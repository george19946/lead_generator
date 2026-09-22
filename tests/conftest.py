"""Shared test setup. Tests must never touch live APIs: real network I/O raises."""

from __future__ import annotations

import json
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

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
    """Keep a developer's real .env and keys out of tests."""
    monkeypatch.delenv("CQC_API_KEY", raising=False)
    monkeypatch.delenv("COMPANIES_HOUSE_API_KEY", raising=False)
    monkeypatch.delenv("SIGNALS_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)


def load_fixture(relative: str) -> Any:
    return json.loads((FIXTURES / relative).read_text())


@pytest.fixture
def fixture() -> Callable[[str], Any]:
    return load_fixture


def no_sleep(_: float) -> None:
    pass
