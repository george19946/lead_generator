"""CQC public API client (https://api-portal.service.cqc.org.uk/).

Auth: subscription key in the `Ocp-Apim-Subscription-Key` header.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from signals.http import JsonApiClient, RateLimiter
from signals.settings import Settings

SUBSCRIPTION_HEADER = "Ocp-Apim-Subscription-Key"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

EntityType = Literal["location", "provider"]


def format_timestamp(dt: datetime) -> str:
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime(TIMESTAMP_FORMAT)


class CqcClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        limiter: RateLimiter,
        *,
        transport: httpx.BaseTransport | None = None,
        **client_kwargs: Any,
    ):
        self.api = JsonApiClient(
            base_url,
            limiter,
            headers={SUBSCRIPTION_HEADER: api_key},
            transport=transport,
            **client_kwargs,
        )

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: Any) -> CqcClient:
        cfg = settings.config.sources.cqc
        limiter = RateLimiter(cfg.max_requests, cfg.per_seconds)
        return cls(settings.cqc_api_key, cfg.base_url, limiter, **kwargs)

    def close(self) -> None:
        self.api.close()

    @property
    def request_count(self) -> int:
        return self.api.request_count

    def changes_page(
        self, entity: EntityType, start: datetime, end: datetime, page: int = 1, per_page: int = 1000
    ) -> dict:
        """One page of changed IDs. The window is inclusive of start, exclusive of end."""
        params = {
            "startTimestamp": format_timestamp(start),
            "endTimestamp": format_timestamp(end),
            "page": page,
            "perPage": per_page,
        }
        return self.api.get_json(f"changes/{entity}", params) or {}

    def iter_changes(self, entity: EntityType, start: datetime, end: datetime) -> Iterator[str]:
        """Yield IDs of locations/providers changed between two timestamps (deduplicated)."""
        seen: set[str] = set()
        for page in self._pages(lambda p: self.changes_page(entity, start, end, p)):
            for change in page.get("changes") or []:
                change_id = change if isinstance(change, str) else _first_id(change)
                if change_id and change_id not in seen:
                    seen.add(change_id)
                    yield change_id

    def locations_page(self, page: int = 1, per_page: int = 1000, **filters: Any) -> dict:
        params = {k: v for k, v in filters.items() if v is not None}
        params.update(page=page, perPage=per_page)
        return self.api.get_json("locations", params) or {}

    def iter_location_summaries(self, per_page: int = 1000, **filters: Any) -> Iterator[dict]:
        """Yield the short location entries (id, name, postcode) from the list endpoint."""
        for page in self._pages(lambda p: self.locations_page(p, per_page, **filters)):
            yield from page.get("locations") or []

    def get_location(self, location_id: str) -> dict | None:
        return self.api.get_json(f"locations/{location_id}", not_found_ok=True)

    def get_provider(self, provider_id: str) -> dict | None:
        return self.api.get_json(f"providers/{provider_id}", not_found_ok=True)

    @staticmethod
    def _pages(fetch: Any) -> Iterator[dict]:
        page_no = 1
        while True:
            page = fetch(page_no)
            yield page
            total_pages = page.get("totalPages")
            if total_pages is not None:
                if page_no >= int(total_pages):
                    return
            elif not page.get("nextPageUri"):
                return
            page_no += 1


def _first_id(change: dict) -> str | None:
    for key in ("locationId", "providerId", "id"):
        if change.get(key):
            return str(change[key])
    return None
