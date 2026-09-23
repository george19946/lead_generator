"""Customer regions: decide which configured regions a record belongs to.

A region matches a record if ANY of its criteria match (see config/signals.yaml):
the register's region name, the local authority, or the postcode area/district.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
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


class PostcodeLookup:
    """Infer a register's region and local authority for a postcode, learned from records that have both.

    Some sources (e.g. company registers) give only a postcode. Records that carry a postcode *and* a region
    (e.g. CQC locations) vote per postcode district. If the district is unknown, the postcode area is used,
    but only when it is dominated by one region (`AREA_AGREEMENT`), because areas can straddle regions.
    """

    AREA_AGREEMENT = 0.9
    AREA_MIN_SAMPLES = 5

    def __init__(self) -> None:
        self._district_region: dict[str, Counter[str]] = defaultdict(Counter)
        self._district_la: dict[str, Counter[str]] = defaultdict(Counter)
        self._area_region: dict[str, Counter[str]] = defaultdict(Counter)

    def add(self, postcode: str | None, region: str | None, local_authority: str | None) -> None:
        district = outward_code(postcode)
        if not district:
            return
        if region:
            self._district_region[district][region] += 1
            self._area_region[_OUTWARD.match(district).group(1)][region] += 1
        if local_authority:
            self._district_la[district][local_authority] += 1

    def lookup(self, postcode: str | None) -> tuple[str | None, str | None]:
        """(region, local_authority) for the postcode; either may be None."""
        district = outward_code(postcode)
        if not district:
            return None, None
        region = _top(self._district_region.get(district))
        local_authority = _top(self._district_la.get(district))
        if region is None:
            votes = self._area_region.get(_OUTWARD.match(district).group(1))
            if votes and sum(votes.values()) >= self.AREA_MIN_SAMPLES:
                name, count = max(votes.items(), key=lambda kv: (kv[1], kv[0]))
                if count / sum(votes.values()) >= self.AREA_AGREEMENT:
                    region = name
        return region, local_authority


def _top(votes: Counter[str] | None) -> str | None:
    if not votes:
        return None
    return max(votes.items(), key=lambda kv: (kv[1], kv[0]))[0]
