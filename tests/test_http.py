import httpx
import pytest

from signals.http import ApiError, JsonApiClient, RateLimiter
from tests.conftest import LiveNetworkError, no_sleep


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_rate_limiter_waits_when_window_full():
    clock = FakeClock()
    limiter = RateLimiter(3, 10, clock=clock, sleep=clock.sleep)
    for _ in range(3):
        limiter.acquire()
    assert clock.slept == []
    limiter.acquire()
    assert clock.slept == [10]


def test_rate_limiter_frees_slots_after_window():
    clock = FakeClock()
    limiter = RateLimiter(2, 5, clock=clock, sleep=clock.sleep)
    limiter.acquire()
    clock.now = 3
    limiter.acquire()
    clock.now = 6  # first request has aged out
    limiter.acquire()
    assert clock.slept == []


def _client(handler, **kw) -> JsonApiClient:
    return JsonApiClient(
        "https://api.test/v1", RateLimiter(100, 1), transport=httpx.MockTransport(handler), sleep=no_sleep, **kw
    )


def test_retries_on_429_then_succeeds():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"ok": True})

    client = _client(handler)
    assert client.get_json("thing") == {"ok": True}
    assert len(calls) == 3
    assert client.request_count == 3


def test_gives_up_after_max_retries():
    client = _client(lambda r: httpx.Response(503), max_retries=2)
    with pytest.raises(ApiError) as exc:
        client.get_json("thing")
    assert exc.value.status_code == 503


def test_404_can_be_tolerated():
    client = _client(lambda r: httpx.Response(404))
    assert client.get_json("missing", not_found_ok=True) is None
    with pytest.raises(ApiError):
        client.get_json("missing")


def test_error_message_does_not_leak_api_key():
    client = JsonApiClient(
        "https://api.test/v1",
        RateLimiter(100, 1),
        headers={"X-Key": "sekret-key"},
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="denied")),
        sleep=no_sleep,
    )
    with pytest.raises(ApiError) as exc:
        client.get_json("thing")
    assert "sekret-key" not in str(exc.value)


def test_live_network_is_blocked():
    with pytest.raises(LiveNetworkError):
        httpx.get("https://example.com")
