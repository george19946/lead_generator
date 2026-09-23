from datetime import date

from signals.sources.companies_house.models import ChCompany
from signals.sources.cqc.models import CqcLocation, CqcProvider
from signals.sources.cqc.sanitise import sanitise, strip_personal_names
from tests.conftest import load_fixture


def test_strip_personal_names_removes_contacts_everywhere():
    raw = load_fixture("synthetic/cqc_location_rated_ri.json")
    clean = strip_personal_names(raw)
    assert "contacts" not in clean["regulatedActivities"][0]
    assert "Jane" not in str(clean)
    assert "contacts" in raw["regulatedActivities"][0]  # original untouched
    provider = strip_personal_names(load_fixture("synthetic/cqc_provider_limited.json"))
    assert "contacts" not in provider and "John" not in str(provider)


def test_sanitise_can_opt_in_to_names():
    raw = load_fixture("synthetic/cqc_location_rated_ri.json")
    assert sanitise(raw, include_personal_names=True) is raw


def test_location_model_reads_key_fields():
    loc = CqcLocation.model_validate(load_fixture("synthetic/cqc_location_rated_ri.json"))
    assert loc.location_id == "1-900000001"
    assert loc.provider_id == "1-800000001"
    assert loc.registration_date == date(2019, 3, 12)
    assert loc.overall_rating.rating == "Requires improvement"
    assert loc.overall_rating.published == date(2026, 9, 16)
    assert loc.overall_rating.framework == "currentRatings"
    assert loc.historic_ratings[0].overall.rating == "Good"
    assert loc.address == "1 Example Road, London"
    assert loc.profile_url == "https://www.cqc.org.uk/location/1-900000001"


def test_never_inspected_location_has_no_rating():
    loc = CqcLocation.model_validate(load_fixture("synthetic/cqc_location_never_inspected.json"))
    assert loc.overall_rating is None


def test_provider_model():
    prov = CqcProvider.model_validate(load_fixture("synthetic/cqc_provider_limited.json"))
    assert prov.companies_house_number == "01234567"
    assert prov.ownership_type == "Organisation"
    assert prov.website == "www.example-care.test"


def test_ch_company_model():
    item = load_fixture("synthetic/ch_advanced_search.json")["items"][0]
    company = ChCompany.model_validate(item)
    assert company.company_type == "ltd"
    assert company.date_of_creation == date(2026, 9, 15)
    assert company.registered_office_address.postal_code == "IG1 1AA"
    assert company.url.endswith("/company/16000001")


def test_rating_from_single_assessment_framework_when_no_current_ratings():
    loc = CqcLocation.model_validate(load_fixture("synthetic/cqc_location_assessment_only.json"))
    rating = loc.overall_rating
    assert rating.rating == "Inadequate"
    assert rating.framework == "assessment"
    assert rating.published == date(2026, 9, 17)
    assert loc.website == "www.example-lodge.test"


def test_newer_assessment_rating_beats_older_current_ratings():
    raw = load_fixture("synthetic/cqc_location_assessment_only.json")
    older = {**raw, "currentRatings": {"overall": {"rating": "Good", "reportDate": "2022-02-10"}}}
    assert CqcLocation.model_validate(older).overall_rating.rating == "Inadequate"
    newer = {**raw, "currentRatings": {"overall": {"rating": "Good", "reportDate": "2026-09-18"}}}
    rating = CqcLocation.model_validate(newer).overall_rating
    assert (rating.rating, rating.framework) == ("Good", "currentRatings")


def test_normalise_rating_spellings():
    from signals.sources.cqc.models import normalise_rating

    assert normalise_rating("Requires Improvement") == "Requires improvement"
    assert normalise_rating(" inadequate ") == "Inadequate"
    assert normalise_rating("") is None
    assert normalise_rating("Something new") == "Something new"


def test_strip_nominated_individual():
    provider = {
        "providerId": "1-1",
        "regulatedActivities": [
            {"name": "Personal care", "nominatedIndividual": {"personTitle": "Ms", "personGivenName": "Mary", "personFamilyName": "Jones"}}
        ],
    }
    clean = strip_personal_names(provider)
    assert clean["regulatedActivities"] == [{"name": "Personal care"}]
