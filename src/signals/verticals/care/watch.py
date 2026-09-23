"""Watch new care companies whose location is unknown (registered at a formation agent).

Such companies often reveal where they operate within months: they move their registered office to
their own address, or they register with CQC (whose records carry the company number). `recheck_companies`
re-reads each watched company's Companies House profile every RECHECK_DAYS and stores any new registered
office; the `company_located` feed then turns a move (or a CQC link) into a regional lead.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from typing import Any

from signals.core.source import RawRecord
from signals.db.store import Store, StoredEntity
from signals.http import ApiError
from signals.sources.companies_house.source import SOURCE as CH
from signals.sources.companies_house.source import CompaniesHouseSource

# A registered office shared by this many stored care companies is treated as a formation agent or virtual
# office (live data: 13% of new care companies use one). Its postcode says nothing about where the business
# operates, so no customer region is inferred from it.
SHARED_ADDRESS_MIN = 5
WATCH_DAYS = 365  # watch a company for this long after incorporation
RECHECK_DAYS = 28  # re-read each watched company's profile this often
MAX_CHECKS_PER_RUN = 300  # about 3 minutes at the Companies House rate limit


def postcode_key(postcode: str | None) -> str:
    return "".join((postcode or "").upper().split())


def office_postcode(payload: dict[str, Any]) -> str | None:
    return (payload.get("registered_office_address") or {}).get("postal_code")


def postcode_counts(payloads: Iterable[dict[str, Any]]) -> Counter[str]:
    """How many stored companies have their registered office at each postcode."""
    return Counter(postcode_key(office_postcode(p)) for p in payloads if office_postcode(p))


def is_shared(postcode: str | None, counts: Counter[str]) -> bool:
    return bool(postcode) and counts.get(postcode_key(postcode), 0) >= SHARED_ADDRESS_MIN


def watch_candidates(store: Store, now: datetime, limit: int = MAX_CHECKS_PER_RUN) -> list[StoredEntity]:
    """Companies at a shared registered office, incorporated within WATCH_DAYS, not checked for RECHECK_DAYS.

    Oldest-checked first, so a capped run works through the backlog over successive weeks.
    """
    companies = list(store.iter_entities(CH, "company"))
    counts = postcode_counts(e.payload for e in companies)
    since = now.date() - timedelta(days=WATCH_DAYS)
    stale = now - timedelta(days=RECHECK_DAYS)
    due = []
    for entity in companies:
        created = entity.payload.get("date_of_creation")
        if (
            is_shared(office_postcode(entity.payload), counts)
            and created and date.fromisoformat(created) >= since
            and entity.last_fetched_at <= stale
            and entity.payload.get("company_status", "active") == "active"
        ):
            due.append(entity)
    due.sort(key=lambda e: (e.last_fetched_at, e.entity_id))
    return due[:limit]


def merge_profile(payload: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Apply a profile's changes to the stored (search-result shaped) payload.

    Profiles format addresses differently from search results, so the address is replaced only when the
    postcode actually differs; otherwise re-checking would record a spurious change.
    """
    merged = dict(payload)
    new_office = profile.get("registered_office_address") or {}
    if new_office.get("postal_code") and postcode_key(new_office["postal_code"]) != postcode_key(office_postcode(payload)):
        line_1 = " ".join(p for p in (new_office.get("premises"), new_office.get("address_line_1")) if p)
        merged["registered_office_address"] = {
            k: v
            for k, v in {
                "address_line_1": line_1 or None,
                "address_line_2": new_office.get("address_line_2"),
                "locality": new_office.get("locality"),
                "region": new_office.get("region"),
                "postal_code": new_office.get("postal_code"),
                "country": new_office.get("country"),
            }.items()
            if v
        }
    for key in ("company_status", "company_name"):
        if profile.get(key) and profile[key] != payload.get(key):
            merged[key] = profile[key]
    return merged


def recheck_companies(
    ch: CompaniesHouseSource,
    store: Store,
    now: datetime,
    *,
    bump: Callable[[str], None],
    fail: Callable[[str], None],
    limit: int = MAX_CHECKS_PER_RUN,
) -> None:
    for entity in watch_candidates(store, now, limit):
        try:
            profile = ch.profile(entity.entity_id)
        except ApiError as exc:
            fail(f"company {entity.entity_id}: {exc}")
            continue
        bump("company_rechecked")
        if profile is None:
            continue
        before = postcode_key(office_postcode(entity.payload))
        merged = merge_profile(entity.payload, profile)
        store.save_record(RawRecord(CH, "company", entity.entity_id, ch.clock(), merged))
        if postcode_key(office_postcode(merged)) != before:
            bump("company_moved")
