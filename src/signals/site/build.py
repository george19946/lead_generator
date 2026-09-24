"""Build the business website and sales sheet from ~/Signals/business.yaml and the stored data.

Pages: index (landing + pricing), sample (live numbers and anonymised examples), privacy (the notice people
whose data we use are entitled to), opt-out, and a printable one-page sales sheet. The output is plain static
files (no scripts, no cookies) that any static host can serve.

The examples are anonymised on purpose: names are masked, only the postcode district is shown, and
sole traders and partnerships are left out entirely, so the public site never names a person.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from signals.core.feed import Week
from signals.settings import BusinessConfig
from signals.verticals.care.digest import RegionLeads, region_label

PAGES = ("index.html", "sample.html", "privacy.html", "opt-out.html", "sales-sheet.html")
EXAMPLES_PER_LIST = 5
CORPORATE_FORMS = {"limited company", "LLP", "other corporate body", "public body"}

# Words kept when masking a name, so an example still reads like a care service.
GENERIC_WORDS = {
    "a", "and", "at", "by", "care", "centre", "community", "domiciliary", "group", "health", "healthcare",
    "home", "homecare", "homes", "house", "in", "limited", "living", "lodge", "ltd", "llp", "nursing", "of",
    "residential", "services", "service", "solutions", "support", "supported", "the", "uk", "agency", "court",
}


def mask_name(name: str | None) -> str:
    """'Sunrise Meadows Care Ltd' -> 'S••••• M•••• Care Ltd'. Generic words are kept; others keep one letter."""
    def mask(match: re.Match[str]) -> str:
        word = match.group(0)
        if word.lower() in GENERIC_WORDS or len(word) <= 1:
            return word
        return word[0] + "•" * (len(word) - 1)

    return re.sub(r"[A-Za-z]+", mask, name or "")


def district(postcode: str | None) -> str:
    """Only the outward part of a postcode ('SE1 7PB' -> 'SE1')."""
    parts = (postcode or "").split()
    return parts[0].upper() if parts else ""


@dataclass
class SiteData:
    business: BusinessConfig
    region: str
    weeks: list[Week]
    counts: dict[str, int] = field(default_factory=dict)
    examples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    never_inspected_total: int = 0

    @property
    def region_name(self) -> str:
        return region_label(self.region)

    @property
    def period(self) -> str:
        start, end = self.weeks[0].start, self.weeks[-1].ending
        return f"{start:%d %b} to {end:%d %b %Y}"

    @property
    def has_numbers(self) -> bool:
        return any(self.counts.values())

    def stats(self) -> list[tuple[str, str, str]]:
        """(value, label, note) for the headline numbers, leaving out zeros (they sell nothing)."""
        items = [
            (self.counts.get("poor_ratings", 0), "New poor ratings", "Requires improvement or Inadequate"),
            (self.counts.get("never_inspected", 0), "Newly registered services", "not yet inspected by CQC"),
            (self.counts.get("new_companies", 0), "New care companies",
             f"about {self.per_week('new_companies')} a week"),
            (self.never_inspected_total, "Never inspected", f"services in {self.region_name} awaiting a first inspection"),
        ]
        return [(f"{value:,}", label, note) for value, label, note in items if value]

    def per_week(self, key: str) -> str:
        value = self.counts.get(key, 0) / max(len(self.weeks), 1)
        return f"{value:.0f}" if value >= 10 or value == int(value) else f"{value:.1f}"


def _safe(row: dict[str, Any]) -> bool:
    """Only organisations: sole traders, partnerships and unknown forms never appear on the public site."""
    return row.get("legal_form") in CORPORATE_FORMS


def anonymise(leads: RegionLeads) -> dict[str, list[dict[str, Any]]]:
    poor = [
        {
            "name": mask_name(r.get("location_name")),
            "service": r.get("service_types") or "Care service",
            "area": r.get("local_authority") or "",
            "district": district(r.get("postcode")),
            "rating": r.get("rating"),
            "rating_date": r.get("rating_date"),
            "previous": r.get("previous_rating"),
            "change": r.get("rating_change"),
        }
        for r in leads.poor_ratings
        if _safe(r)
    ]
    never = [
        {
            "name": mask_name(r.get("location_name")),
            "service": r.get("service_types") or "Care service",
            "area": r.get("local_authority") or "",
            "district": district(r.get("postcode")),
            "registered": r.get("registration_date"),
        }
        for r in leads.never_inspected
        if _safe(r)
    ]
    companies = [
        {
            "name": mask_name(r.get("company_name")),
            "activity": r.get("sic_description") or "",
            "area": r.get("inferred_local_authority") or "",
            "district": district(r.get("postcode")),
            "incorporated": r.get("incorporated"),
        }
        for r in leads.new_companies
        if _safe(r) and not r.get("flag")
    ]

    def newest(rows: list[dict], key: str) -> list[dict]:
        return sorted(rows, key=lambda r: (r.get(key) or "", r["name"]), reverse=True)[:EXAMPLES_PER_LIST]

    return {
        "poor_ratings": newest(poor, "rating_date"),
        "never_inspected": newest(never, "registered"),
        "new_companies": newest(companies, "incorporated"),
    }


def site_data(business: BusinessConfig, region: str, weeks: list[Week], leads: RegionLeads | None) -> SiteData:
    data = SiteData(business=business, region=region, weeks=weeks)
    if leads is not None:
        data.counts = {
            "poor_ratings": len(leads.poor_ratings),
            "never_inspected": len(leads.never_inspected),
            "new_companies": len(leads.new_companies),
            "company_located": len(leads.company_located),
            "location_unknown": len(leads.location_unknown),
        }
        data.examples = anonymise(leads)
        data.never_inspected_total = len(leads.never_inspected_all)
    return data


_env = Environment(
    loader=PackageLoader("signals.site", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def build_site(data: SiteData, out_dir: Path, *, today: date) -> list[Path]:
    """Render every page into out_dir (replacing the previous build's pages) and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for page in PAGES:
        html = _env.get_template(f"{page}.j2").render(d=data, b=data.business, page=page, today=today)
        path = out_dir / page
        path.write_text(html, encoding="utf-8")
        paths.append(path)
    css = resources.files("signals.site").joinpath("static/styles.css")
    with resources.as_file(css) as source:
        shutil.copyfile(source, out_dir / "styles.css")
    paths.append(out_dir / "styles.css")
    return paths
