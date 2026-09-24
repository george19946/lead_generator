from pathlib import Path

import pytest

from signals.settings import MissingSecretError, Settings

REPO_CONFIG = Path(__file__).parent.parent / "config" / "signals.yaml"


def test_repo_config_loads():
    settings = Settings.load(REPO_CONFIG)
    assert settings.config.include_personal_names is False
    assert settings.config.retention_days == 365
    assert settings.config.regions["london"].cqc_region == "London"
    assert settings.config.regions["east-london"].postcode_areas == ["E", "IG", "RM"]


def test_keys_read_from_dotenv(tmp_path):
    (tmp_path / ".env").write_text("CQC_API_KEY=abc\nCOMPANIES_HOUSE_API_KEY=def\n")
    settings = Settings.load(REPO_CONFIG)
    assert settings.cqc_api_key == "abc"
    assert settings.companies_house_api_key == "def"


def test_env_var_beats_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("CQC_API_KEY=from-file\n")
    monkeypatch.setenv("CQC_API_KEY", "from-env")
    assert Settings.load(REPO_CONFIG).cqc_api_key == "from-env"


def test_missing_key_is_a_clear_error():
    with pytest.raises(MissingSecretError, match="CQC_API_KEY"):
        _ = Settings.load(REPO_CONFIG).cqc_api_key


def test_region_needs_a_criterion(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("regions:\n  empty: {}\n")
    with pytest.raises(ValueError):
        Settings.load(cfg)


def test_missing_key_message_names_the_folder_and_problem(tmp_path):
    with pytest.raises(MissingSecretError, match="There is no .env file in") as exc:
        Settings.load(tmp_path / "none.yaml").cqc_api_key
    assert str(tmp_path) in str(exc.value)
    # A .env holding bare keys (no NAME=) is the other common mistake. Keys must never be echoed back.
    (tmp_path / ".env").write_text("abc123secret\nCOMPANIES_HOUSE_API_KEY=x\n")
    with pytest.raises(MissingSecretError, match="has no line starting CQC_API_KEY=") as exc:
        Settings.load(tmp_path / "none.yaml").cqc_api_key
    assert "COMPANIES_HOUSE_API_KEY" in str(exc.value) and "1 line(s) without NAME=" in str(exc.value)
    assert "abc123secret" not in str(exc.value)
