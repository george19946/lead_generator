"""Collect care data into the store: a one-off backfill (baseline) and the weekly incremental sync.

Scope: CQC adult social care locations in the configured customer regions, their providers, and
every new company incorporated with a care SIC code (filtered by region later, at output time).

- Backfill lists the in-scope locations (cheap list pages), then fetches every location's detail and
  every registered location's provider. It resumes: anything fetched within `fresh_hours` is skipped.
- Sync fetches CQC changes since the stored watermark and keeps the in-scope or already tracked ones,
  re-reads recent Companies House incorporations, and re-checks watched formation-agent companies (watch.py).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from signals.core.clock import from_iso, to_iso
from signals.core.regions import RegionMatcher
from signals.core.source import FetchWindow
from signals.db.store import SaveResult, Store
from signals.http import ApiError
from signals.settings import RegionConfig
from signals.sources.companies_house.source import SOURCE as CH
from signals.sources.companies_house.source import CompaniesHouseSource
from signals.sources.cqc.source import SOURCE as CQC
from signals.sources.cqc.source import CqcSource
from signals.verticals.care.watch import recheck_companies

log = logging.getLogger(__name__)

ASC_DIRECTORATE = "Adult social care"
CQC_CHANGES_STREAM = "changes"
CH_INCORPORATIONS_STREAM = "incorporations"

# Planning figures from the live measurements in PROGRESS.md (2026-09-22).
SECONDS_PER_CQC_CALL = 0.3  # sequential; measured 0.2-0.31s per detail call, below the 10 req/s limit
SECONDS_PER_CH_CALL = 0.9
PROVIDERS_PER_LOCATION = 0.4  # distinct providers per in-scope location, estimated
CH_OVERLAP_DAYS = 7  # re-read recent incorporations: the search index can lag a few days

Progress = Callable[[str], None]


def _quiet(_: str) -> None:
    pass


class CareScope:
    """Which CQC locations the care vertical tracks."""

    def __init__(self, regions: Mapping[str, RegionConfig], *, all_england: bool = False):
        self.regions = dict(regions)
        self.all_england = all_england or not self.regions
        self.matcher = RegionMatcher(self.regions)

    def list_queries(self) -> list[tuple[dict[str, object], bool]]:
        """CQC location-list queries that together cover the scope, as (filters, filter_by_postcode).

        The list endpoint can filter by region and local authority but not by postcode. Postcode regions
        therefore use the full adult social care list, filtered locally on each entry's `postalCode`.
        """
        base: dict[str, object] = {"inspectionDirectorate": ASC_DIRECTORATE}
        if self.all_england:
            return [(base, False)]
        queries: list[tuple[dict[str, object], bool]] = []
        for cfg in self.regions.values():
            if cfg.cqc_region:
                queries.append(({**base, "region": cfg.cqc_region}, False))
            if cfg.local_authorities:
                queries.append(({**base, "localAuthority": sorted(cfg.local_authorities)}, False))
        if any(cfg.postcode_areas for cfg in self.regions.values()):
            queries.append((base, True))
        unique: list[tuple[dict[str, object], bool]] = []
        for q in queries:
            if q not in unique:
                unique.append(q)
        return unique

    def location_in_scope(self, payload: dict) -> bool:
        if payload.get("inspectionDirectorate") != ASC_DIRECTORATE:
            return False
        if self.all_england:
            return True
        return bool(
            self.matcher.match(
                region=payload.get("region"),
                local_authority=payload.get("localAuthority"),
                postcode=payload.get("postalCode"),
            )
        )


@dataclass
class BackfillPlan:
    days: int
    location_ids: list[str]  # every in-scope location, from the list endpoint
    fresh_location_ids: set[str]  # fetched recently: skipped (resume)
    list_calls: int
    started_at: datetime
    only_new: bool = False

    @property
    def locations_to_fetch(self) -> list[str]:
        return [i for i in self.location_ids if i not in self.fresh_location_ids]

    @property
    def estimated_provider_calls(self) -> int:
        return math.ceil(len(self.locations_to_fetch) * PROVIDERS_PER_LOCATION)

    @property
    def estimated_ch_calls(self) -> int:
        return math.ceil(self.days / 7)

    @property
    def estimated_cqc_calls(self) -> int:
        return len(self.locations_to_fetch) + self.estimated_provider_calls

    @property
    def estimated_seconds(self) -> float:
        return self.estimated_cqc_calls * SECONDS_PER_CQC_CALL + self.estimated_ch_calls * SECONDS_PER_CH_CALL

    def describe(self) -> list[str]:
        minutes = self.estimated_seconds / 60
        return [
            f"In-scope CQC locations: {len(self.location_ids):,} "
            f"({len(self.fresh_location_ids):,} {'already stored' if self.only_new else 'fetched in the last day'}, "
            "skipped)",
            f"CQC calls: {len(self.locations_to_fetch):,} location details + about "
            f"{self.estimated_provider_calls:,} provider details (list pages already made: {self.list_calls})",
            f"Companies House calls: about {self.estimated_ch_calls} ({self.days} days of care-SIC incorporations)",
            f"Estimated duration: about {minutes:.0f} min (sequential, {SECONDS_PER_CQC_CALL}s per CQC call)",
        ]


def plan_backfill(
    cqc: CqcSource, store: Store, scope: CareScope, *, days: int, now: datetime, fresh_hours: float = 24,
    only_new: bool = False,
) -> BackfillPlan:
    """List the in-scope locations and work out what still needs fetching. Makes only list calls.

    With `only_new`, every location already stored is skipped (sync keeps those up to date): use it after
    adding or widening a region.
    """
    before = cqc.client.request_count
    ids: dict[str, None] = {}  # ordered set
    for query, by_postcode in scope.list_queries():
        for summary in cqc.location_summaries(**query):
            location_id = summary.get("locationId")
            if location_id and (not by_postcode or scope.matcher.match(postcode=summary.get("postalCode"))):
                ids[str(location_id)] = None
    if only_new:
        fresh = {e.entity_id for e in store.iter_entities(CQC, "location", include_gone=True)}
    else:
        fresh = store.fetched_since(CQC, "location", now - timedelta(hours=fresh_hours))
    return BackfillPlan(
        days=days,
        location_ids=list(ids),
        fresh_location_ids=fresh & set(ids),
        list_calls=cqc.client.request_count - before,
        started_at=now,
        only_new=only_new,
    )


@dataclass
class CollectStats:
    counts: dict[str, int] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

    def bump(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    def saved(self, kind: str, result: SaveResult) -> None:
        self.bump(f"{kind}_{result.value}")

    def as_dict(self) -> dict[str, object]:
        return {**self.counts, "failures": len(self.failures)}


def _fetch_locations(
    cqc: CqcSource, store: Store, ids: Iterable[str], stats: CollectStats, progress: Progress,
    *, keep: Callable[[str, dict], bool], total: int | None = None,
) -> set[str]:
    """Fetch and store location details. Returns the provider IDs of the registered ones kept."""
    providers: set[str] = set()
    for n, location_id in enumerate(ids, 1):
        if n % 250 == 0:
            progress(f"  locations: {n:,}{f'/{total:,}' if total else ''}")
        try:
            record = cqc.location(location_id)
        except ApiError as exc:
            stats.failures.append(f"location {location_id}: {exc}")
            continue
        if record is None:
            gone = store.mark_gone(CQC, "location", location_id, cqc.clock())
            stats.bump("location_gone" if gone else "location_not_found")
            continue
        if not keep(location_id, record.payload):
            stats.bump("location_out_of_scope")
            continue
        stats.saved("location", store.save_record(record))
        if record.payload.get("registrationStatus") == "Registered" and record.payload.get("providerId"):
            providers.add(str(record.payload["providerId"]))
    return providers


def _fetch_providers(cqc: CqcSource, store: Store, ids: Iterable[str], stats: CollectStats, progress: Progress) -> None:
    ids = sorted(ids)
    for n, provider_id in enumerate(ids, 1):
        if n % 250 == 0:
            progress(f"  providers: {n:,}/{len(ids):,}")
        try:
            record = cqc.provider(provider_id)
        except ApiError as exc:
            stats.failures.append(f"provider {provider_id}: {exc}")
            continue
        if record is None:
            gone = store.mark_gone(CQC, "provider", provider_id, cqc.clock())
            stats.bump("provider_gone" if gone else "provider_not_found")
            continue
        stats.saved("provider", store.save_record(record))


def _fetch_companies(ch: CompaniesHouseSource, store: Store, start: date, end: date, stats: CollectStats) -> None:
    try:
        for record in ch.incorporations(start, end):
            stats.saved("company", store.save_record(record))
    except ApiError as exc:
        stats.failures.append(f"companies house {start}..{end}: {exc}")


def _registered_provider_ids(store: Store, location_ids: Iterable[str]) -> set[str]:
    out = set()
    for location_id in location_ids:
        entity = store.get(CQC, "location", location_id)
        if entity and entity.payload.get("registrationStatus") == "Registered" and entity.payload.get("providerId"):
            out.add(str(entity.payload["providerId"]))
    return out


def run_backfill(
    plan: BackfillPlan,
    cqc: CqcSource,
    ch: CompaniesHouseSource,
    store: Store,
    *,
    fresh_hours: float = 24,
    progress: Progress = _quiet,
) -> CollectStats:
    stats = CollectStats()
    run_id = store.start_run("backfill", {"days": plan.days, "locations": len(plan.location_ids)}, plan.started_at)
    try:
        todo = plan.locations_to_fetch
        progress(f"Fetching {len(todo):,} CQC locations")
        providers = _fetch_locations(cqc, store, todo, stats, progress, keep=lambda *_: True, total=len(todo))
        providers |= _registered_provider_ids(store, plan.fresh_location_ids)
        if plan.only_new:
            fresh = {e.entity_id for e in store.iter_entities(CQC, "provider", include_gone=True)}
        else:
            fresh = store.fetched_since(CQC, "provider", plan.started_at - timedelta(hours=fresh_hours))
        progress(f"Fetching {len(providers - fresh):,} CQC providers ({len(providers & fresh):,} fresh, skipped)")
        _fetch_providers(cqc, store, providers - fresh, stats, progress)

        today = plan.started_at.date()
        progress(f"Fetching Companies House incorporations since {today - timedelta(days=plan.days)}")
        _fetch_companies(ch, store, today - timedelta(days=plan.days), today, stats)

        # Changes from the moment the backfill started are picked up by the next sync.
        _advance_cursor(store, CQC, CQC_CHANGES_STREAM, to_iso(plan.started_at))
        _advance_cursor(store, CH, CH_INCORPORATIONS_STREAM, today.isoformat())
    except BaseException:
        store.finish_run(run_id, "failed", stats.as_dict())
        raise
    store.finish_run(run_id, "ok" if not stats.failures else "partial", stats.as_dict())
    return stats


def _advance_cursor(store: Store, source: str, stream: str, value: str) -> None:
    """Move a cursor forward, never back (both cursor formats sort as text)."""
    current = store.get_cursor(source, stream)
    if current is None or value > current:
        store.set_cursor(source, stream, value)


class NotBackfilledError(RuntimeError):
    pass


def run_sync(
    cqc: CqcSource,
    ch: CompaniesHouseSource,
    store: Store,
    scope: CareScope,
    *,
    now: datetime,
    progress: Progress = _quiet,
) -> CollectStats:
    """Fetch everything that changed since the last backfill/sync and store it."""
    cqc_cursor = store.get_cursor(CQC, CQC_CHANGES_STREAM)
    ch_cursor = store.get_cursor(CH, CH_INCORPORATIONS_STREAM)
    if cqc_cursor is None or ch_cursor is None:
        raise NotBackfilledError("no sync cursor yet: run `signals backfill` first")

    stats = CollectStats()
    window = FetchWindow(from_iso(cqc_cursor), now)
    run_id = store.start_run("sync", {"since": cqc_cursor, "until": to_iso(now)}, now)
    try:
        location_ids = list(cqc.changed_ids("location", window))
        provider_ids = list(cqc.changed_ids("provider", window))
        stats.bump("location_changes", len(location_ids))
        stats.bump("provider_changes", len(provider_ids))
        progress(f"CQC changes since {cqc_cursor}: {len(location_ids):,} locations, {len(provider_ids):,} providers")

        # The change feed is national and only gives IDs, so each changed location's detail is fetched
        # to see whether it is in scope. Tracked locations are always kept (e.g. to see deregistration).
        def keep(location_id: str, payload: dict) -> bool:
            return store.has(CQC, "location", location_id) or scope.location_in_scope(payload)

        new_providers = _fetch_locations(cqc, store, location_ids, stats, progress, keep=keep, total=len(location_ids))
        wanted = {p for p in provider_ids if store.has(CQC, "provider", p)}
        wanted |= {p for p in new_providers if not store.has(CQC, "provider", p)}
        _fetch_providers(cqc, store, wanted, stats, progress)

        ch_from = date.fromisoformat(ch_cursor) - timedelta(days=CH_OVERLAP_DAYS)
        _fetch_companies(ch, store, ch_from, now.date(), stats)

        # Formation-agent companies: re-read their profiles to see if they have moved to a real address.
        # A failed check is simply retried next time, so it doesn't hold the cursors back.
        recheck_companies(ch, store, now, bump=stats.bump, fail=lambda _: stats.bump("company_recheck_failed"))

        if not stats.failures:
            store.set_cursor(CQC, CQC_CHANGES_STREAM, to_iso(now))
            store.set_cursor(CH, CH_INCORPORATIONS_STREAM, now.date().isoformat())
    except BaseException:
        store.finish_run(run_id, "failed", stats.as_dict())
        raise
    store.finish_run(run_id, "ok" if not stats.failures else "partial", stats.as_dict())
    return stats
