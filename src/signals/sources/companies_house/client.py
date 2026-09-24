"""Companies House public data API client (https://developer.company-information.service.gov.uk/).

Auth: HTTP basic auth with the API key as the username and an empty password.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from datetime import date, timedelta
from typing import Any

import httpx

from signals.http import JsonApiClient, RateLimiter
from signals.settings import Settings

log = logging.getLogger(__name__)

MAX_PAGE_SIZE = 5000
# Advanced search fails once start_index passes ~10,000, so narrower date slices are used instead.
MAX_RESULT_WINDOW = 10_000


class CompaniesHouseClient:
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
            base_url, limiter, auth=(api_key, ""), transport=transport, **client_kwargs
        )

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: Any) -> CompaniesHouseClient:
        cfg = settings.config.sources.companies_house
        limiter = RateLimiter(cfg.max_requests, cfg.per_seconds)
        return cls(settings.companies_house_api_key, cfg.base_url, limiter, **kwargs)

    def close(self) -> None:
        self.api.close()

    @property
    def request_count(self) -> int:
        return self.api.request_count

    def advanced_search(
        self,
        *,
        sic_codes: Sequence[str],
        incorporated_from: date,
        incorporated_to: date,
        size: int = MAX_PAGE_SIZE,
        start_index: int = 0,
    ) -> dict:
        params = {
            "sic_codes": ",".join(sic_codes),
            "incorporated_from": incorporated_from.isoformat(),
            "incorporated_to": incorporated_to.isoformat(),
            "size": size,
            "start_index": start_index,
        }
        # Advanced search answers 404 when nothing matches.
        return self.api.get_json("advanced-search/companies", params, not_found_ok=True) or {}

    def search_by_name(
        self, name_includes: str, *, company_types: Sequence[str] = (), status: str = "active",
        size: int = MAX_PAGE_SIZE, start_index: int = 0,
    ) -> dict:
        """Advanced search on a phrase in the company name (e.g. prospects: "care consultancy")."""
        params: dict[str, object] = {"company_name_includes": name_includes, "company_status": status,
                                     "size": size, "start_index": start_index}
        if company_types:
            params["company_type"] = ",".join(company_types)
        return self.api.get_json("advanced-search/companies", params, not_found_ok=True) or {}

    def get_company(self, company_number: str) -> dict | None:
        """The company profile (current registered office, status...), or None if not found."""
        return self.api.get_json(f"company/{company_number}", not_found_ok=True)

    def iter_incorporations(
        self,
        sic_codes: Sequence[str],
        incorporated_from: date,
        incorporated_to: date,
        *,
        slice_days: int = 7,
        page_size: int = MAX_PAGE_SIZE,
    ) -> Iterator[dict]:
        """Yield companies incorporated in [from, to] with any of the SIC codes, deduplicated."""
        seen: set[str] = set()
        start = incorporated_from
        while start <= incorporated_to:
            end = min(start + timedelta(days=slice_days - 1), incorporated_to)
            for item in self._iter_slice(sic_codes, start, end, page_size):
                number = item.get("company_number")
                if number and number not in seen:
                    seen.add(number)
                    yield item
            start = end + timedelta(days=1)

    def _iter_slice(self, sic_codes: Sequence[str], start: date, end: date, page_size: int) -> Iterator[dict]:
        first = self.advanced_search(
            sic_codes=sic_codes, incorporated_from=start, incorporated_to=end, size=page_size
        )
        hits = int(first.get("hits") or 0)
        if hits > MAX_RESULT_WINDOW and start < end:
            mid = start + (end - start) // 2
            log.info("%d hits for %s..%s; splitting the date range", hits, start, end)
            yield from self._iter_slice(sic_codes, start, mid, page_size)
            yield from self._iter_slice(sic_codes, mid + timedelta(days=1), end, page_size)
            return
        items = first.get("items") or []
        yield from items
        fetched = len(items)
        while items and fetched < min(hits, MAX_RESULT_WINDOW):
            page = self.advanced_search(
                sic_codes=sic_codes,
                incorporated_from=start,
                incorporated_to=end,
                size=page_size,
                start_index=fetched,
            )
            items = page.get("items") or []
            yield from items
            fetched += len(items)
