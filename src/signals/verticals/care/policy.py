"""Companies-only mode: keep no data about sole traders or partnerships.

A sole trader's or partnership's business details identify people, so holding them is processing personal data. In
companies-only mode (config `companies_only`, on by default) they are erased and never stored again, so the leads
contain organisations only. This uses the opt-out list with a note of its own, which marks these entries as a
policy rather than someone's objection. Turning the mode off lifts exactly those entries, and nothing else.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError

from signals.core.legal_form import LegalForm
from signals.db.store import Store
from signals.sources.cqc.legal_form import provider_legal_form
from signals.sources.cqc.models import CqcProvider

COMPANIES_ONLY_NOTE = "companies-only mode: sole trader or partnership (not an opt-out)"
INDIVIDUAL_FORMS = frozenset({LegalForm.SOLE_TRADER, LegalForm.PARTNERSHIP})


def individual_providers(store: Store) -> list[str]:
    """Stored CQC providers that are sole traders or partnerships."""
    out = []
    for entity in store.iter_entities("cqc", "provider"):
        try:
            provider = CqcProvider.model_validate(entity.payload)
        except ValidationError:
            continue
        if provider_legal_form(provider) in INDIVIDUAL_FORMS:
            out.append(provider.provider_id)
    return out


def apply_companies_only(store: Store, now: datetime) -> int:
    """Erase every stored sole trader and partnership (with their locations and leads) and block them.

    Returns how many providers were removed.
    """
    removed = 0
    for provider_id in individual_providers(store):
        if not store.is_suppressed(provider_id):
            store.suppress(provider_id, COMPANIES_ONLY_NOTE, now)
            removed += 1
    return removed


def lift_companies_only(store: Store) -> int:
    """Remove the companies-only blocks (never real opt-outs). Returns how many were lifted."""
    lifted = 0
    for entity_id, _, note in store.suppressed():
        if note == COMPANIES_ONLY_NOTE:
            lifted += store.unsuppress(entity_id)
    return lifted
