"""Feeds, leads and digest weeks: the vertical-agnostic shape of a lead generator.

A Feed looks at the stored register data and returns every lead that currently qualifies, each with a
stable trigger (what happened, and when). The runner keeps the ones whose event falls in the digest
week and records them once; a lead is reported in the first week that sees it and never again.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class Week:
    """A digest week: the seven days ending on (and including) `ending`."""

    ending: date

    @property
    def start(self) -> date:
        return self.ending - timedelta(days=6)

    @property
    def end_datetime(self) -> datetime:
        """The first instant after the week (exclusive bound), in UTC."""
        return datetime.combine(self.ending + timedelta(days=1), time(), tzinfo=timezone.utc)

    def previous(self) -> Week:
        return Week(self.ending - timedelta(days=7))

    @classmethod
    def last_completed(cls, today: date) -> Week:
        """The most recent Monday-to-Sunday week that has fully ended before `today`."""
        days_since_sunday = (today.weekday() + 1) % 7 or 7
        return cls(today - timedelta(days=days_since_sunday))

    def __str__(self) -> str:
        return self.ending.isoformat()


@dataclass(frozen=True)
class Lead:
    feed: str
    entity_key: str  # e.g. "cqc:location:1-123"
    trigger_key: str  # what happened, e.g. "Inadequate:2026-09-16"
    event_date: date | None  # when it happened; None if the source doesn't say
    regions: tuple[str, ...]  # customer regions the lead belongs to
    data: dict[str, Any] = field(default_factory=dict)  # flat fields for the digest and CSV


class Feed(Protocol):
    name: str

    def leads(self) -> Iterable[Lead]:
        """Every lead that currently qualifies (not only this week's)."""
        ...


class Vertical(Protocol):
    name: str

    def feeds(self) -> list[Feed]: ...
