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


def test_missing_key_message_says_where_and_what(tmp_path):
    with pytest.raises(MissingSecretError, match="There is no keys file yet") as exc:
        _ = Settings.load(tmp_path / "none.yaml").cqc_api_key
    assert str(tmp_path / "keys.env") in str(exc.value) and "uv run signals keys" in str(exc.value)
    # A keys file holding a bare key (no NAME=) is the other common mistake. Keys must never be echoed back.
    (tmp_path / "keys.env").write_text("abc123secret\nCOMPANIES_HOUSE_API_KEY=x\n")
    with pytest.raises(MissingSecretError, match="has no CQC_API_KEY") as exc:
        _ = Settings.load(tmp_path / "none.yaml").cqc_api_key
    assert "COMPANIES_HOUSE_API_KEY" in str(exc.value) and "1 line(s) without NAME=" in str(exc.value)
    assert "abc123secret" not in str(exc.value)


def test_keys_file_in_data_home_beats_local_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("SIGNALS_HOME", str(home))
    (tmp_path / ".env").write_text("CQC_API_KEY=local\nCOMPANIES_HOUSE_API_KEY=local-ch\n")
    (home / "keys.env").write_text("CQC_API_KEY=home\n")
    settings = Settings.load(REPO_CONFIG)
    assert settings.cqc_api_key == "home"
    assert settings.companies_house_api_key == "local-ch"


def test_paths_are_under_the_data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALS_HOME", str(tmp_path / "h"))
    settings = Settings.load(REPO_CONFIG)
    assert settings.config.database == tmp_path / "h" / "data" / "signals.db"
    assert settings.config.outputs_dir == tmp_path / "h" / "outputs"
    cfg = tmp_path / "abs.yaml"
    cfg.write_text(f"database: {tmp_path / 'elsewhere.db'}\n")
    assert Settings.load(cfg).config.database == tmp_path / "elsewhere.db"


def test_config_in_data_home_is_preferred(tmp_path, monkeypatch):
    from signals.settings import config_file

    monkeypatch.setenv("SIGNALS_HOME", str(tmp_path))
    assert config_file() == Path("config/signals.yaml")
    (tmp_path / "signals.yaml").write_text("regions:\n  kent:\n    local_authorities: [Kent]\n")
    assert config_file() == tmp_path / "signals.yaml"
    assert list(Settings.load().config.regions) == ["kent"]


def test_write_keys_keeps_other_lines_and_is_private(tmp_path):
    from signals.settings import write_keys

    (tmp_path / "keys.env").write_text("# my keys\nCQC_API_KEY=old\n")
    path = write_keys({"CQC_API_KEY": "new", "COMPANIES_HOUSE_API_KEY": "ch"})
    assert path.read_text() == "# my keys\nCQC_API_KEY=new\nCOMPANIES_HOUSE_API_KEY=ch\n"
    assert path.stat().st_mode & 0o777 == 0o600
