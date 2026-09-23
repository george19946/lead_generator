import pytest

from signals.core.legal_form import EMAIL_OK, PHONE_CHECK_TPS, POST_ONLY, LegalForm, suggested_channel
from signals.core.matching import Candidate, NameIndex, name_similarity, normalise_name
from signals.core.regions import PostcodeLookup
from signals.sources.companies_house.legal_form import legal_form, legal_form_from_number, normalise_company_number
from signals.sources.cqc.legal_form import provider_legal_form
from signals.sources.cqc.models import CqcProvider


@pytest.mark.parametrize(
    ("form", "phone", "channel"),
    [
        (LegalForm.LIMITED_COMPANY, False, EMAIL_OK),
        (LegalForm.LLP, True, EMAIL_OK),
        (LegalForm.PUBLIC_BODY, False, EMAIL_OK),
        (LegalForm.SOLE_TRADER, True, PHONE_CHECK_TPS),
        (LegalForm.PARTNERSHIP, False, POST_ONLY),
        (LegalForm.UNKNOWN, True, PHONE_CHECK_TPS),
        (LegalForm.UNKNOWN, False, POST_ONLY),
    ],
)
def test_suggested_channel(form, phone, channel):
    assert suggested_channel(form, phone) == channel


@pytest.mark.parametrize(
    ("raw", "normal"),
    [("3959933", "03959933"), (" 03959933 ", "03959933"), ("sc123456", "SC123456"), ("OC4001", "OC004001"),
     ("", None), (None, None)],
)
def test_normalise_company_number(raw, normal):
    assert normalise_company_number(raw) == normal


def test_legal_form_from_companies_house():
    assert legal_form("ltd") is LegalForm.LIMITED_COMPANY
    assert legal_form("private-limited-guarant-nsc") is LegalForm.LIMITED_COMPANY
    assert legal_form("private-limited-guarant-nsc-limited-exemption") is LegalForm.LIMITED_COMPANY
    assert legal_form("llp") is LegalForm.LLP
    assert legal_form("limited-partnership") is LegalForm.PARTNERSHIP
    assert legal_form("scottish-partnership") is LegalForm.OTHER_CORPORATE
    assert legal_form("something-new", "OC400001") is LegalForm.LLP
    assert legal_form(None, None) is LegalForm.UNKNOWN
    assert legal_form_from_number("LP012345") is LegalForm.PARTNERSHIP
    assert legal_form_from_number("SL012345") is LegalForm.OTHER_CORPORATE
    assert legal_form_from_number("XX012345") is LegalForm.UNKNOWN


def _provider(**kw):
    return CqcProvider.model_validate({"providerId": "P", "name": "X", **kw})


def test_provider_legal_form():
    assert provider_legal_form(_provider(ownershipType="Organisation", companiesHouseNumber="1234567")) is LegalForm.LIMITED_COMPANY
    assert provider_legal_form(_provider(ownershipType="Organisation", companiesHouseNumber="OC300001")) is LegalForm.LLP
    assert provider_legal_form(_provider(ownershipType="Organisation", charityNumber="123")) is LegalForm.UNKNOWN
    assert provider_legal_form(_provider(ownershipType="Individual", companiesHouseNumber="1234567")) is LegalForm.SOLE_TRADER
    assert provider_legal_form(_provider(ownershipType="Partnership")) is LegalForm.PARTNERSHIP
    assert provider_legal_form(_provider(ownershipType="NHS Body")) is LegalForm.PUBLIC_BODY


def test_normalise_name():
    assert normalise_name("The Example Care & Support Ltd.") == "example care and support"
    assert normalise_name("EXAMPLE CARE AND SUPPORT LIMITED") == "example care and support"
    assert normalise_name(None) == ""


def test_name_similarity():
    assert name_similarity("Midshires Care Limited", "MIDSHIRES CARE LTD") == 1.0
    assert name_similarity("Bright Homecare Ltd", "Bright Home Care Limited") > 0.9
    assert name_similarity("Bright Homecare", "Sunrise Nursing") < 0.6
    assert name_similarity("", "X") == 0.0


def test_name_index_prefers_postcode_and_blocks():
    index = NameIndex(
        [
            Candidate("p1", "Bright Homecare Services", "E1 6AN"),
            Candidate("p2", "Bright Homecare Service", "M1 1AA"),
            Candidate("p3", "Sunrise Nursing", "E1 7AA"),
        ]
    )
    match = index.best("BRIGHT HOMECARE SERVICES LTD", "E1 1AA")
    assert (match.key, match.method, match.score) == ("p1", "name+postcode", 1.0)
    # Lower name score is accepted only with the same district.
    assert index.best("Bright Homecare Svcs", "E1 2AA").key == "p1"  # score 0.91
    assert index.best("Bright Homecare Svcs", "SW1A 1AA") is None
    assert index.best("Completely Different Ltd") is None


def test_postcode_lookup():
    lookup = PostcodeLookup()
    for pc in ("IG1 1AA", "IG1 2BB", "IG2 1AA", "IG3 1AA", "IG4 1AA"):
        lookup.add(pc, "London", "Redbridge")
    lookup.add("IG10 1AA", "East", "Epping Forest")
    assert lookup.lookup("IG1 9ZZ") == ("London", "Redbridge")
    assert lookup.lookup("IG10 3XX") == ("East", "Epping Forest")
    # Unknown district: the IG area is 5/6 London, below the 90% agreement bar.
    assert lookup.lookup("IG11 1AA") == (None, None)
    for pc in ("E1 1AA", "E2 1AA", "E3 1AA", "E4 1AA", "E5 1AA"):
        lookup.add(pc, "London", None)
    assert lookup.lookup("E17 1AA") == ("London", None)
    assert lookup.lookup("M1 1AA") == (None, None)
    assert lookup.lookup(None) == (None, None)
