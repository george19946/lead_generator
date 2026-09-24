"""Configuration: secrets from keys.env (or the environment), everything else from YAML.

Everything that belongs to the user lives in the **data home**, `~/Signals` (or $SIGNALS_HOME), kept apart from
the code so that replacing the code folder with a new version can never touch it:

    ~/Signals/keys.env        API keys
    ~/Signals/signals.yaml    config, including customer regions (copied from config/signals.yaml by `setup`)
    ~/Signals/data/           the database
    ~/Signals/outputs/        digests and CSVs
    ~/Signals/logs/           scheduled-run logs

Relative paths in the config are relative to the data home. A `.env` in the current folder is still read
(for development); keys.env wins over it, and real environment variables win over both.
"""

from __future__ import annotations

import os
import re
from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONFIG_PATH = Path("config/signals.yaml")  # the template in the code folder
KEYS_FILE = "keys.env"
CONFIG_FILE = "signals.yaml"
KEY_NAMES = ("CQC_API_KEY", "COMPANIES_HOUSE_API_KEY")


def data_home() -> Path:
    return Path(os.environ.get("SIGNALS_HOME") or Path.home() / "Signals").expanduser()


def keys_path() -> Path:
    return data_home() / KEYS_FILE


class Secrets(BaseSettings):
    """API keys. Real environment variables win, then keys.env in the data home, then a local .env."""

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

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
    # Also list new companies whose location is unknown (formation-agent addresses) in this region's digest.
    location_unknown: bool = True

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


class BusinessConfig(BaseModel):
    """Your business details for the website and sales material (~/Signals/business.yaml)."""

    brand: str = "Care Signals"
    tagline: str = "Weekly CQC leads for care compliance consultancies"
    legal_name: str = ""
    company_number: str = ""
    address: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    ico_registration: str = ""
    price_per_region: float | None = 149
    price_note: str = "per region, per month, excluding VAT. Cancel any time."
    trial: str = ""
    showcase_region: str | None = None

    def missing(self) -> list[str]:
        """Fields the privacy notice legally needs that are still empty."""
        return [name for name in ("legal_name", "address", "email") if not getattr(self, name).strip()]


BUSINESS_FILE = "business.yaml"
DEFAULT_BUSINESS_PATH = Path("config/business.yaml")


def load_business() -> BusinessConfig:
    """~/Signals/business.yaml, else the template in the code folder, else defaults."""
    for path in (data_home() / BUSINESS_FILE, DEFAULT_BUSINESS_PATH):
        if path.exists():
            return BusinessConfig.model_validate(yaml.safe_load(path.read_text()) or {})
    return BusinessConfig()


class Settings:
    """Bundles the YAML config with the secrets."""

    def __init__(self, config: AppConfig, secrets: Secrets):
        self.config = config
        self.secrets = secrets
        self.config_path: Path | None = None

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        home = data_home()
        path = config_path or config_file()
        data = yaml.safe_load(path.read_text()) if path.exists() else {}
        config = AppConfig.model_validate(data or {})
        config.database = home / config.database  # an absolute path stays as it is
        config.outputs_dir = home / config.outputs_dir
        # Later files win: the data home's keys.env over a local .env.
        secrets = Secrets(_env_file=(Path(".env"), home / KEYS_FILE))
        settings = cls(config, secrets)
        settings.config_path = path
        return settings

    @cached_property
    def cqc_api_key(self) -> str:
        return _require(self.secrets.cqc_api_key, "CQC_API_KEY")

    @cached_property
    def companies_house_api_key(self) -> str:
        return _require(self.secrets.companies_house_api_key, "COMPANIES_HOUSE_API_KEY")


def config_file() -> Path:
    """$SIGNALS_CONFIG, else the data home's signals.yaml, else the template in the code folder."""
    if os.environ.get("SIGNALS_CONFIG"):
        return Path(os.environ["SIGNALS_CONFIG"])
    home_config = data_home() / CONFIG_FILE
    return home_config if home_config.exists() else DEFAULT_CONFIG_PATH


def write_keys(values: dict[str, str]) -> Path:
    """Write keys.env (readable only by the user), keeping any other lines already in it."""
    path = keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = []
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            name = line.split("=", 1)[0].strip()
            if name not in values:
                kept.append(line)
    lines = kept + [f"{name}={value}" for name, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


class MissingSecretError(RuntimeError):
    pass


def _require(value: SecretStr | None, name: str) -> str:
    if value is None or not value.get_secret_value().strip():
        raise MissingSecretError(_missing_message(name))
    return value.get_secret_value().strip()


def _missing_message(name: str) -> str:
    """Say where keys were looked for and what was wrong. Never prints a key."""
    path = keys_path()
    if not path.exists():
        hint = f"There is no keys file yet ({path})."
    else:
        lines = [line.strip() for line in path.read_text(errors="replace").splitlines()]
        lines = [line for line in lines if line and not line.startswith("#")]
        # Show variable names only: a line without NAME= may be a bare key, which must never be printed.
        names = [line.split("=", 1)[0].strip() for line in lines if re.fullmatch(r"[A-Za-z_]\w*\s*=.*", line)]
        other = len(lines) - len(names)
        found = ", ".join(names) or "no NAME=value lines"
        if other:
            found += f", plus {other} line(s) without NAME= (not shown)"
        hint = f"{path} has no {name} (it has: {found})."
    return f"{name} is not set. {hint}\nAdd your keys with:  uv run signals keys"
