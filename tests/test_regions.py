import pytest

from signals.core.regions import RegionMatcher, outward_code, postcode_matches
from signals.settings import RegionConfig


@pytest.mark.parametrize(
    ("postcode", "outward"),
    [("SE1 7PB", "SE1"), ("se17pb", "SE1"), ("EC1A 1BB", "EC1A"), ("E14", "E14"), ("W1D 3QU", "W1D"),
     ("", None), (None, None), ("not a postcode", None), ("12345", None)],
)
def test_outward_code(postcode, outward):
    assert outward_code(postcode) == outward


@pytest.mark.parametrize(
    ("postcode", "areas", "expected"),
    [
        ("E14 5AB", ["E"], True),
        ("EC1A 1BB", ["E"], False),  # area EC is not area E
        ("IG1 1AA", ["E", "IG", "RM"], True),
        ("SE1 7PB", ["SE1"], True),
        ("SE10 9AA", ["SE1"], False),
        ("EC1A 1BB", ["EC1"], True),  # sub-district
        ("E1W 1AA", ["e1"], True),
        ("E14 5AB", ["E1"], False),
        ("N16 0AA", [" n16 "], True),
        (None, ["E"], False),
    ],
)
def test_postcode_matches(postcode, areas, expected):
    assert postcode_matches(postcode, areas) is expected


def test_region_matcher_any_criterion():
    matcher = RegionMatcher(
        {
            "london": RegionConfig(cqc_region="London"),
            "east-london": RegionConfig(postcode_areas=["E", "IG", "RM"]),
            "yorkshire": RegionConfig(cqc_region="Yorkshire & Humberside"),
            "kent": RegionConfig(local_authorities=["Kent", "Medway"]),
        }
    )
    assert matcher.match(region="London", postcode="E14 5AB") == ["london", "east-london"]
    assert matcher.match(region="East", postcode="IG10 1AA") == ["east-london"]  # Loughton, Essex
    assert matcher.match(region="yorkshire and humberside") == ["yorkshire"]
    assert matcher.match(region="South East", local_authority="medway") == ["kent"]
    assert matcher.match(region="North West", postcode="FY4 2RF") == []
