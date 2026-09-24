"""The care digest: per region, one HTML page plus a CSV per lead list.

outputs/care/<week_ending>/<region>/
    digest.html              this week's leads, all lists
    poor_ratings.csv         new Requires improvement / Inadequate ratings
    never_inspected.csv      newly registered locations with no inspection yet
    due_for_inspection.csv   locations that became due for inspection this week (aged rating, or a year unrated)
    new_companies.csv        new care companies placed in the region
    location_unknown.csv     new care companies at formation-agent addresses (national)
    company_located.csv      formation-agent companies that have now revealed a location in the region
    never_inspected_all.csv  every never-inspected location in the region, as the database stands now
    due_for_inspection_all.csv  every location in the region currently due for inspection, oldest first

Everything except the *_all.csv files comes from the recorded lead events, so re-running a week writes the
same files. Locations of large groups (a CQC brand, or 10+ locations) are left out unless the region sets
include_large_groups: they have in-house quality teams and rarely hire consultants.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from signals.core.feed import Lead, Week
from signals.core.legal_form import EMAIL_OK, PHONE_CHECK_TPS, POST_ONLY
from signals.db.store import LeadRow, Store
from signals.output.model import Cell, Column, Digest, Section, Tile
from signals.output.writers import write_csv, write_html
from signals.settings import RegionConfig
from signals.verticals.care.feeds import (
    ALL_ENGLAND,
    INDEPENDENT,
    LARGE_GROUP,
    MULTI_SITE,
    NATIONAL,
    CareVertical,
    DueForInspectionFeed,
    NeverInspectedFeed,
)
from signals.verticals.care.flags import name_flag, sic_labels

CHANNEL_TONE = {EMAIL_OK: "good", PHONE_CHECK_TPS: "info", POST_ONLY: "neutral"}
RATING_TONE = {"Inadequate": "bad", "Requires improvement": "warn"}
GROUP_TONE = {INDEPENDENT: "good", MULTI_SITE: "info", LARGE_GROUP: "neutral"}
LOCATION_FEEDS = ("poor_ratings", "never_inspected", "due_for_inspection")

LOCATION_COLUMNS = [
    Column("location_name", "Location"),
    Column("address", "Address"),
    Column("postcode", "Postcode"),
    Column("local_authority", "Local authority"),
    Column("service_types", "Service types"),
    Column("care_home", "Care home"),
    Column("beds", "Beds"),
    Column("phone", "Phone"),
    Column("website", "Website"),
    Column("provider_name", "Provider"),
    Column("provider_group", "Provider size"),
    Column("legal_form", "Legal form"),
    Column("suggested_channel", "Contact rule"),
    Column("provider_company_number", "Company number"),
    Column("cqc_url", "CQC profile"),
    Column("provider_url", "CQC provider profile"),
    Column("companies_house_url", "Companies House"),
    Column("location_id", "CQC location ID"),
    Column("provider_id", "CQC provider ID"),
    Column("regions", "Regions"),
]
POOR_COLUMNS = [
    Column("location_name", "Location"),
    Column("rating", "Rating"),
    Column("rating_date", "Rating published"),
    Column("previous_rating", "Previous rating"),
    Column("previous_rating_date", "Previous rating date"),
    Column("rating_change", "Change"),
    Column("rating_framework", "Rating source"),
    *LOCATION_COLUMNS[1:],
]
NEVER_COLUMNS = [
    Column("location_name", "Location"),
    Column("registration_date", "Registered"),
    Column("dormant", "Dormant"),
    *LOCATION_COLUMNS[1:],
]
NEVER_ALL_COLUMNS = [NEVER_COLUMNS[0], NEVER_COLUMNS[1], Column("days_registered", "Days registered"), *NEVER_COLUMNS[2:]]
DUE_COLUMNS = [
    Column("location_name", "Location"),
    Column("due_reason", "Why due"),
    Column("years_waiting", "Years since rating or registration"),
    Column("rating", "Current rating"),
    Column("rating_date", "Rating date"),
    Column("registration_date", "Registered"),
    Column("dormant", "Dormant"),
    *LOCATION_COLUMNS[1:],
]
COMPANY_COLUMNS = [
    Column("company_name", "Company"),
    Column("incorporated", "Incorporated"),
    Column("flag", "Check"),
    Column("sic_description", "Activity (SIC)"),
    Column("sic_codes", "SIC codes"),
    Column("address", "Registered office"),
    Column("postcode", "Postcode"),
    Column("inferred_local_authority", "Local authority (inferred)"),
    Column("legal_form", "Legal form"),
    Column("suggested_channel", "Contact rule"),
    Column("cqc_registered", "CQC registered"),
    Column("cqc_provider_name", "CQC provider (matched)"),
    Column("cqc_match", "Match method"),
    Column("cqc_match_score", "Match score"),
    Column("companies_house_url", "Companies House"),
    Column("company_number", "Company number"),
    Column("regions", "Regions"),
]
UNKNOWN_COLUMNS = [
    Column("company_name", "Company"),
    Column("incorporated", "Incorporated"),
    Column("flag", "Check"),
    Column("sic_description", "Activity (SIC)"),
    Column("sic_codes", "SIC codes"),
    Column("address", "Registered office"),
    Column("postcode", "Postcode"),
    Column("companies_at_postcode", "New care companies at this postcode"),
    Column("legal_form", "Legal form"),
    Column("suggested_channel", "Contact rule"),
    Column("companies_house_url", "Companies House"),
    Column("company_number", "Company number"),
]

LOCATED_COLUMNS = [
    Column("company_name", "Company"),
    Column("located_by", "How located"),
    Column("located_date", "Located on"),
    Column("previous_postcode", "Previous (formation agent) postcode"),
    Column("address", "Registered office"),
    Column("postcode", "Postcode"),
    Column("inferred_local_authority", "Local authority"),
    Column("cqc_provider_name", "CQC provider"),
    Column("cqc_provider_address", "CQC provider address"),
    Column("cqc_provider_postcode", "CQC provider postcode"),
    *[c for c in COMPANY_COLUMNS if c.key in (
        "incorporated", "flag", "sic_description", "legal_form", "suggested_channel", "companies_house_url",
        "company_number", "regions")],
]

NOTES = [
    "Each lead is listed once, in the week it is first found. Events that registers publish late are still picked up "
    "for up to 14 days.",
    "Contact rules (PECR): “email OK” means a corporate subscriber (company, LLP, public body), so marketing "
    "email is allowed with an opt-out. “phone”: screen the number against TPS/CTPS before calling. "
    "“post only”: sole traders and partnerships with no phone number listed. An unknown legal form is "
    "treated with the stricter rule.",
    "“Due for inspection”: the current rating is 4 or more years old, or the service has waited a year since "
    "registering without an inspection. CQC is inspecting the oldest ratings first. Provider size: "
    "“independent” has one location; “large group” is a CQC brand or 10+ locations.",
    "Sole-trader provider names are personal data: use them only to offer relevant services, and stop if asked.",
    "Contains CQC data © Care Quality Commission, licensed under the Open Government Licence v3.0. "
    "Contains Companies House data.",
]


def region_label(key: str) -> str:
    return key.replace("-", " ").replace("_", " ").title()


def _row(lead: LeadRow | Lead, groups: Mapping[str, str] | None = None) -> dict[str, Any]:
    row = {**lead.data, "regions": ", ".join(lead.regions)}
    if "company_name" in row:  # derived at render time, so older events get the current labels too
        row["flag"] = name_flag(row.get("company_name"))
        row["sic_description"] = sic_labels(row.get("sic_codes"))
    if groups is not None and row.get("provider_id") in groups:
        row["provider_group"] = groups[row["provider_id"]]
    return row


def _website_url(site: str | None) -> str | None:
    if not site:
        return None
    return site if site.startswith(("http://", "https://")) else f"https://{site}"


def _service(row: dict) -> Cell:
    home = row.get("care_home") == "Y"
    detail = f"care home, {row['beds']} beds" if home and row.get("beds") else ("care home" if home else None)
    return Cell(row.get("service_types") or "Not stated", sub=detail)


def _contact(row: dict) -> Cell:
    channel = row.get("suggested_channel")
    return Cell(row.get("phone"), sub=row.get("website"), badge=channel, tone=CHANNEL_TONE.get(channel, "neutral"))


def _provider(row: dict) -> Cell:
    sub = row.get("legal_form")
    if row.get("provider_company_number"):
        sub = f"{sub}, {row['provider_company_number']}"
    group = row.get("provider_group")
    return Cell(row.get("provider_name") or "Unknown", url=row.get("provider_url"), sub=sub,
                badge=group, tone=GROUP_TONE.get(group, "neutral"))


def _location(row: dict) -> Cell:
    return Cell(row.get("location_name"), url=row.get("cqc_url"), sub=row.get("address"))


def _area(row: dict) -> Cell:
    return Cell(row.get("local_authority"), sub=row.get("postcode"))


def _days(since: str | None, until: date) -> int | None:
    return (until - date.fromisoformat(since)).days if since else None


def _years(since: str | None, until: date) -> float | None:
    days = _days(since, until)
    return round(days / 365.25, 1) if days is not None else None


def _sort_poor(rows: list[dict]) -> list[dict]:
    severity = {"Inadequate": 0, "Requires improvement": 1}
    rows = sorted(rows, key=lambda r: (r.get("location_name") or "", r.get("location_id") or ""))
    rows = sorted(rows, key=lambda r: r.get("rating_date") or "", reverse=True)
    return sorted(rows, key=lambda r: severity.get(r.get("rating"), 2))


def _sort_by_date(rows: list[dict], key: str, name: str, flagged_last: bool = False) -> list[dict]:
    rows = sorted(rows, key=lambda r: (r.get(name) or "", r.get("company_number") or r.get("location_id") or ""))
    rows = sorted(rows, key=lambda r: r.get(key) or "", reverse=True)
    return sorted(rows, key=lambda r: bool(r.get("flag"))) if flagged_last else rows


def poor_ratings_section(rows: list[dict]) -> Section:
    rows = _sort_poor(rows)
    html = []
    for r in rows:
        change = r.get("rating_change")
        html.append([
            _location(r),
            Cell(badge=r.get("rating"), tone=RATING_TONE.get(r.get("rating"), "neutral"),
                 sub=f"published {r['rating_date']}" if r.get("rating_date") else "date not published"),
            Cell(r.get("previous_rating") or "No earlier rating", sub=r.get("previous_rating_date"),
                 badge="downgrade" if change == "downgrade" else None, tone="bad"),
            _service(r), _area(r), _contact(r), _provider(r),
        ])
    return Section(
        key="poor_ratings", title="New poor ratings",
        intro="Locations newly rated Requires improvement or Inadequate. They usually need an action plan and "
              "support before re-inspection.",
        columns=POOR_COLUMNS, rows=rows, csv_name="poor_ratings.csv",
        html_headers=["Location", "Rating", "Previously", "Service", "Area", "Contact", "Provider"], html_rows=html,
    )


def never_inspected_section(rows: list[dict], week_ending: date) -> Section:
    rows = _sort_by_date(rows, "registration_date", "location_name")
    html = []
    for r in rows:
        days = _days(r.get("registration_date"), week_ending)
        html.append([
            _location(r),
            Cell(r.get("registration_date"), sub=f"{days} days before the week ended" if days is not None else None,
                 badge="dormant" if r.get("dormant") else None),
            _service(r), _area(r), _contact(r), _provider(r),
        ])
    return Section(
        key="never_inspected", title="Newly registered, not yet inspected",
        intro="Adult social care locations newly registered with CQC that have no inspection or rating yet. Their "
              "first inspection is coming.",
        columns=NEVER_COLUMNS, rows=rows, csv_name="never_inspected.csv",
        html_headers=["Location", "Registered", "Service", "Area", "Contact", "Provider"], html_rows=html,
    )


def _sort_due(rows: list[dict]) -> list[dict]:
    """Longest waiting first: CQC works through the oldest ratings first."""
    rows = sorted(rows, key=lambda r: (r.get("location_name") or "", r.get("location_id") or ""))
    return sorted(rows, key=lambda r: r.get("due_since") or "9999")


def due_rows(rows: list[dict], week_ending: date) -> list[dict]:
    for row in rows:
        row["years_waiting"] = _years(row.get("due_since"), week_ending)
    return _sort_due(rows)


def due_for_inspection_section(rows: list[dict], week_ending: date) -> Section:
    rows = due_rows(rows, week_ending)
    html = []
    for r in rows:
        unrated = r.get("rating") is None
        html.append([
            _location(r),
            Cell(r.get("due_reason"), badge=f"{r['years_waiting']} years" if r.get("years_waiting") is not None
                 else None, tone="info" if unrated else RATING_TONE.get(r.get("rating"), "neutral")),
            _service(r), _area(r), _contact(r), _provider(r),
        ])
    return Section(
        key="due_for_inspection", title="Now due for inspection",
        intro="Services whose CQC rating turned 4 years old this week, or that have now waited a year since registering "
              "without an inspection. CQC is inspecting the oldest ratings first, so these are good candidates for a "
              "mock inspection. Every service currently due in your area is in due_for_inspection_all.csv, "
              "longest waiting first.",
        columns=DUE_COLUMNS, rows=rows, csv_name="due_for_inspection.csv",
        html_headers=["Location", "Why due", "Service", "Area", "Contact", "Provider"], html_rows=html,
    )


def _company_cell(r: dict) -> Cell:
    return Cell(r.get("company_name"), url=r.get("companies_house_url"),
                sub=f"{r.get('company_number')}, {r.get('legal_form')}", badge=r.get("flag"), tone="warn")


def new_companies_section(rows: list[dict]) -> Section:
    rows = _sort_by_date(rows, "incorporated", "company_name", flagged_last=True)
    cqc = {"yes": ("already CQC-registered", "good"), "possible": ("possible CQC match", "info")}
    html = []
    for r in rows:
        badge, tone = cqc.get(r.get("cqc_registered"), ("not CQC-registered yet", "neutral"))
        html.append([
            _company_cell(r),
            Cell(r.get("incorporated")),
            Cell(r.get("sic_description")),
            Cell(r.get("inferred_local_authority"), sub=r.get("address")),
            Cell(badge=badge, tone=tone, sub=r.get("cqc_provider_name")),
        ])
    return Section(
        key="new_companies", title="New care companies",
        intro="Companies incorporated with a care SIC code, with a registered office in this region. Most will need "
              "to register with CQC. Companies House lists no phone or email: write to the registered office or "
              "look up the company's website. Companies flagged “Check” may not be CQC-regulated.",
        columns=COMPANY_COLUMNS, rows=rows, csv_name="new_companies.csv",
        html_headers=["Company", "Incorporated", "Activity", "Registered office", "CQC"], html_rows=html,
    )


def location_unknown_section(rows: list[dict]) -> Section:
    rows = _sort_by_date(rows, "incorporated", "company_name", flagged_last=True)
    html = [
        [
            _company_cell(r),
            Cell(r.get("incorporated")),
            Cell(r.get("sic_description")),
            Cell(r.get("postcode"), sub=f"shared by {r.get('companies_at_postcode')} new care companies"),
        ]
        for r in rows
    ]
    return Section(
        key="location_unknown", title="New care companies, location unknown (national)",
        intro="New care companies registered at a formation agent or virtual office, so where they operate isn't "
              "known. Useful if you work nationally or remotely. Post sent to these addresses may not be forwarded.",
        columns=UNKNOWN_COLUMNS, rows=rows, csv_name="location_unknown.csv",
        html_headers=["Company", "Incorporated", "Activity", "Registered office"], html_rows=html,
    )


def company_located_section(rows: list[dict]) -> Section:
    rows = _sort_by_date(rows, "located_date", "company_name", flagged_last=True)
    html = []
    for r in rows:
        by_cqc = r.get("located_by") == "registered with CQC"
        html.append([
            _company_cell(r),
            Cell(badge=r.get("located_by"), tone="good" if by_cqc else "info", sub=r.get("located_date")),
            Cell(r.get("inferred_local_authority"),
                 sub=(r.get("cqc_provider_address") if by_cqc else r.get("address")) or r.get("postcode")),
            Cell(r.get("previous_postcode"), sub="formation-agent address"),
            Cell(r.get("incorporated"), sub=r.get("sic_description")),
        ])
    return Section(
        key="company_located", title="Now located in your region",
        intro="New care companies that were registered at a formation agent (location unknown) and have now "
              "revealed where they operate: they moved their registered office here, or registered with CQC here.",
        columns=LOCATED_COLUMNS, rows=rows, csv_name="company_located.csv",
        html_headers=["Company", "How located", "Now", "Previously", "Incorporated"], html_rows=html,
    )


@dataclass
class RegionLeads:
    region: str
    poor_ratings: list[dict]
    never_inspected: list[dict]
    new_companies: list[dict]
    location_unknown: list[dict]
    company_located: list[dict]
    never_inspected_all: list[dict]
    due_for_inspection: list[dict] = field(default_factory=list)
    due_for_inspection_all: list[dict] = field(default_factory=list)
    hidden_large_groups: int = 0  # location leads left out because the provider is a large group


@dataclass
class Selection:
    """How to pick one region's rows: its key, and the region's settings."""

    region: str
    include_location_unknown: bool = True
    include_large_groups: bool = True
    groups: Mapping[str, str] | None = None  # provider ID -> size label, from the current data
    hidden: int = 0  # counts rows left out as large groups

    @classmethod
    def for_region(cls, region: str, config: RegionConfig | None, vertical: CareVertical) -> Selection:
        return cls(
            region,
            include_location_unknown=config.location_unknown if config else True,
            include_large_groups=config.include_large_groups if config else False,
            groups=vertical.data.provider_groups,
        )

    def row(self, lead: LeadRow | Lead) -> dict | None:
        """The lead's row if it belongs in this region's digest, else None."""
        if lead.feed == "location_unknown":
            wanted = self.include_location_unknown and NATIONAL in lead.regions
        else:
            wanted = self.region in lead.regions or ALL_ENGLAND in lead.regions
        if not wanted:
            return None
        row = _row(lead, self.groups)
        if lead.feed in LOCATION_FEEDS and not self.include_large_groups and row.get("provider_group") == LARGE_GROUP:
            self.hidden += 1
            return None
        return row


def select_region(
    leads: Iterable[LeadRow | Lead], region: str | Selection, *, include_location_unknown: bool = True
) -> dict[str, list[dict]]:
    """This region's rows per feed. Location-unknown leads are national, so they go to every region."""
    selection = region if isinstance(region, Selection) else Selection(region, include_location_unknown)
    feeds = ("poor_ratings", "never_inspected", "due_for_inspection", "new_companies", "location_unknown",
             "company_located")
    out: dict[str, list[dict]] = {feed: [] for feed in feeds}
    for lead in leads:
        if lead.feed in out and (row := selection.row(lead)) is not None:
            out[lead.feed].append(row)
    return out


def _all_rows(all_leads: list[Lead], region: str | Selection) -> list[dict]:
    selection = region if isinstance(region, Selection) else Selection(region)
    return [row for lead in all_leads if (row := selection.row(lead)) is not None]


def never_inspected_all(all_leads: list[Lead], region: str | Selection, week_ending: date) -> list[dict]:
    rows = _all_rows(all_leads, region)
    for row in rows:
        row["days_registered"] = _days(row.get("registration_date"), week_ending)
    return _sort_by_date(rows, "registration_date", "location_name")


def due_for_inspection_all(all_leads: list[Lead], region: str | Selection, week_ending: date) -> list[dict]:
    """Every location due by the end of the week (the feed may have been evaluated later)."""
    due = [lead for lead in all_leads if lead.event_date is None or lead.event_date <= week_ending]
    return due_rows(_all_rows(due, region), week_ending)


def _region_leads(selection: Selection, leads: Iterable[LeadRow | Lead], vertical: CareVertical,
                  week_ending: date) -> RegionLeads:
    chosen = select_region(leads, selection)
    hidden = selection.hidden  # this week's leads only, not the full lists below
    never_all = never_inspected_all(NeverInspectedFeed(vertical.data).leads(), selection, week_ending)
    due_all = due_for_inspection_all(DueForInspectionFeed(vertical.data).leads(), selection, week_ending)
    return RegionLeads(selection.region, **chosen, never_inspected_all=never_all, due_for_inspection_all=due_all,
                       hidden_large_groups=hidden)


def build_digest(leads: RegionLeads, *, heading: str, subtitle: str, week_ending: date) -> Digest:
    sections = [
        poor_ratings_section(leads.poor_ratings),
        never_inspected_section(leads.never_inspected, week_ending),
        due_for_inspection_section(leads.due_for_inspection, week_ending),
        new_companies_section(leads.new_companies),
        company_located_section(leads.company_located),
        location_unknown_section(leads.location_unknown),
    ]
    count = {s.key: len(s.rows) for s in sections}
    tiles = [
        Tile("New poor ratings", count["poor_ratings"], "Requires improvement or Inadequate"),
        Tile("Newly registered", count["never_inspected"], "not yet inspected"),
        Tile("Now due for inspection", count["due_for_inspection"], "rating 4+ years old, or a year unrated"),
        Tile("New care companies", count["new_companies"], "in this region"),
        Tile("Now located", count["company_located"], "formation-agent companies found here"),
        Tile("Location unknown", count["location_unknown"], "new companies, national"),
        Tile("Never inspected", f"{len(leads.never_inspected_all):,}", "all in region, see never_inspected_all.csv"),
        Tile("Due for inspection", f"{len(leads.due_for_inspection_all):,}",
             "all in region, see due_for_inspection_all.csv"),
    ]
    files = [
        ("poor_ratings.csv", "new poor ratings"),
        ("never_inspected.csv", "newly registered, not yet inspected"),
        ("due_for_inspection.csv", "newly due for inspection this week"),
        ("new_companies.csv", "new care companies in the region"),
        ("company_located.csv", "formation-agent companies now located in the region"),
        ("location_unknown.csv", "new care companies at formation-agent addresses (national)"),
        ("never_inspected_all.csv", "every never-inspected location in the region, from the latest data"),
        ("due_for_inspection_all.csv", "every location in the region due for inspection, longest waiting first"),
    ]
    notes = list(NOTES)
    if leads.hidden_large_groups:
        notes.insert(0, f"{leads.hidden_large_groups:,} leads from large groups (a CQC brand, or 10+ locations) are "
                        "left out: they have in-house quality teams. To include them, set "
                        "include_large_groups: true for this region in signals.yaml.")
    return Digest(title=heading, subtitle=subtitle, tiles=tiles, sections=sections, files=files, notes=notes)


def write_region(folder: Path, leads: RegionLeads, *, heading: str, subtitle: str, week_ending: date) -> Path:
    """Write digest.html and the CSVs for one region. Returns the digest path."""
    digest = build_digest(leads, heading=heading, subtitle=subtitle, week_ending=week_ending)
    for section in digest.sections:
        write_csv(folder / f"{section.key}.csv", section.columns, section.rows)
    write_csv(folder / "never_inspected_all.csv", NEVER_ALL_COLUMNS, leads.never_inspected_all)
    write_csv(folder / "due_for_inspection_all.csv", DUE_COLUMNS, leads.due_for_inspection_all)
    return write_html(folder / "digest.html", digest)


def week_subtitle(week: Week) -> str:
    return f"Week {week.start:%a %d %b} to {week.ending:%a %d %b %Y}"


def _regions(regions: Mapping[str, RegionConfig]) -> dict[str, RegionConfig | None]:
    """Region key -> its config. With no regions configured, one all-England digest."""
    return dict(regions) or {ALL_ENGLAND: None}


def write_week(
    store: Store, vertical: CareVertical, week: Week, regions: Mapping[str, RegionConfig], outputs_dir: Path
) -> list[Path]:
    """Write every region's digest and CSVs for a week that has been run (from its recorded leads)."""
    leads = store.leads_for_week(vertical.name, week.ending)
    paths = []
    for key, config in _regions(regions).items():
        region_leads = _region_leads(Selection.for_region(key, config, vertical), leads, vertical, week.ending)
        folder = outputs_dir / vertical.name / str(week) / key
        paths.append(write_region(folder, region_leads, heading=f"Care leads: {region_label(key)}",
                                  subtitle=week_subtitle(week), week_ending=week.ending))
    return paths


def sample_leads(
    vertical: CareVertical, weeks: list[Week], region: str, region_config: RegionConfig | None
) -> RegionLeads:
    """One region's leads over several weeks, straight from the data. Records nothing.

    Every lead whose event falls in the period is included (no grace window, undated events left out).
    """
    start, end = weeks[0].start, weeks[-1].ending
    leads = [
        lead
        for feed in vertical.feeds()
        for lead in feed.leads()
        if lead.event_date is not None and start <= lead.event_date <= end
    ]
    return _region_leads(Selection.for_region(region, region_config, vertical), leads, vertical, end)


TEASER_EXAMPLES = 3
ORGANISATION_FORMS = {"limited company", "LLP", "other corporate body", "public body"}


def _organisations(rows: list[dict]) -> list[dict]:
    """Only rows about organisations: a sales email must never name a sole trader or partnership."""
    return [r for r in rows if r.get("legal_form") in ORGANISATION_FORMS]


def _where(row: dict) -> str:
    return f"{row.get('location_name')} ({row.get('local_authority') or row.get('postcode') or 'area unknown'})"


def email_teaser(leads: RegionLeads, weeks: list[Week]) -> str:
    """Numbers and real examples for a sales email about one region: proof that there's a tool behind it."""
    start, end = weeks[0].start, weeks[-1].ending
    name = region_label(leads.region)
    due = leads.due_for_inspection_all
    unrated = sum(1 for r in due if r.get("rating") is None)
    longest = sorted(_organisations(due), key=lambda r: (r.get("provider_group") != INDEPENDENT, r.get("due_since") or ""))
    poor = _sort_poor(_organisations(leads.poor_ratings))
    lines = [
        f"Numbers and examples for emails about {name} (from the CQC and Companies House registers, "
        f"{start:%d %b} to {end:%d %b %Y}).",
        "Every example below is an organisation, never a sole trader. Check the numbers are current before sending.",
        "",
        f"Due for inspection now: {len(due):,} services",
        f"  - {len(due) - unrated:,} last rated 4 or more years ago",
        f"  - {unrated:,} never inspected, a year or more after registering",
        f"Last {len(weeks)} weeks: {len(leads.poor_ratings):,} new poor ratings, {len(leads.never_inspected):,} newly "
        f"registered services, {len(leads.new_companies):,} new care companies",
        "",
        "Longest waiting (independents first):",
        *[f"  - {_where(r)}: {r.get('due_reason')}, {r.get('years_waiting')} years ago"
          for r in longest[:TEASER_EXAMPLES]],
    ]
    if poor:
        lines += ["", "Recent poor ratings:"]
        lines += [
            f"  - {_where(r)}: {r.get('rating')} on {r.get('rating_date') or 'a recent date'}"
            + (f", was {r['previous_rating']}" if r.get("previous_rating") else "")
            for r in poor[:TEASER_EXAMPLES]
        ]
    if longest:
        first = longest[0]
        lines += [
            "",
            "A ready-made sentence:",
            f"  In {name} right now, {len(due):,} care services have a CQC rating that is 4 or more years old, or have "
            f"waited over a year for their first inspection. For example, {first.get('location_name')} in "
            f"{first.get('local_authority') or 'your area'}: {first.get('due_reason')}.",
        ]
    return "\n".join(lines) + "\n"


def write_sample(
    vertical: CareVertical, weeks: list[Week], region: str, region_config: RegionConfig | None, outputs_dir: Path
) -> Path:
    """A preview digest for one region over several weeks (see sample_leads), plus email-teaser.txt."""
    start, end = weeks[0].start, weeks[-1].ending
    folder = outputs_dir / "samples" / vertical.name / f"{region}_{start}_to_{end}"
    subtitle = f"Sample: {len(weeks)} week{'s' if len(weeks) > 1 else ''}, {start:%a %d %b} to {end:%a %d %b %Y}"
    leads = sample_leads(vertical, weeks, region, region_config)
    path = write_region(folder, leads, heading=f"Care leads: {region_label(region)}", subtitle=subtitle,
                        week_ending=end)
    (folder / "email-teaser.txt").write_text(email_teaser(leads, weeks), encoding="utf-8")
    return path
