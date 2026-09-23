import plistlib
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from signals.cli import app
from signals.output.writers import purge_outputs
from signals.schedule import cron_line, launchd_plist, protected_folder

runner = CliRunner()
PROJECT = Path("/Users/sam/lead generator")


def test_launchd_plist():
    plist = plistlib.loads(launchd_plist(PROJECT, "/Users/sam/.local/bin/uv", "monday", 7, 30))
    assert plist["Label"] == "com.signals.weekly"
    assert plist["StartCalendarInterval"] == {"Weekday": 1, "Hour": 7, "Minute": 30}
    command = plist["ProgramArguments"][2]
    assert command == ("cd '/Users/sam/lead generator' && /Users/sam/.local/bin/uv run signals run"
                       " && /Users/sam/.local/bin/uv run signals purge")
    assert plist["StandardOutPath"] == "/Users/sam/lead generator/logs/weekly.log"


def test_cron_line():
    line = cron_line(Path("/srv/signals"), "/usr/local/bin/uv", "sunday", 6, 0)
    assert line.startswith("0 6 * * 0 (cd /srv/signals && /usr/local/bin/uv run signals run")
    assert line.endswith(">> /srv/signals/logs/weekly.log 2>&1")


def test_protected_folder():
    home = Path("/Users/sam")
    assert protected_folder(home / "Downloads" / "lead_generator", home) == "Downloads"
    assert protected_folder(home / "Library" / "Mobile Documents" / "x", home) == "Library/Mobile Documents"
    assert protected_folder(home / "lead_generator", home) is None


def _project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "config").mkdir()


def test_schedule_command_on_a_mac(tmp_path, monkeypatch):
    _project(tmp_path)
    home = tmp_path / "home"
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("UV", "/opt/uv")
    result = runner.invoke(app, ["schedule", "--day", "Tuesday", "--hour", "8"])
    assert result.exit_code == 0, result.output
    path = home / "Library" / "LaunchAgents" / "com.signals.weekly.plist"
    assert plistlib.loads(path.read_bytes())["StartCalendarInterval"]["Weekday"] == 2
    assert "launchctl load -w" in result.output and (tmp_path / "logs").is_dir()


def test_schedule_refuses_protected_folder(tmp_path, monkeypatch):
    project = tmp_path / "Downloads" / "lead_generator"
    project.mkdir(parents=True)
    _project(project)
    monkeypatch.chdir(project)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("UV", "/opt/uv")
    result = runner.invoke(app, ["schedule"])
    assert result.exit_code == 1 and "Downloads" in result.output
    assert not (tmp_path / "Library").exists()


def test_schedule_elsewhere_prints_cron(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setenv("UV", "/opt/uv")
    result = runner.invoke(app, ["schedule"])
    assert result.exit_code == 0 and "0 7 * * 1 (cd" in result.output


def test_schedule_needs_project_folder(tmp_path):
    assert runner.invoke(app, ["schedule"]).exit_code == 2


def test_purge_outputs(tmp_path):
    for folder in ("care/2025-01-05/london", "care/2026-09-20/london", "samples/care/london_2024-12-01_to_2025-01-05",
                   "samples/care/london_2026-08-24_to_2026-09-20", "care/notes"):
        (tmp_path / folder).mkdir(parents=True)
    assert purge_outputs(tmp_path, date(2025, 9, 1)) == 2
    remaining = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.glob("**/*") if p.is_dir())
    assert remaining == ["care", "care/2026-09-20", "care/2026-09-20/london", "care/notes", "samples", "samples/care",
                         "samples/care/london_2026-08-24_to_2026-09-20"]
    assert purge_outputs(tmp_path / "missing", date(2025, 9, 1)) == 0


def test_suppress_command(tmp_path):
    (tmp_path / "signals.yaml").write_text("database: data/t.db\n")
    cfg = ["--config", str(tmp_path / "signals.yaml")]
    result = runner.invoke(app, ["suppress", "1-101", "--note", "asked by email", *cfg])
    assert result.exit_code == 0 and "1-101 is now opted out" in result.output
    listing = runner.invoke(app, ["suppress", *cfg]).output
    assert "1 on the opt-out list" in listing and "asked by email" in listing
    assert "removed" in runner.invoke(app, ["suppress", "1-101", "--remove", *cfg]).output
    assert "0 on the opt-out list" in runner.invoke(app, ["suppress", *cfg]).output
