"""The Source interface: something that fetches raw records from an external register.

Sources know nothing about feeds, verticals or customers. They return raw JSON-able
records tagged with a stable (source, entity_type, entity_id) key; the store snapshots
them and feeds interpret them.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class RawRecord:
    source: str  # e.g. "cqc", "companies_house"
    entity_type: str  # e.g. "location", "provider", "company"
    entity_id: str
    fetched_at: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class FetchWindow:
    start: datetime
    end: datetime


class Source(Protocol):
    name: str

    def fetch(self, window: FetchWindow) -> Iterator[RawRecord]:
        """Yield records that changed (or were created) within the window."""
        ...
