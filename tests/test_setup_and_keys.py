import sqlite3

from typer.testing import CliRunner

from signals.cli import app
from signals.settings import Settings

runner = CliRunner()


def _code_folder(root):
    """A code folder as an older version left it: data, outputs, logs and .env inside it."""
    (root / "config").mkdir(parents=True)
    (root / "config" / "signals.yaml").write_text("regions:\n  london:\n    cqc_region: London\n")
    (root / "data").mkdir()
    sqlite3.connect(root / "data" / "signals.db").close()
    (root / "outputs" / "care").mkdir(parents=True)
    (root / ".env").write_text("CQC_API_KEY=cqc-key\nCOMPANIES_HOUSE_API_KEY=ch-key\n")


def test_setup_moves_an_old_layout_into_the_data_home(tmp_path, monkeypatch):
    code, home = tmp_path / "code", tmp_path / "Signals"
    _code_folder(code)
    monkeypatch.chdir(code)
    monkeypatch.setenv("SIGNALS_HOME", str(home))

    result = runner.invoke(app, ["setup"])

    assert result.exit_code == 0, result.output
    assert (home / "data" / "signals.db").exists() and not (code / "data").exists()
    assert (home / "outputs" / "care").is_dir()
    assert (home / "signals.yaml").exists() and (code / "config" / "signals.yaml").exists()
    assert (home / "keys.env").stat().st_mode & 0o777 == 0o600
    settings = Settings.load()
    assert settings.cqc_api_key == "cqc-key" and settings.config.database == home / "data" / "signals.db"
    assert "Paste each key" not in result.output  # nothing missing, so no questions
    # Safe to re-run.
    assert runner.invoke(app, ["setup"]).exit_code == 0


def test_setup_leaves_data_alone_when_both_exist(tmp_path, monkeypatch):
    code, home = tmp_path / "code", tmp_path / "Signals"
    _code_folder(code)
    (home / "data").mkdir(parents=True)
    (home / "data" / "signals.db").write_text("newer")
    monkeypatch.chdir(code)
    monkeypatch.setenv("SIGNALS_HOME", str(home))
    result = runner.invoke(app, ["setup"])
    assert "left" in result.output and (code / "data" / "signals.db").exists()
    assert (home / "data" / "signals.db").read_text() == "newer"


def test_setup_asks_for_missing_keys(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "signals.yaml").write_text("{}\n")
    result = runner.invoke(app, ["setup"], input="bad key\ncqc-123\nch-456\n")
    assert result.exit_code == 0, result.output
    assert "doesn't look like a key" in result.output
    assert "cqc-123" not in result.output and "ch-456" not in result.output
    assert (tmp_path / "keys.env").read_text() == "CQC_API_KEY=cqc-123\nCOMPANIES_HOUSE_API_KEY=ch-456\n"


def test_keys_command_keeps_saved_keys_on_enter(tmp_path):
    (tmp_path / "keys.env").write_text("CQC_API_KEY=old-cqc\nCOMPANIES_HOUSE_API_KEY=old-ch\n")
    result = runner.invoke(app, ["keys"], input="\nnew-ch\n")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "keys.env").read_text() == "CQC_API_KEY=old-cqc\nCOMPANIES_HOUSE_API_KEY=new-ch\n"
