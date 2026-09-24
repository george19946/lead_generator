"""Prospects: CQC compliance consultancies to offer the service to, found free on Companies House.

Only incorporated bodies (limited companies, LLPs, PLCs) are listed: under PECR they are corporate subscribers, so a
relevant business email with an opt-out is allowed. Sole-trader consultants aren't on Companies House at all.
Companies House has no email addresses; the CSV has empty `website`, `email` and `first_name` columns to fill in from
each company's own website, and an `approved` column: only prospects marked "yes" should be contacted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from signals.core.regions import PostcodeLookup
from signals.output.model import Column
from signals.output.writers import write_csv
from signals.sources.companies_house.client import MAX_PAGE_SIZE, CompaniesHouseClient
from signals.sources.companies_house.models import ChCompany
from signals.verticals.care.collect import CareScope
from signals.verticals.care.flags import sic_labels

NAME_PHRASES = (
    "cqc", "care compliance", "care consultancy", "care consultants", "care consulting",
    "social care consultancy", "social care consultants", "healthcare compliance", "compliance consultancy",
    "compliance consultants", "care solutions consultancy",
)
COMPANY_TYPES = ("ltd", "llp", "plc", "private-limited-guarant-nsc", "private-limited-guarant-nsc-limited-exemption")
# A prospect's name must be about care, and not about something else that happens to match a phrase.
CARE_WORDS = re.compile(r"\b(cqc|care|healthcare|health|social|nursing)\b", re.IGNORECASE)
CONSULTANCY_WORDS = re.compile(r"\b(cqc|consult\w*|complian\w*|advis\w*|advice)\b", re.IGNORECASE)
NOT_CONSULTANCY = re.compile(
    r"\b(visa|dental|dentist|pharmacy|primary care|skin|hair|beauty|pet|pets|vet|lawn|garden|tree|car|cars|vehicle|"
    r"transport|holdings?|property|properties|cleaning|legal|housing)\b",
    re.IGNORECASE,
)
MAX_PAGES = 2  # per phrase; Companies House errors beyond start_index ~10,000

COLUMNS = [
    Column("company_name", "company_name"),
    Column("approved", "approved"),
    Column("email", "email"),
    Column("first_name", "first_name"),
    Column("website", "website"),
    Column("notes", "notes"),
    Column("inferred_local_authority", "local_authority"),
    Column("inferred_region", "cqc_region"),
    Column("regions", "your_regions"),
    Column("postcode", "postcode"),
    Column("registered_office", "registered_office"),
    Column("incorporated", "incorporated"),
    Column("activity", "activity"),
    Column("company_type", "company_type"),
    Column("company_number", "company_number"),
    Column("companies_house_url", "companies_house_url"),
]


@dataclass
class ProspectResult:
    rows: list[dict]
    skipped: int  # matched a phrase but look like something else
    requests: int


def search(client: CompaniesHouseClient, phrases: Iterable[str] = NAME_PHRASES) -> tuple[list[ChCompany], int]:
    """Every active incorporated company whose name contains one of the phrases (deduplicated)."""
    found: dict[str, ChCompany] = {}
    for phrase in phrases:
        for page in range(MAX_PAGES):
            data = client.search_by_name(phrase, company_types=COMPANY_TYPES, start_index=page * MAX_PAGE_SIZE)
            items = data.get("items") or []
            for item in items:
                try:
                    company = ChCompany.model_validate(item)
                except ValidationError:
                    continue
                found.setdefault(company.company_number, company)
            if len(items) < MAX_PAGE_SIZE:
                break
    return list(found.values()), client.request_count


def build_rows(companies: Iterable[ChCompany], postcodes: PostcodeLookup, scope: CareScope,
               region: str | None = None) -> tuple[list[dict], int]:
    """Prospect rows, newest first (new consultancies need clients most), optionally for one customer region."""
    rows, skipped = [], 0
    for company in companies:
        name = company.company_name
        if not (CARE_WORDS.search(name) and CONSULTANCY_WORDS.search(name)) or NOT_CONSULTANCY.search(name):
            skipped += 1
            continue
        office = company.registered_office_address
        postcode = office.postal_code if office else None
        inferred_region, local_authority = postcodes.lookup(postcode)
        regions = [] if scope.all_england else scope.matcher.match(
            region=inferred_region, local_authority=local_authority, postcode=postcode)
        if region and region not in regions:
            continue
        rows.append({
            "company_name": company.company_name,
            "approved": "",
            "email": "",
            "first_name": "",
            "website": "",
            "notes": "",
            "inferred_local_authority": local_authority,
            "inferred_region": inferred_region,
            "regions": ", ".join(regions),
            "postcode": postcode,
            "registered_office": office.one_line() if office else None,
            "incorporated": company.date_of_creation.isoformat() if company.date_of_creation else None,
            "activity": sic_labels(company.sic_codes),
            "company_type": company.company_type,
            "company_number": company.company_number,
            "companies_house_url": company.url,
        })
    rows.sort(key=lambda r: (r["incorporated"] or "", r["company_number"]), reverse=True)
    rows.sort(key=lambda r: not r["regions"])  # in your regions first
    return rows, skipped


def write_prospects(path: Path, rows: list[dict]) -> Path:
    return write_csv(path, COLUMNS, rows)
