"""The care vertical's three feeds, evaluated over the stored register data.

- new_companies: companies incorporated with a care SIC code, linked to CQC where possible.
  Trigger: the incorporation date.
- never_inspected: registered adult social care locations with no rating and no inspection yet.
  Trigger: the registration date, so only newly registered locations become weekly leads; the full
  current list is available from `NeverInspectedFeed.leads()` (for never_inspected_all.csv).
- poor_ratings: locations currently rated Requires improvement or Inadequate.
  Trigger: the rating and its publication date, so a re-rating is a new lead.
- location_unknown: new care companies registered at a formation agent (shared registered office), so they
  can't be placed in a region; listed nationally.
- company_located: those formation-agent companies once they reveal a real location (see CompanyLocatedFeed).
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import replace
from datetime import date
from functools import cached_property
from typing import Any

from pydantic import ValidationError

from signals.core.feed import Lead
from signals.core.legal_form import LegalForm, suggested_channel
from signals.core.regions import PostcodeLookup
from signals.db.store import Store, StoredEntity
from signals.sources.companies_house.legal_form import legal_form as ch_legal_form
from signals.sources.companies_house.legal_form import normalise_company_number
from signals.sources.companies_house.models import ChCompany
from signals.sources.cqc.legal_form import provider_legal_form
from signals.sources.cqc.models import CqcLocation, CqcProvider, EffectiveRating, normalise_rating
from signals.verticals.care.collect import ASC_DIRECTORATE, CareScope
from signals.verticals.care.flags import name_flag, sic_labels
from signals.verticals.care.linking import CqcLinker
from signals.verticals.care.watch import is_shared, office_postcode, postcode_counts, postcode_key

log = logging.getLogger(__name__)

POOR_RATINGS = ("Requires improvement", "Inadequate")
RATING_RANK = {"Outstanding": 4, "Good": 3, "Requires improvement": 2, "Inadequate": 1}
ALL_ENGLAND = "england"
NATIONAL = "national"  # pseudo-region for leads that can't be placed (location_unknown)
CH_PROFILE = "https://find-and-update.company-information.service.gov.uk/company/"


class CareData:
    """Everything the feeds need, loaded from the store once per run."""

    def __init__(self, store: Store, scope: CareScope):
        self.store = store
        self.scope = scope
        self.skipped = 0

    def _parse(self, model: type, entity: StoredEntity) -> Any:
        try:
            return model.model_validate(entity.payload)
        except ValidationError as exc:
            self.skipped += 1
            log.warning("skipping %s %s: %s", entity.entity_type, entity.entity_id, exc.errors()[:1])
            return None

    @cached_property
    def locations(self) -> list[tuple[StoredEntity, CqcLocation]]:
        out = []
        for entity in self.store.iter_entities("cqc", "location"):
            loc = self._parse(CqcLocation, entity)
            if loc:
                out.append((entity, loc))
        return out

    @cached_property
    def providers(self) -> dict[str, CqcProvider]:
        out = {}
        for entity in self.store.iter_entities("cqc", "provider"):
            provider = self._parse(CqcProvider, entity)
            if provider:
                out[provider.provider_id] = provider
        return out

    @cached_property
    def companies(self) -> list[ChCompany]:
        out = []
        for entity in self.store.iter_entities("companies_house", "company"):
            company = self._parse(ChCompany, entity)
            if company:
                out.append(company)
        return out

    @cached_property
    def postcodes(self) -> PostcodeLookup:
        lookup = PostcodeLookup()
        for _, loc in self.locations:
            lookup.add(loc.postal_code, loc.region, loc.local_authority)
        for provider in self.providers.values():
            lookup.add(provider.postal_code, provider.region, provider.local_authority)
        return lookup

    @cached_property
    def linker(self) -> CqcLinker:
        return CqcLinker(self.providers.values())

    @cached_property
    def company_leads(self) -> list[tuple[bool, Lead]]:
        return build_company_leads(self)

    @cached_property
    def postcode_counts(self) -> Counter[str]:
        return postcode_counts(
            {"registered_office_address": c.registered_office_address.model_dump()}
            for c in self.companies
            if c.registered_office_address
        )

    def regions(self, *, region: str | None, local_authority: str | None, postcode: str | None) -> tuple[str, ...]:
        if self.scope.all_england:
            return (ALL_ENGLAND,)
        return tuple(self.scope.matcher.match(region=region, local_authority=local_authority, postcode=postcode))


def _provider_fields(provider: CqcProvider | None, has_phone: bool) -> dict[str, Any]:
    form = provider_legal_form(provider) if provider else LegalForm.UNKNOWN
    number = normalise_company_number(provider.companies_house_number) if provider else None
    return {
        "provider_id": provider.provider_id if provider else None,
        "provider_name": provider.name if provider else None,
        "provider_ownership": provider.ownership_type if provider else None,
        "provider_company_number": number,
        "provider_url": provider.profile_url if provider else None,
        "companies_house_url": f"{CH_PROFILE}{number}" if number else None,
        "legal_form": str(form),
        "suggested_channel": suggested_channel(form, has_phone),
    }


def location_fields(data: CareData, entity: StoredEntity, loc: CqcLocation) -> dict[str, Any]:
    provider = data.providers.get(loc.provider_id or "")
    phone = loc.main_phone_number or (provider.main_phone_number if provider else None)
    return {
        "location_id": loc.location_id,
        "location_name": loc.name,
        "address": loc.address,
        "postcode": loc.postal_code,
        "cqc_region": loc.region,
        "local_authority": loc.local_authority,
        "service_types": "; ".join(s.name for s in loc.gac_service_types if s.name),
        "care_home": loc.care_home,
        "beds": loc.number_of_beds,
        "registration_date": loc.registration_date.isoformat() if loc.registration_date else None,
        "dormant": entity.payload.get("dormancy") == "Y",
        "phone": phone,
        "website": loc.website or (provider.website if provider else None),
        "cqc_url": loc.profile_url,
        **_provider_fields(provider, bool(phone)),
    }


def _is_registered_asc(loc: CqcLocation) -> bool:
    return loc.registration_status == "Registered" and loc.inspection_directorate == ASC_DIRECTORATE


def _location_regions(data: CareData, loc: CqcLocation) -> tuple[str, ...]:
    return data.regions(region=loc.region, local_authority=loc.local_authority, postcode=loc.postal_code)


class NewCompaniesFeed:
    """New care companies whose registered office places them in a customer region."""

    name = "new_companies"

    def __init__(self, data: CareData):
        self.data = data

    def leads(self) -> list[Lead]:
        return [lead for shared, lead in self.data.company_leads if not shared]


class LocationUnknownFeed:
    """New care companies registered at a formation agent or virtual office: location unknown.

    Their postcode says nothing about where they operate, so they get no customer region. They are
    recorded under the pseudo-region "national" and listed separately in every region's digest.
    """

    name = "location_unknown"

    def __init__(self, data: CareData):
        self.data = data

    def leads(self) -> list[Lead]:
        return [
            replace(lead, feed=self.name, regions=(NATIONAL,)) for shared, lead in self.data.company_leads if shared
        ]


def build_company_leads(data: CareData) -> list[tuple[bool, Lead]]:
    """A lead per stored company, with whether its registered office is shared (formation agent)."""
    out = []
    for company in data.companies:
        office = company.registered_office_address
        postcode = office.postal_code if office else None
        shared_by = data.postcode_counts.get(postcode_key(postcode), 0) if postcode else 0
        shared = is_shared(postcode, data.postcode_counts)
        region, local_authority = (None, None) if shared else data.postcodes.lookup(postcode)
        regions = () if shared else data.regions(region=region, local_authority=local_authority, postcode=postcode)
        link = data.linker.link(company)
        form = ch_legal_form(company.company_type, company.company_number)
        created = company.date_of_creation
        lead = Lead(
            feed=NewCompaniesFeed.name,
            entity_key=f"companies_house:company:{company.company_number}",
            trigger_key=f"incorporated:{created.isoformat() if created else 'unknown'}",
            event_date=created,
            regions=regions,
            data={
                "company_number": company.company_number,
                "company_name": company.company_name,
                "company_type": company.company_type,
                "company_status": company.company_status,
                "incorporated": created.isoformat() if created else None,
                "sic_codes": "; ".join(company.sic_codes),
                "sic_description": sic_labels(company.sic_codes),
                "flag": name_flag(company.company_name),
                "address": office.one_line() if office else None,
                "postcode": postcode,
                "shared_registered_office": shared,
                "companies_at_postcode": shared_by,
                "inferred_cqc_region": region,
                "inferred_local_authority": local_authority,
                "companies_house_url": company.url,
                "legal_form": str(form),
                "suggested_channel": suggested_channel(form, has_phone=False),
                "cqc_registered": "yes" if link and link.exact else ("possible" if link else "no"),
                "cqc_provider_id": link.provider.provider_id if link else None,
                "cqc_provider_name": link.provider.name if link else None,
                "cqc_match": link.method if link else None,
                "cqc_match_score": link.score if link else None,
            },
        )
        out.append((shared, lead))
    return out


class CompanyLocatedFeed:
    """Formation-agent companies that have since revealed where they operate.

    - "moved": the registered office moved from a shared (formation-agent) postcode to one that places the
      company in a customer region. Found by the weekly re-checks (watch.py); dated when we saw the move.
    - "registered with CQC": a company still at a formation agent now appears as a CQC provider (matched
      by company number) in a customer region. Dated by the provider's CQC registration.
    """

    name = "company_located"

    def __init__(self, data: CareData):
        self.data = data

    def leads(self) -> list[Lead]:
        store, counts = self.data.store, self.data.postcode_counts
        moved_ids = store.ids_with_history("companies_house", "company")
        out = []
        for shared, base in self.data.company_leads:
            number = base.data["company_number"]
            if not shared and number in moved_ids:
                move = self._move(number, counts)
                if move and base.regions:
                    previous, when = move
                    out.append(replace(
                        base, feed=self.name, trigger_key=f"moved:{postcode_key(base.data['postcode'])}",
                        event_date=when,
                        data={**base.data, "located_by": "moved registered office", "located_date": when.isoformat(),
                              "previous_postcode": previous},
                    ))
            if shared and base.data["cqc_registered"] == "yes":
                provider = self.data.providers.get(base.data["cqc_provider_id"])
                regions = self.data.regions(region=provider.region, local_authority=provider.local_authority,
                                            postcode=provider.postal_code) if provider else ()
                if regions:
                    registered = provider.registration_date
                    out.append(replace(
                        base, feed=self.name, trigger_key=f"cqc:{provider.provider_id}", event_date=registered,
                        regions=regions,
                        data={**base.data, "located_by": "registered with CQC",
                              "located_date": registered.isoformat() if registered else None,
                              "previous_postcode": base.data["postcode"],
                              "inferred_local_authority": provider.local_authority,
                              "cqc_provider_address": provider.address, "cqc_provider_postcode": provider.postal_code},
                    ))
        return out

    def _move(self, number: str, counts: Counter[str]) -> tuple[str, date] | None:
        """(previous postcode, date first seen at the current one) if it moved away from a shared postcode."""
        history = self.data.store.history("companies_house", "company", number)
        current = postcode_key(office_postcode(history[-1].payload))
        since = None
        for snapshot in reversed(history):
            postcode = office_postcode(snapshot.payload)
            if postcode_key(postcode) == current:
                since = snapshot.fetched_at.date()
                continue
            return (postcode, since) if is_shared(postcode, counts) and since else None
        return None


class NeverInspectedFeed:
    name = "never_inspected"

    def __init__(self, data: CareData):
        self.data = data

    @staticmethod
    def qualifies(loc: CqcLocation) -> bool:
        inspected = loc.last_inspection is not None and loc.last_inspection.date is not None
        return _is_registered_asc(loc) and loc.overall_rating is None and not loc.historic_ratings and not inspected

    def leads(self) -> list[Lead]:
        out = []
        for entity, loc in self.data.locations:
            if not self.qualifies(loc):
                continue
            registered = loc.registration_date
            out.append(
                Lead(
                    feed=self.name,
                    entity_key=f"cqc:location:{loc.location_id}",
                    trigger_key=f"registered:{registered.isoformat() if registered else 'unknown'}",
                    event_date=registered,
                    regions=_location_regions(self.data, loc),
                    data=location_fields(self.data, entity, loc),
                )
            )
        return out


def rating_change(previous: str | None, current: str) -> str:
    if previous is None:
        return "first rating"
    before, now = RATING_RANK.get(previous), RATING_RANK.get(current)
    if before is None or now is None:
        return "unknown"
    if now < before:
        return "downgrade"
    return "no change" if now == before else "improved but still poor"


class PoorRatingsFeed:
    name = "poor_ratings"

    def __init__(self, data: CareData):
        self.data = data

    def _previous(self, loc: CqcLocation, current: EffectiveRating) -> tuple[str | None, date | None]:
        """The rating before the current one: from CQC's rating history, else from our own snapshots."""
        earlier = [
            (h.report_date, h.overall.rating)
            for h in loc.historic_ratings
            if h.overall and h.overall.rating and h.report_date
            and (current.published is None or h.report_date < current.published)
        ]
        if current.framework == "assessment" and loc.current_ratings and loc.current_ratings.overall:
            old = loc.current_ratings.overall
            if old.rating and old.report_date and (current.published is None or old.report_date < current.published):
                earlier.append((old.report_date, old.rating))
        if earlier:
            when, rating = max(earlier)
            return normalise_rating(rating), when
        for snapshot in reversed(self.data.store.history("cqc", "location", loc.location_id)[:-1]):
            try:
                before = CqcLocation.model_validate(snapshot.payload).overall_rating
            except ValidationError:
                continue
            if before and (before.rating, before.published) != (current.rating, current.published):
                return before.rating, before.published
        return None, None

    def _first_seen(self, loc: CqcLocation, rating: str) -> date | None:
        """For an undated rating: when our snapshots first showed it (the latest unbroken run)."""
        since = None
        for snapshot in reversed(self.data.store.history("cqc", "location", loc.location_id)):
            try:
                seen = CqcLocation.model_validate(snapshot.payload).overall_rating
            except ValidationError:
                break
            if not seen or seen.rating != rating:
                break
            since = snapshot.fetched_at.date()
        return since

    def leads(self) -> list[Lead]:
        out = []
        for entity, loc in self.data.locations:
            current = loc.overall_rating
            if not _is_registered_asc(loc) or not current or current.rating not in POOR_RATINGS:
                continue
            published = current.published or self._first_seen(loc, current.rating)
            previous, previous_date = self._previous(loc, current)
            out.append(
                Lead(
                    feed=self.name,
                    entity_key=f"cqc:location:{loc.location_id}",
                    trigger_key=f"{current.rating}:{current.published.isoformat() if current.published else 'undated'}",
                    event_date=published,
                    regions=_location_regions(self.data, loc),
                    data={
                        **location_fields(self.data, entity, loc),
                        "rating": current.rating,
                        "rating_date": current.published.isoformat() if current.published else None,
                        "rating_framework": current.framework,
                        "previous_rating": previous,
                        "previous_rating_date": previous_date.isoformat() if previous_date else None,
                        "rating_change": rating_change(previous, current.rating),
                    },
                )
            )
        return out


class CareVertical:
    name = "care"

    def __init__(self, store: Store, scope: CareScope):
        self.data = CareData(store, scope)

    def feeds(self) -> list[Any]:
        return [
            PoorRatingsFeed(self.data),
            NeverInspectedFeed(self.data),
            NewCompaniesFeed(self.data),
            LocationUnknownFeed(self.data),
            CompanyLocatedFeed(self.data),
        ]
