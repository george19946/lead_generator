"""Legal form and the PECR contact channel it allows (see PRIVACY_NOTES.md).

Under PECR, unsolicited marketing email may go to corporate subscribers (companies, LLPs, Scottish
partnerships, public bodies...) but not to individual subscribers (sole traders and other partnerships).
When the legal form is unknown we assume the stricter rule.
"""

from __future__ import annotations

from enum import StrEnum


class LegalForm(StrEnum):
    LIMITED_COMPANY = "limited company"
    LLP = "LLP"
    OTHER_CORPORATE = "other corporate body"  # PLC, CIO, registered society, Scottish partnership...
    PUBLIC_BODY = "public body"
    SOLE_TRADER = "sole trader"
    PARTNERSHIP = "partnership"
    UNKNOWN = "unknown"


CORPORATE = frozenset({LegalForm.LIMITED_COMPANY, LegalForm.LLP, LegalForm.OTHER_CORPORATE, LegalForm.PUBLIC_BODY})

EMAIL_OK = "email OK"
PHONE_CHECK_TPS = "phone - check TPS/CTPS first"
POST_ONLY = "post only"


def is_corporate(form: LegalForm) -> bool:
    return form in CORPORATE


def suggested_channel(form: LegalForm, has_phone: bool) -> str:
    """How a lead may be contacted. Any phone number must still be screened against TPS/CTPS."""
    if is_corporate(form):
        return EMAIL_OK
    return PHONE_CHECK_TPS if has_phone else POST_ONLY
