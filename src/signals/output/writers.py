"""Write digests to disk: one CSV per section and one self-contained HTML page."""

from __future__ import annotations

import csv
import re
import shutil
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from signals.output.model import Column, Digest


def cell(value: Any) -> str:
    """CSV cell text: yes/no for booleans, empty for None."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def write_csv(path: Path, columns: list[Column], rows: Iterable[dict[str, Any]]) -> Path:
    """UTF-8 with a byte-order mark, so Excel opens it with the right encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([c.label for c in columns])
        for row in rows:
            writer.writerow([cell(row.get(c.key)) for c in columns])
    return path


_env = Environment(
    loader=PackageLoader("signals.output", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(digest: Digest) -> str:
    return _env.get_template("digest.html.j2").render(d=digest)


def write_html(path: Path, digest: Digest) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(digest), encoding="utf-8")
    return path


def purge_outputs(outputs_dir: Path, before: date) -> int:
    """Delete week folders (`<vertical>/<YYYY-MM-DD>`) and samples (`samples/<vertical>/<region>_<start>_to_<end>`)
    that ended before `before`. Returns the number of folders removed; anything else is left alone."""
    removed = 0
    if not outputs_dir.is_dir():
        return 0
    for folder in sorted(outputs_dir.glob("*/*")) + sorted(outputs_dir.glob("samples/*/*")):
        if not folder.is_dir():
            continue
        match = re.fullmatch(r"(?:.*_to_)?(\d{4}-\d{2}-\d{2})", folder.name)
        if match and date.fromisoformat(match.group(1)) < before:
            shutil.rmtree(folder)
            removed += 1
    return removed
