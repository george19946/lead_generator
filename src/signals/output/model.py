"""A vertical-agnostic description of a digest: sections of tabular leads, rendered as HTML and CSV."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Column:
    key: str  # key in each row dict
    label: str


@dataclass(frozen=True)
class Cell:
    """One HTML table cell: main text (optionally a link), a muted second line, and an optional badge."""

    text: str | None = None
    url: str | None = None
    sub: str | None = None
    badge: str | None = None
    tone: str = "neutral"  # badge colour: neutral, bad, warn, good, info


@dataclass(frozen=True)
class Tile:
    label: str
    value: int | str
    note: str = ""


@dataclass
class Section:
    key: str  # also the CSV file stem
    title: str
    intro: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    empty: str = "None this week."
    html_headers: list[str] = field(default_factory=list)
    html_rows: list[list[Cell]] = field(default_factory=list)  # pre-formatted cells for the HTML table
    csv_name: str | None = None  # the CSV holding this section, linked from the HTML


@dataclass
class Digest:
    title: str
    subtitle: str
    tiles: list[Tile]
    sections: list[Section]
    files: list[tuple[str, str]]  # (file name, description) listed in the digest
    notes: list[str]
