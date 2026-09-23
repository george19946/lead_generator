"""Run the weekly job automatically: a macOS launchd agent, or a cron line elsewhere.

The job changes into the project folder (so `.env` and `config/` are found), runs `signals run` (sync,
record the week's leads, write the digests) and then `signals purge` (retention), logging to logs/weekly.log.
launchd runs a job missed while the Mac was asleep as soon as it wakes; a job missed while it was switched
off is skipped until the next week.
"""

from __future__ import annotations

import os
import plistlib
import shlex
import shutil
from pathlib import Path

LABEL = "com.signals.weekly"
DAYS = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")  # launchd: Sunday = 0
# macOS privacy protection stops background jobs reading these folders without extra permissions.
PROTECTED = ("Desktop", "Documents", "Downloads", "Library/Mobile Documents")


def find_uv() -> str | None:
    """The uv executable: `uv run` sets $UV; otherwise look on PATH."""
    return os.environ.get("UV") or shutil.which("uv")


def job_command(project: Path, uv: str) -> str:
    q_uv = shlex.quote(uv)
    return f"cd {shlex.quote(str(project))} && {q_uv} run signals run && {q_uv} run signals purge"


def launchd_plist(project: Path, uv: str, day: str, hour: int, minute: int) -> bytes:
    log = str(project / "logs" / "weekly.log")
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": ["/bin/zsh", "-lc", job_command(project, uv)],
            "StartCalendarInterval": {"Weekday": DAYS.index(day), "Hour": hour, "Minute": minute},
            "StandardOutPath": log,
            "StandardErrorPath": log,
            "RunAtLoad": False,
        }
    )


def cron_line(project: Path, uv: str, day: str, hour: int, minute: int) -> str:
    log = shlex.quote(str(project / "logs" / "weekly.log"))
    return f"{minute} {hour} * * {DAYS.index(day)} ({job_command(project, uv)}) >> {log} 2>&1"


def plist_path(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def protected_folder(project: Path, home: Path) -> str | None:
    """The protected folder the project sits in (e.g. Downloads), if any."""
    for name in PROTECTED:
        folder = home / name
        if project == folder or folder in project.parents:
            return name
    return None
