"""Typed views over the CQC fields the feeds use. Unknown fields are ignored.

Field names follow the CQC API's camelCase; verify against live responses with `signals smoke`.
"""

from __future__ import annotations

import datetime as dt
from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel


class CqcModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class Rating(CqcModel):
    rating: str | None = None
    report_date: date | None = None
    report_link_id: str | None = None

    @field_validator("report_date", mode="before")
    @classmethod
    def _date_only(cls, v: object) -> object:
        return v[:10] if isinstance(v, str) and v else (v or None)


class CurrentRatings(CqcModel):
    overall: Rating | None = None


class HistoricRating(CqcModel):
    report_date: date | None = None
    report_link_id: str | None = None
    overall: Rating | None = None

    @field_validator("report_date", mode="before")
    @classmethod
    def _date_only(cls, v: object) -> object:
        return v[:10] if isinstance(v, str) and v else (v or None)


class Named(CqcModel):
    name: str | None = None
    description: str | None = None
    code: str | None = None


class LastInspection(CqcModel):
    date: dt.date | None = None


class _Addressed(CqcModel):
    name: str
    registration_status: str | None = None
    registration_date: date | None = None
    deregistration_date: date | None = None
    postal_address_line1: str | None = None
    postal_address_line2: str | None = None
    postal_address_town_city: str | None = None
    postal_address_county: str | None = None
    postal_code: str | None = None
    region: str | None = None
    local_authority: str | None = None
    main_phone_number: str | None = None
    website: str | None = None
    inspection_directorate: str | None = None
    regulated_activities: list[Named] = []
    current_ratings: CurrentRatings | None = None
    historic_ratings: list[HistoricRating] = []
    last_inspection: LastInspection | None = None

    @property
    def address(self) -> str:
        parts = [
            self.postal_address_line1,
            self.postal_address_line2,
            self.postal_address_town_city,
            self.postal_address_county,
        ]
        return ", ".join(p.strip() for p in parts if p and p.strip())

    @property
    def overall_rating(self) -> Rating | None:
        overall = self.current_ratings.overall if self.current_ratings else None
        return overall if overall and overall.rating else None


class CqcLocation(_Addressed):
    location_id: str
    provider_id: str | None = None
    type: str | None = None
    care_home: str | None = None
    number_of_beds: int | None = None
    gac_service_types: list[Named] = []

    @property
    def profile_url(self) -> str:
        return f"https://www.cqc.org.uk/location/{self.location_id}"


class CqcProvider(_Addressed):
    provider_id: str
    organisation_type: str | None = None
    ownership_type: str | None = None
    type: str | None = None
    companies_house_number: str | None = None
    charity_number: str | None = None
    location_ids: list[str] = []

    @property
    def profile_url(self) -> str:
        return f"https://www.cqc.org.uk/provider/{self.provider_id}"
