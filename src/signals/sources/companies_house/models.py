"""Typed view over Companies House advanced-search items. Unknown fields are ignored."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class RegisteredOfficeAddress(BaseModel):
    model_config = ConfigDict(extra="ignore")

    address_line_1: str | None = None
    address_line_2: str | None = None
    locality: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None

    def one_line(self) -> str:
        parts = [self.address_line_1, self.address_line_2, self.locality, self.region]
        return ", ".join(p.strip() for p in parts if p and p.strip())


class ChCompany(BaseModel):
    model_config = ConfigDict(extra="ignore")

    company_number: str
    company_name: str
    company_status: str | None = None
    company_type: str | None = None
    date_of_creation: date | None = None
    sic_codes: list[str] = []
    registered_office_address: RegisteredOfficeAddress | None = None

    @property
    def url(self) -> str:
        return f"https://find-and-update.company-information.service.gov.uk/company/{self.company_number}"
