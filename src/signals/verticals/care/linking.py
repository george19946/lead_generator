"""Link Companies House companies to CQC providers.

1. Exact: the provider's `companiesHouseNumber` equals the company number (after normalising).
2. Fuzzy: similar names (stdlib difflib), with a lower bar when the postcode district matches too.
   Fuzzy links are reported as "possible" matches for a person to check.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from signals.core.matching import Candidate, NameIndex
from signals.sources.companies_house.legal_form import normalise_company_number
from signals.sources.companies_house.models import ChCompany
from signals.sources.cqc.models import CqcProvider

EXACT = "companies house number"


@dataclass(frozen=True)
class ProviderLink:
    provider: CqcProvider
    method: str  # EXACT, "name+postcode" or "name"
    score: float

    @property
    def exact(self) -> bool:
        return self.method == EXACT


class CqcLinker:
    def __init__(self, providers: Iterable[CqcProvider]):
        self.providers = {p.provider_id: p for p in providers}
        self.by_number: dict[str, CqcProvider] = {}
        for p in sorted(self.providers.values(), key=lambda p: p.provider_id):
            number = normalise_company_number(p.companies_house_number)
            if number:
                self.by_number.setdefault(number, p)
        self.names = NameIndex(Candidate(p.provider_id, p.name, p.postal_code) for p in self.providers.values())

    def link(self, company: ChCompany) -> ProviderLink | None:
        number = normalise_company_number(company.company_number)
        if number and number in self.by_number:
            return ProviderLink(self.by_number[number], EXACT, 1.0)
        office = company.registered_office_address
        match = self.names.best(company.company_name, office.postal_code if office else None)
        if match:
            return ProviderLink(self.providers[match.key], match.method, match.score)
        return None
