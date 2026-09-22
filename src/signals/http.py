"""Shared HTTP plumbing: a sliding-window rate limiter and a JSON client with retry/backoff.

Keys are passed to httpx as headers/auth and are never logged or included in errors.
"""

from __future__ import annotations

import logging
import random
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}


class RateLimiter:
    """Allow at most `max_requests` in any rolling `per_seconds` window."""

    def __init__(
        self,
        max_requests: int,
        per_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.max_requests = max_requests
        self.per_seconds = per_seconds
        self._clock = clock
        self._sleep = sleep
        self._sent: deque[float] = deque()

    def acquire(self) -> None:
        now = self._clock()
        while self._sent and now - self._sent[0] >= self.per_seconds:
            self._sent.popleft()
        if len(self._sent) >= self.max_requests:
            wait = self.per_seconds - (now - self._sent[0])
            if wait > 0:
                self._sleep(wait)
            now = self._clock()
            self._sent.popleft()
        self._sent.append(now)


class ApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class JsonApiClient:
    """GET-only JSON client with throttling and exponential backoff on 429/5xx/transport errors."""

    def __init__(
        self,
        base_url: str,
        limiter: RateLimiter,
        *,
        headers: dict[str, str] | None = None,
        auth: httpx.Auth | tuple[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        max_retries: int = 6,
        backoff_base: float = 1.0,
        backoff_cap: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.limiter = limiter
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._sleep = sleep
        self.request_count = 0
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers={"Accept": "application/json", "User-Agent": "signals-engine/0.1", **(headers or {})},
            auth=auth,
            transport=transport,
            timeout=timeout,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> JsonApiClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_json(
        self, path: str, params: dict[str, Any] | None = None, *, not_found_ok: bool = False
    ) -> Any:
        """GET `path` (relative to base_url) and return decoded JSON.

        Returns None for a 404 when `not_found_ok` is set.
        """
        path = path.lstrip("/")
        attempt = 0
        while True:
            self.limiter.acquire()
            self.request_count += 1
            try:
                resp = self._http.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise ApiError(f"GET {path} failed after {attempt + 1} attempts: {exc!r}") from exc
                self._backoff(attempt, None, f"transport error {type(exc).__name__}")
                attempt += 1
                continue

            if resp.status_code in RETRY_STATUSES and attempt < self.max_retries:
                self._backoff(attempt, resp.headers.get("Retry-After"), f"HTTP {resp.status_code}")
                attempt += 1
                continue
            if resp.status_code == 404 and not_found_ok:
                return None
            if resp.status_code >= 400:
                raise ApiError(
                    f"GET {path} returned HTTP {resp.status_code}: {resp.text[:300]}", resp.status_code
                )
            if not resp.content:
                return None
            return resp.json()

    def _backoff(self, attempt: int, retry_after: str | None, reason: str) -> None:
        delay = min(self.backoff_cap, self.backoff_base * 2**attempt) * (0.5 + random.random() / 2)
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        log.warning("%s; retry %d/%d in %.1fs", reason, attempt + 1, self.max_retries, delay)
        self._sleep(delay)
