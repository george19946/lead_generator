"""The care digest: per region, one HTML page plus a CSV per lead list.

outputs/care/<week_ending>/<region>/
    digest.html              this week's leads, all lists
    poor_ratings.csv         new Requires improvement / Inadequate ratings
    never_inspected.csv      newly registered locations with no inspection yet
    new_companies.csv        new care companies placed in the region
    location_unknown.csv     new care companies at formation-agent addresses (national)
    never_inspected_all.csv  every never-inspected location in the region, as the database stands now

Everything except never_inspected_all.csv comes from the recorded lead events, so re-running a week
writes the same files.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from signals.core.feed import Lead, Week
from signals.core.legal_form import EMAIL_OK, PHONE_CHECK_TPS, POST_ONLY
from signals.db.store import LeadRow, Store
from signals.output.model import Cell, Column, Digest, Section, Tile
from signals.output.writers import write_csv, write_html
from signals.settings import RegionConfig
from signals.verticals.care.feeds import ALL_ENGLAND, NATIONAL, CareVertical, NeverInspectedFeed
from signals.verticals.care.flags import name_flag, sic_labels

CHANNEL_TONE = {EMAIL_OK: "good", PHONE_CHECK_TPS: "info", POST_ONLY: "neutral"}
RATING_TONE = {"Inadequate": "bad", "Requires improvement": "warn"}

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

NOTES = [
    "Each lead is listed once, in the week it is first found. Events that registers publish late are still picked up "
    "for up to 14 days.",
    "Contact rules (PECR): “email OK” means a corporate subscriber (company, LLP, public body), so marketing "
    "email is allowed with an opt-out. “phone”: screen the number against TPS/CTPS before calling. "
    "“post only”: sole traders and partnerships with no phone number listed. An unknown legal form is "
    "treated with the stricter rule.",
    "Sole-trader provider names are personal data: use them only to offer relevant services, and stop if asked.",
    "Contains CQC data © Care Quality Commission, licensed under the Open Government Licence v3.0. "
    "Contains Companies House data.",
]


def region_label(key: str) -> str:
    return key.replace("-", " ").replace("_", " ").title()


def _row(lead: LeadRow | Lead) -> dict[str, Any]:
    row = {**lead.data, "regions": ", ".join(lead.regions)}
    if "company_name" in row:  # derived at render time, so older events get the current labels too
        row["flag"] = name_flag(row.get("company_name"))
        row["sic_description"] = sic_labels(row.get("sic_codes"))
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
    return Cell(row.get("provider_name") or "Unknown", url=row.get("provider_url"), sub=sub)


def _location(row: dict) -> Cell:
    return Cell(row.get("location_name"), url=row.get("cqc_url"), sub=row.get("address"))


def _area(row: dict) -> Cell:
    return Cell(row.get("local_authority"), sub=row.get("postcode"))


def _days(since: str | None, until: date) -> int | None:
    return (until - date.fromisoformat(since)).days if since else None


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


@dataclass
class RegionLeads:
    region: str
    poor_ratings: list[dict]
    never_inspected: list[dict]
    new_companies: list[dict]
    location_unknown: list[dict]
    never_inspected_all: list[dict]


def select_region(
    leads: Iterable[LeadRow | Lead], region: str, *, include_location_unknown: bool = True
) -> dict[str, list[dict]]:
    """This region's rows per feed. Location-unknown leads are national, so they go to every region."""
    out: dict[str, list[dict]] = {"poor_ratings": [], "never_inspected": [], "new_companies": [], "location_unknown": []}
    for lead in leads:
        if lead.feed not in out:
            continue
        if lead.feed == "location_unknown":
            wanted = include_location_unknown and NATIONAL in lead.regions
        else:
            wanted = region in lead.regions or ALL_ENGLAND in lead.regions
        if wanted:
            out[lead.feed].append(_row(lead))
    return out


def never_inspected_all(all_leads: list[Lead], region: str, week_ending: date) -> list[dict]:
    rows = []
    for lead in all_leads:
        if region in lead.regions or ALL_ENGLAND in lead.regions:
            row = _row(lead)
            row["days_registered"] = _days(row.get("registration_date"), week_ending)
            rows.append(row)
    return _sort_by_date(rows, "registration_date", "location_name")


def build_digest(leads: RegionLeads, *, heading: str, subtitle: str, week_ending: date) -> Digest:
    sections = [
        poor_ratings_section(leads.poor_ratings),
        never_inspected_section(leads.never_inspected, week_ending),
        new_companies_section(leads.new_companies),
        location_unknown_section(leads.location_unknown),
    ]
    count = {s.key: len(s.rows) for s in sections}
    tiles = [
        Tile("New poor ratings", count["poor_ratings"], "Requires improvement or Inadequate"),
        Tile("Newly registered", count["never_inspected"], "not yet inspected"),
        Tile("New care companies", count["new_companies"], "in this region"),
        Tile("Location unknown", count["location_unknown"], "new companies, national"),
        Tile("Never inspected", f"{len(leads.never_inspected_all):,}", "all in region, see never_inspected_all.csv"),
    ]
    files = [
        ("poor_ratings.csv", "new poor ratings"),
        ("never_inspected.csv", "newly registered, not yet inspected"),
        ("new_companies.csv", "new care companies in the region"),
        ("location_unknown.csv", "new care companies at formation-agent addresses (national)"),
        ("never_inspected_all.csv", "every never-inspected location in the region, from the latest data"),
    ]
    return Digest(title=heading, subtitle=subtitle, tiles=tiles, sections=sections, files=files, notes=NOTES)


def write_region(folder: Path, leads: RegionLeads, *, heading: str, subtitle: str, week_ending: date) -> Path:
    """Write digest.html and the CSVs for one region. Returns the digest path."""
    digest = build_digest(leads, heading=heading, subtitle=subtitle, week_ending=week_ending)
    for section in digest.sections:
        write_csv(folder / f"{section.key}.csv", section.columns, section.rows)
    write_csv(folder / "never_inspected_all.csv", NEVER_ALL_COLUMNS, leads.never_inspected_all)
    return write_html(folder / "digest.html", digest)


def week_subtitle(week: Week) -> str:
    return f"Week {week.start:%a %d %b} to {week.ending:%a %d %b %Y}"


def _regions(regions: Mapping[str, RegionConfig]) -> dict[str, bool]:
    """Region key -> include location-unknown leads. With no regions configured, one all-England digest."""
    return {key: cfg.location_unknown for key, cfg in regions.items()} or {ALL_ENGLAND: True}


def write_week(
    store: Store, vertical: CareVertical, week: Week, regions: Mapping[str, RegionConfig], outputs_dir: Path
) -> list[Path]:
    """Write every region's digest and CSVs for a week that has been run (from its recorded leads)."""
    leads = store.leads_for_week(vertical.name, week.ending)
    never_all = NeverInspectedFeed(vertical.data).leads()
    paths = []
    for key, with_unknown in _regions(regions).items():
        chosen = select_region(leads, key, include_location_unknown=with_unknown)
        region_leads = RegionLeads(key, **chosen, never_inspected_all=never_inspected_all(never_all, key, week.ending))
        folder = outputs_dir / vertical.name / str(week) / key
        paths.append(write_region(folder, region_leads, heading=f"Care leads: {region_label(key)}",
                                  subtitle=week_subtitle(week), week_ending=week.ending))
    return paths


def write_sample(
    vertical: CareVertical, weeks: list[Week], region: str, region_config: RegionConfig | None, outputs_dir: Path
) -> Path:
    """A preview digest for one region over several weeks, straight from the data. Records nothing.

    Every lead whose event falls in the period is included (no grace window, undated events left out).
    """
    start, end = weeks[0].start, weeks[-1].ending
    leads = [
        lead
        for feed in vertical.feeds()
        for lead in feed.leads()
        if lead.event_date is not None and start <= lead.event_date <= end
    ]
    with_unknown = region_config.location_unknown if region_config else True
    chosen = select_region(leads, region, include_location_unknown=with_unknown)
    never_all = never_inspected_all(NeverInspectedFeed(vertical.data).leads(), region, end)
    folder = outputs_dir / "samples" / vertical.name / f"{region}_{start}_to_{end}"
    subtitle = f"Sample: {len(weeks)} week{'s' if len(weeks) > 1 else ''}, {start:%a %d %b} to {end:%a %d %b %Y}"
    return write_region(folder, RegionLeads(region, **chosen, never_inspected_all=never_all),
                        heading=f"Care leads: {region_label(region)}", subtitle=subtitle, week_ending=end)
