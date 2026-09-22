"""Checks against sanitised responses captured live by `signals smoke --save-fixtures`."""

import json
from pathlib import Path

import pytest

from signals.sources.cqc.models import CqcLocation, CqcProvider
from signals.sources.cqc.sanitise import PERSON_KEYS

CQC_DIR = Path(__file__).parent / "fixtures" / "cqc"
LOCATIONS = sorted(CQC_DIR.glob("location_*.json"))
PROVIDERS = sorted(CQC_DIR.glob("provider_*.json"))


def _keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v)
    elif isinstance(node, list):
        for item in node:
            yield from _keys(item)


@pytest.mark.parametrize("path", LOCATIONS + PROVIDERS, ids=lambda p: p.name)
def test_live_fixtures_contain_no_personal_names(path):
    keys = set(_keys(json.loads(path.read_text())))
    assert not keys & (PERSON_KEYS | {"contacts", "nominatedIndividual"})


@pytest.mark.parametrize("path", LOCATIONS, ids=lambda p: p.name)
def test_live_locations_parse(path):
    loc = CqcLocation.model_validate(json.loads(path.read_text()))
    assert loc.location_id and loc.name
    rating = loc.overall_rating
    if rating:
        assert rating.rating in {"Outstanding", "Good", "Requires improvement", "Inadequate", "Insufficient evidence to rate"}


@pytest.mark.parametrize("path", PROVIDERS, ids=lambda p: p.name)
def test_live_providers_parse(path):
    prov = CqcProvider.model_validate(json.loads(path.read_text()))
    assert prov.provider_id and prov.location_ids


def test_live_changes_page_shape():
    page = json.loads((CQC_DIR / "changes_location.json").read_text())
    assert {"changes", "total", "totalPages", "page", "perPage"} <= set(page)
    assert all(isinstance(c, str) for c in page["changes"])


def test_deregistered_location_is_recognisable():
    locs = [CqcLocation.model_validate(json.loads(p.read_text())) for p in LOCATIONS]
    dereg = [loc for loc in locs if loc.registration_status == "Deregistered"]
    assert dereg and all(loc.deregistration_date for loc in dereg)
