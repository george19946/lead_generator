"""Customer regions: decide which configured regions a record belongs to.

A region matches a record if ANY of its criteria match (see config/signals.yaml):
the register's region name, the local authority, or the postcode area/district.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from signals.settings import RegionConfig

_OUTWARD = re.compile(r"^([A-Z]{1,2})(\d[A-Z\d]?)$")


def _norm(text: str | None) -> str:
    return " ".join((text or "").replace("&", "and").lower().split())


def outward_code(postcode: str | None) -> str | None:
    """The outward code of a UK postcode ("SE1 7PB" -> "SE1"), or None if it doesn't look like one."""
    if not postcode:
        return None
    compact = re.sub(r"\s+", "", postcode.upper())
    if len(compact) < 5:
        # Allow a bare outward code ("E14") as well as full postcodes.
        return compact if _OUTWARD.match(compact) else None
    outward = compact[:-3]
    return outward if _OUTWARD.match(outward) else None


def postcode_matches(postcode: str | None, areas: list[str]) -> bool:
    """True if the postcode is in any of the areas ("E", "IG") or districts ("SE1", "N16", "EC1").

    A district also covers its sub-districts ("EC1" matches "EC1A 1BB") but not longer numbers
    ("E1" does not match "E14 5AB").
    """
    outward = outward_code(postcode)
    if not outward:
        return False
    area = _OUTWARD.match(outward).group(1)
    for raw in areas:
        want = raw.strip().upper().replace(" ", "")
        if not want:
            continue
        if want.isalpha():
            if area == want:
                return True
        elif outward == want or (outward.startswith(want) and outward[len(want)].isalpha()):
            return True
    return False


class RegionMatcher:
    def __init__(self, regions: Mapping[str, RegionConfig]):
        self.regions = dict(regions)

    def match(
        self, *, region: str | None = None, local_authority: str | None = None, postcode: str | None = None
    ) -> list[str]:
        """Names of the configured regions the record belongs to, in config order."""
        hits = []
        for name, cfg in self.regions.items():
            if (
                (cfg.cqc_region and region and _norm(cfg.cqc_region) == _norm(region))
                or (local_authority and _norm(local_authority) in {_norm(la) for la in cfg.local_authorities})
                or (cfg.postcode_areas and postcode_matches(postcode, cfg.postcode_areas))
            ):
                hits.append(name)
        return hits
