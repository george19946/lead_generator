"""CQC Source adapter: turns API responses into sanitised RawRecords ready for the store."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

from signals.core.clock import utcnow
from signals.core.source import FetchWindow, RawRecord
from signals.sources.cqc.client import CqcClient, EntityType
from signals.sources.cqc.sanitise import sanitise

SOURCE = "cqc"


class CqcSource:
    name = SOURCE

    def __init__(
        self,
        client: CqcClient,
        *,
        include_personal_names: bool = False,
        clock: Callable[[], datetime] = utcnow,
    ):
        self.client = client
        self.include_personal_names = include_personal_names
        self.clock = clock

    def _record(self, entity_type: EntityType, entity_id: str, payload: dict) -> RawRecord:
        return RawRecord(
            source=SOURCE,
            entity_type=entity_type,
            entity_id=entity_id,
            fetched_at=self.clock(),
            payload=sanitise(payload, self.include_personal_names),
        )

    def location(self, location_id: str) -> RawRecord | None:
        """The location's detail record, or None if CQC no longer has it (404)."""
        payload = self.client.get_location(location_id)
        return self._record("location", location_id, payload) if payload else None

    def provider(self, provider_id: str) -> RawRecord | None:
        payload = self.client.get_provider(provider_id)
        return self._record("provider", provider_id, payload) if payload else None

    def changed_ids(self, entity_type: EntityType, window: FetchWindow) -> Iterator[str]:
        return self.client.iter_changes(entity_type, window.start, window.end)

    def location_summaries(self, **filters: object) -> Iterator[dict]:
        """Short list entries `{locationId, locationName, postalCode}` matching the list filters."""
        return self.client.iter_location_summaries(**filters)

    def fetch(self, window: FetchWindow) -> Iterator[RawRecord]:
        """Every location and provider changed in the window (the Source protocol)."""
        for entity_type, getter in (("location", self.location), ("provider", self.provider)):
            for entity_id in self.changed_ids(entity_type, window):
                record = getter(entity_id)
                if record:
                    yield record
