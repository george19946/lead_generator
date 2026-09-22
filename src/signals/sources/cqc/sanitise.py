"""Strip personal data from raw CQC records before they are stored or saved as fixtures.

CQC records name registered managers and nominated individuals in `contacts` arrays
(e.g. under `regulatedActivities[]`), using `person*` keys. We drop these unless the
config explicitly opts in via `include_personal_names`.
"""

from __future__ import annotations

from typing import Any

PERSON_KEYS = frozenset({"personTitle", "personGivenName", "personFamilyName", "personRoles"})
CONTACT_KEYS = frozenset({"contacts"})


def strip_personal_names(record: Any) -> Any:
    """Return a deep copy of `record` with contact/person-name fields removed."""
    if isinstance(record, dict):
        return {
            key: strip_personal_names(value)
            for key, value in record.items()
            if key not in CONTACT_KEYS and key not in PERSON_KEYS
        }
    if isinstance(record, list):
        return [strip_personal_names(item) for item in record]
    return record


def sanitise(record: Any, include_personal_names: bool = False) -> Any:
    return record if include_personal_names else strip_personal_names(record)
