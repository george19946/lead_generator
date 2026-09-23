"""Legal form of a CQC provider, from `ownershipType` and `companiesHouseNumber`."""

from __future__ import annotations

from signals.core.legal_form import LegalForm
from signals.sources.companies_house.legal_form import legal_form_from_number
from signals.sources.cqc.models import CqcProvider


def provider_legal_form(provider: CqcProvider) -> LegalForm:
    ownership = (provider.ownership_type or "").strip().lower()
    if ownership == "individual":
        return LegalForm.SOLE_TRADER
    if "nhs" in ownership or "local authority" in ownership:
        return LegalForm.PUBLIC_BODY
    from_number = legal_form_from_number(provider.companies_house_number)
    if from_number is not LegalForm.UNKNOWN:
        return from_number
    if ownership == "partnership":
        return LegalForm.PARTNERSHIP
    # An "Organisation" without a company number may be a charitable trust or other unincorporated body.
    return LegalForm.UNKNOWN
