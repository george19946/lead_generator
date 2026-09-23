"""Evaluate a vertical's feeds for a digest week and record new leads exactly once.

A lead is recorded for week W when its event date falls in W, or up to `grace_days` before it (registers
publish some events late). Leads without an event date are recorded when first seen. Recording is
idempotent (unique trigger), so a lead appears in the first week that sees it and never again, and
re-running a week returns the same leads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from signals.core.feed import Lead, Vertical, Week
from signals.db.store import LeadRow, Store

GRACE_DAYS = 14


@dataclass
class FeedResult:
    feed: str
    qualifying: int = 0  # currently qualifying, any date (e.g. every never-inspected location)
    recorded: int = 0  # newly recorded in this run
    leads: list[LeadRow] = field(default_factory=list)  # all of this week's leads for the feed


def in_window(lead: Lead, week: Week, grace_days: int) -> bool:
    if lead.event_date is None:
        return True
    return week.start - timedelta(days=grace_days) <= lead.event_date <= week.ending


def run_week(
    vertical: Vertical, store: Store, week: Week, *, now: datetime, grace_days: int = GRACE_DAYS
) -> dict[str, FeedResult]:
    run_id = store.start_run("run", {"vertical": vertical.name, "week_ending": str(week)}, now)
    results: dict[str, FeedResult] = {}
    try:
        for feed in vertical.feeds():
            result = results[feed.name] = FeedResult(feed.name)
            for lead in feed.leads():
                result.qualifying += 1
                if lead.regions and in_window(lead, week, grace_days):
                    result.recorded += store.record_lead(vertical.name, lead, week.ending, now)
            result.leads = store.leads_for_week(vertical.name, week.ending, feed.name)
    except BaseException:
        store.finish_run(run_id, "failed", {})
        raise
    store.finish_run(
        run_id, "ok", {name: {"recorded": r.recorded, "week": len(r.leads)} for name, r in results.items()}, now
    )
    return results
