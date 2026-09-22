"""Companies House Source adapter: new incorporations with given SIC codes, as RawRecords."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from datetime import date, datetime

from signals.core.clock import utcnow
from signals.core.source import FetchWindow, RawRecord
from signals.sources.companies_house.client import CompaniesHouseClient

SOURCE = "companies_house"


class CompaniesHouseSource:
    """Advanced-search results hold company data only (no officers), so nothing needs stripping."""

    name = SOURCE

    def __init__(
        self,
        client: CompaniesHouseClient,
        sic_codes: Sequence[str],
        *,
        clock: Callable[[], datetime] = utcnow,
    ):
        self.client = client
        self.sic_codes = tuple(sic_codes)
        self.clock = clock

    def incorporations(self, start: date, end: date) -> Iterator[RawRecord]:
        """Companies incorporated on any day from `start` to `end` inclusive."""
        for item in self.client.iter_incorporations(self.sic_codes, start, end):
            yield RawRecord(
                source=SOURCE,
                entity_type="company",
                entity_id=str(item["company_number"]),
                fetched_at=self.clock(),
                payload=item,
            )

    def fetch(self, window: FetchWindow) -> Iterator[RawRecord]:
        return self.incorporations(window.start.date(), window.end.date())
