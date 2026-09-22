"""Live smoke test: fetch a handful of records from each API, check field names, save fixtures."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from signals.sources.companies_house.client import CompaniesHouseClient
from signals.sources.companies_house.models import ChCompany
from signals.sources.cqc.client import CqcClient
from signals.sources.cqc.models import CqcLocation, CqcProvider
from signals.sources.cqc.sanitise import strip_personal_names
from signals.verticals.care import CARE_SIC_CODES

# Fields the feeds rely on; the smoke test reports any that live responses lack.
EXPECTED_FIELDS = {
    "location": [
        "locationId", "providerId", "name", "registrationStatus", "registrationDate",
        "postalCode", "region", "localAuthority", "mainPhoneNumber", "inspectionDirectorate",
        "gacServiceTypes", "regulatedActivities", "currentRatings",
    ],
    "provider": [
        "providerId", "name", "registrationStatus", "registrationDate", "postalCode",
        "ownershipType", "companiesHouseNumber", "website", "mainPhoneNumber", "locationIds",
    ],
    "company": [
        "company_number", "company_name", "company_status", "company_type", "date_of_creation",
        "registered_office_address", "sic_codes",
    ],
}


@dataclass
class SmokeReport:
    lines: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def add(self, line: str) -> None:
        self.lines.append(line)

    def problem(self, line: str) -> None:
        self.problems.append(line)


def _timed(fn: Callable[[], Any]) -> tuple[Any, float]:
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


def _check_fields(kind: str, record: dict, report: SmokeReport) -> None:
    missing = [f for f in EXPECTED_FIELDS[kind] if f not in record]
    if missing:
        report.problem(f"{kind} {record.get('locationId') or record.get('providerId') or record.get('company_number')}: missing {missing}")


def _parse(model: type[BaseModel], record: dict, report: SmokeReport) -> None:
    try:
        model.model_validate(record)
    except Exception as exc:  # report, don't abort: the point is to learn the real shape
        report.problem(f"{model.__name__} failed to parse: {exc}")


def _redact_individual(provider: dict) -> dict:
    """Sole-trader provider names are personal data; don't commit them as fixtures."""
    if str(provider.get("ownershipType", "")).lower() == "individual":
        provider = {**provider, "name": "REDACTED INDIVIDUAL PROVIDER"}
    return provider


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def run_smoke(
    cqc: CqcClient,
    ch: CompaniesHouseClient,
    *,
    n: int = 5,
    fixtures_dir: Path | None = None,
    now: datetime | None = None,
) -> SmokeReport:
    report = SmokeReport()
    now = now or datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # --- CQC: changes feed ---------------------------------------------------------
    loc_changes, secs = _timed(lambda: cqc.changes_page("location", week_ago, now))
    report.add(
        f"CQC changes/location (7 days): keys={sorted(loc_changes)} total={loc_changes.get('total')} "
        f"totalPages={loc_changes.get('totalPages')} ({secs:.2f}s)"
    )
    prov_changes = cqc.changes_page("provider", week_ago, now)
    report.add(f"CQC changes/provider (7 days): total={prov_changes.get('total')}")

    location_ids = [c for c in (loc_changes.get("changes") or []) if isinstance(c, str)][:n]
    if not location_ids:
        report.problem(f"No location IDs in changes response; first item: {(loc_changes.get('changes') or [None])[0]!r}")

    # The changes feed spans every sector, so also sample adult social care via the list endpoint
    # (this also checks the filter value).
    asc_page = cqc.locations_page(page=1, per_page=n, inspectionDirectorate="Adult social care")
    report.add(
        f"CQC /locations?inspectionDirectorate=Adult social care: keys={sorted(asc_page)} total={asc_page.get('total')}"
    )
    asc_ids = [s["locationId"] for s in asc_page.get("locations") or [] if s.get("locationId")][:n]

    locations: list[dict] = []
    durations: list[float] = []
    for location_id in dict.fromkeys(location_ids + asc_ids):
        loc, secs = _timed(lambda: cqc.get_location(location_id))
        durations.append(secs)
        if loc:
            locations.append(strip_personal_names(loc))
    if durations:
        report.add(f"CQC fetched {len(locations)} locations, mean {sum(durations) / len(durations):.2f}s/request")

    provider_ids = list(dict.fromkeys(loc["providerId"] for loc in locations if loc.get("providerId")))[:n]
    providers = [strip_personal_names(p) for pid in provider_ids if (p := cqc.get_provider(pid))]
    report.add(f"CQC fetched {len(providers)} providers")

    for loc in locations:
        _check_fields("location", loc, report)
        _parse(CqcLocation, loc, report)
        rating = (loc.get("currentRatings") or {}).get("overall")
        report.add(
            f"  location {loc.get('locationId')} | {loc.get('name')} | {loc.get('inspectionDirectorate')} | "
            f"{loc.get('region')} | reg {loc.get('registrationDate')} | rating {rating and rating.get('rating')}"
        )
        extra = sorted(set(loc) - set(EXPECTED_FIELDS["location"]))
        report.add(f"    other keys: {extra}")
    for prov in providers:
        _check_fields("provider", prov, report)
        _parse(CqcProvider, prov, report)
        report.add(
            f"  provider {prov.get('providerId')} | ownershipType={prov.get('ownershipType')} | "
            f"CH={prov.get('companiesHouseNumber')} | website={prov.get('website')}"
        )

    # --- Companies House -----------------------------------------------------------
    today = now.date()
    search, secs = _timed(
        lambda: ch.advanced_search(
            sic_codes=CARE_SIC_CODES,
            incorporated_from=today - timedelta(days=7),
            incorporated_to=today,
            size=n,
        )
    )
    items = search.get("items") or []
    report.add(f"Companies House advanced search (7 days): keys={sorted(search)} hits={search.get('hits')} ({secs:.2f}s)")
    for item in items:
        _check_fields("company", item, report)
        _parse(ChCompany, item, report)
        report.add(
            f"  company {item.get('company_number')} | {item.get('company_name')} | {item.get('company_type')} | "
            f"{item.get('date_of_creation')} | {(item.get('registered_office_address') or {}).get('postal_code')} | {item.get('sic_codes')}"
        )

    report.add(f"Requests made: CQC={cqc.request_count}, Companies House={ch.request_count}")

    if fixtures_dir:
        _save(fixtures_dir / "cqc" / "changes_location.json", {**loc_changes, "changes": location_ids})
        _save(fixtures_dir / "cqc" / "locations_list.json", asc_page)
        for loc in locations:
            _save(fixtures_dir / "cqc" / f"location_{loc['locationId']}.json", loc)
        for prov in providers:
            _save(fixtures_dir / "cqc" / f"provider_{prov['providerId']}.json", _redact_individual(prov))
        _save(fixtures_dir / "companies_house" / "advanced_search.json", search)
        report.add(f"Saved sanitised fixtures under {fixtures_dir}/ (captured {date.today().isoformat()})")

    return report
