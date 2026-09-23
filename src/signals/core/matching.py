"""Organisation-name matching with stdlib difflib (no extra dependencies).

Names are normalised (case, punctuation, "&", legal suffixes) and compared with SequenceMatcher.
A match needs a high name score, or a slightly lower one plus the same postcode district.
Candidates are blocked by first name token and by postcode district, so matching stays fast.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

from signals.core.regions import outward_code

LEGAL_SUFFIXES = frozenset({"limited", "ltd", "llp", "plc", "lp", "cic", "cio", "the"})

MIN_SCORE = 0.93  # name alone
MIN_SCORE_SAME_DISTRICT = 0.85  # name plus the same postcode district


def normalise_name(name: str | None) -> str:
    text = (name or "").lower().replace("&", " and ")
    tokens = re.sub(r"[^a-z0-9]+", " ", text).split()
    return " ".join(t for t in tokens if t not in LEGAL_SUFFIXES)


def name_similarity(a: str | None, b: str | None) -> float:
    na, nb = normalise_name(a), normalise_name(b)
    if not na or not nb:
        return 0.0
    return 1.0 if na == nb else SequenceMatcher(None, na, nb).ratio()


@dataclass(frozen=True)
class Candidate:
    key: str
    name: str
    postcode: str | None = None


@dataclass(frozen=True)
class NameMatch:
    key: str
    name: str
    score: float
    method: str  # "name" or "name+postcode"


class NameIndex:
    def __init__(self, candidates: Iterable[Candidate]):
        self._by_token: dict[str, list[Candidate]] = defaultdict(list)
        self._by_district: dict[str, list[Candidate]] = defaultdict(list)
        for c in candidates:
            norm = normalise_name(c.name)
            if norm:
                self._by_token[norm.split()[0]].append(c)
            district = outward_code(c.postcode)
            if district:
                self._by_district[district].append(c)

    def best(self, name: str | None, postcode: str | None = None) -> NameMatch | None:
        norm = normalise_name(name)
        if not norm:
            return None
        district = outward_code(postcode)
        pool = {c.key: c for c in self._by_token.get(norm.split()[0], [])}
        if district:
            pool.update({c.key: c for c in self._by_district.get(district, [])})
        best: NameMatch | None = None
        for key in sorted(pool):  # sorted: ties resolve the same way every run
            c = pool[key]
            score = name_similarity(name, c.name)
            same_district = district is not None and outward_code(c.postcode) == district
            if score >= MIN_SCORE or (same_district and score >= MIN_SCORE_SAME_DISTRICT):
                match = NameMatch(c.key, c.name, round(score, 3), "name+postcode" if same_district else "name")
                if best is None or (match.score, match.method == "name+postcode") > (best.score, best.method == "name+postcode"):
                    best = match
        return best
