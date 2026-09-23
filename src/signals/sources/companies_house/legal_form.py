"""Map Companies House company types and company-number prefixes to a LegalForm."""

from __future__ import annotations

import re

from signals.core.legal_form import LegalForm

# Advanced-search `company_type` values. Anything not listed falls back to the company-number prefix.
COMPANY_TYPES = {
    "ltd": LegalForm.LIMITED_COMPANY,
    "private-limited-guarant-nsc": LegalForm.LIMITED_COMPANY,
    "private-limited-guarant-nsc-limited-exemption": LegalForm.LIMITED_COMPANY,
    "private-limited-shares-section-30-exemption": LegalForm.LIMITED_COMPANY,
    "private-unlimited": LegalForm.OTHER_CORPORATE,
    "private-unlimited-nsc": LegalForm.OTHER_CORPORATE,
    "plc": LegalForm.OTHER_CORPORATE,
    "old-public-company": LegalForm.OTHER_CORPORATE,
    "llp": LegalForm.LLP,
    "charitable-incorporated-organisation": LegalForm.OTHER_CORPORATE,
    "scottish-charitable-incorporated-organisation": LegalForm.OTHER_CORPORATE,
    "registered-society-non-jurisdictional": LegalForm.OTHER_CORPORATE,
    "industrial-and-provident-society": LegalForm.OTHER_CORPORATE,
    "royal-charter": LegalForm.OTHER_CORPORATE,
    "scottish-partnership": LegalForm.OTHER_CORPORATE,  # a legal person, so a corporate subscriber
    "limited-partnership": LegalForm.PARTNERSHIP,  # England & Wales LPs are not legal persons
}

# Company-number prefixes (numbers without a prefix are England & Wales companies).
PREFIXES = {
    "SC": LegalForm.LIMITED_COMPANY,
    "NI": LegalForm.LIMITED_COMPANY,
    "OC": LegalForm.LLP,
    "SO": LegalForm.LLP,
    "NC": LegalForm.LLP,
    "CE": LegalForm.OTHER_CORPORATE,  # CIO
    "CS": LegalForm.OTHER_CORPORATE,  # Scottish CIO
    "IP": LegalForm.OTHER_CORPORATE,
    "SP": LegalForm.OTHER_CORPORATE,
    "RS": LegalForm.OTHER_CORPORATE,
    "RC": LegalForm.OTHER_CORPORATE,
    "SL": LegalForm.OTHER_CORPORATE,  # Scottish limited partnership (legal person)
    "LP": LegalForm.PARTNERSHIP,
}


def normalise_company_number(number: str | None) -> str | None:
    """Upper-case, strip spaces, and zero-pad all-digit numbers to 8 ("3959933" -> "03959933")."""
    if not number:
        return None
    compact = re.sub(r"\s+", "", str(number)).upper()
    if not compact:
        return None
    if compact.isdigit():
        return compact.zfill(8)
    match = re.fullmatch(r"([A-Z]{2})(\d+)", compact)
    return f"{match.group(1)}{match.group(2).zfill(6)}" if match else compact


def legal_form_from_number(number: str | None) -> LegalForm:
    number = normalise_company_number(number)
    if not number:
        return LegalForm.UNKNOWN
    if number.isdigit():
        return LegalForm.LIMITED_COMPANY
    return PREFIXES.get(number[:2], LegalForm.UNKNOWN)


def legal_form(company_type: str | None, company_number: str | None = None) -> LegalForm:
    known = COMPANY_TYPES.get((company_type or "").strip().lower())
    return known or legal_form_from_number(company_number)
