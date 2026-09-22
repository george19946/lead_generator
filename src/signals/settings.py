"""Configuration: secrets from the environment / .env, everything else from YAML."""

from __future__ import annotations

import os
from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONFIG_PATH = Path("config/signals.yaml")


class Secrets(BaseSettings):
    """API keys. Real environment variables take precedence over .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cqc_api_key: SecretStr | None = None
    companies_house_api_key: SecretStr | None = None


class SourceConfig(BaseModel):
    base_url: str
    max_requests: int = Field(gt=0)
    per_seconds: float = Field(gt=0)


class SourcesConfig(BaseModel):
    cqc: SourceConfig = SourceConfig(
        base_url="https://api.service.cqc.org.uk/public/v1", max_requests=10, per_seconds=1
    )
    companies_house: SourceConfig = SourceConfig(
        base_url="https://api.company-information.service.gov.uk", max_requests=550, per_seconds=300
    )


class RegionConfig(BaseModel):
    cqc_region: str | None = None
    local_authorities: list[str] = []
    postcode_areas: list[str] = []

    @model_validator(mode="after")
    def _at_least_one_criterion(self) -> RegionConfig:
        if not (self.cqc_region or self.local_authorities or self.postcode_areas):
            raise ValueError("a region needs cqc_region, local_authorities or postcode_areas")
        return self


class AppConfig(BaseModel):
    database: Path = Path("data/signals.db")
    outputs_dir: Path = Path("outputs")
    retention_days: int = Field(default=365, gt=0)
    include_personal_names: bool = False
    sources: SourcesConfig = SourcesConfig()
    regions: dict[str, RegionConfig] = {}


class Settings:
    """Bundles the YAML config with the secrets."""

    def __init__(self, config: AppConfig, secrets: Secrets):
        self.config = config
        self.secrets = secrets

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        path = config_path or Path(os.environ.get("SIGNALS_CONFIG", DEFAULT_CONFIG_PATH))
        data = yaml.safe_load(path.read_text()) if path.exists() else {}
        return cls(AppConfig.model_validate(data or {}), Secrets())

    @cached_property
    def cqc_api_key(self) -> str:
        return _require(self.secrets.cqc_api_key, "CQC_API_KEY")

    @cached_property
    def companies_house_api_key(self) -> str:
        return _require(self.secrets.companies_house_api_key, "COMPANIES_HOUSE_API_KEY")


class MissingSecretError(RuntimeError):
    pass


def _require(value: SecretStr | None, name: str) -> str:
    if value is None or not value.get_secret_value().strip():
        raise MissingSecretError(f"{name} is not set. Add it to .env (see .env.example) or the environment.")
    return value.get_secret_value().strip()
