"""`signals` command-line interface."""

from __future__ import annotations

import logging
import re
import shlex
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from signals.settings import MissingSecretError, Settings

if TYPE_CHECKING:
    from signals.core.runner import FeedResult
    from signals.db.store import Store
    from signals.sources.companies_house.source import CompaniesHouseSource
    from signals.sources.cqc.source import CqcSource
    from signals.verticals.care.collect import CollectStats

app = typer.Typer(help="Signals engine: weekly lead feeds from UK public registers.", no_args_is_help=True)

ConfigOption = Annotated[
    Path | None, typer.Option("--config", "-c", help="YAML config (default: config/signals.yaml or $SIGNALS_CONFIG)")
]


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def smoke(
    n: Annotated[int, typer.Option(help="Records to fetch from each API")] = 5,
    save_fixtures: Annotated[
        bool, typer.Option(help="Write sanitised responses to tests/fixtures/")
    ] = False,
    config: ConfigOption = None,
) -> None:
    """Live smoke test against the CQC and Companies House APIs."""
    from signals.smoke import run_smoke
    from signals.sources.companies_house.client import CompaniesHouseClient
    from signals.sources.cqc.client import CqcClient

    settings = Settings.load(config)
    try:
        cqc = CqcClient.from_settings(settings)
        ch = CompaniesHouseClient.from_settings(settings)
    except MissingSecretError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(2) from exc

    try:
        report = run_smoke(cqc, ch, n=n, fixtures_dir=Path("tests/fixtures") if save_fixtures else None)
    finally:
        cqc.close()
        ch.close()

    for line in report.lines:
        typer.echo(line)
    if report.problems:
        typer.secho(f"\n{len(report.problems)} problem(s):", fg="yellow")
        for line in report.problems:
            typer.secho(f"  - {line}", fg="yellow")
        raise typer.Exit(1)
    typer.secho("\nSmoke test OK", fg="green")


def _open_store(settings: Settings) -> Store:
    from signals.db.store import Store

    return Store.open(settings.config.database)


def _make_sources(settings: Settings) -> tuple[CqcSource, CompaniesHouseSource]:
    """Build both sources, exiting with a clear message if a key is missing."""
    from signals.sources.companies_house.client import CompaniesHouseClient
    from signals.sources.companies_house.source import CompaniesHouseSource
    from signals.sources.cqc.client import CqcClient
    from signals.sources.cqc.source import CqcSource
    from signals.verticals.care import CARE_SIC_CODES

    try:
        cqc = CqcClient.from_settings(settings)
        ch = CompaniesHouseClient.from_settings(settings)
    except MissingSecretError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(2) from exc
    return (
        CqcSource(cqc, include_personal_names=settings.config.include_personal_names),
        CompaniesHouseSource(ch, CARE_SIC_CODES),
    )


def _echo_counts(store: Store) -> None:
    typer.echo("Database now holds: " + ", ".join(f"{k} {v:,}" for k, v in store.counts().items()))


KEY_HELP = {
    "CQC_API_KEY": "CQC API key (api-portal.service.cqc.org.uk, Profile, primary key)",
    "COMPANIES_HOUSE_API_KEY": "Companies House API key (developer.company-information.service.gov.uk, "
                               "Your applications, Live, REST key)",
}


def _stored_keys() -> dict[str, str]:
    from signals.settings import keys_path

    path = keys_path()
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(errors="replace").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            if value.strip():
                out[name.strip()] = value.strip()
    return out


def _ask_keys(names: tuple[str, ...]) -> None:
    from signals.settings import write_keys

    stored = _stored_keys()
    typer.echo("Paste each key and press Enter. Nothing appears on screen while you paste: that's normal.")
    values = {}
    for name in names:
        keep = " (press Enter to keep the one saved)" if name in stored else ""
        while True:
            value = typer.prompt(f"{KEY_HELP.get(name, name)}{keep}", default="", show_default=False,
                                 hide_input=True).strip()
            if not value and name in stored:
                value = stored[name]
            if value and not re.search(r"[\s=\"']", value):
                break
            typer.secho("That doesn't look like a key (it's empty or has spaces or quotes). Please paste it again.",
                        fg="yellow")
        values[name] = value
    path = write_keys(values)
    typer.secho(f"Saved to {path} (only you can read it).", fg="green")


@app.command()
def keys() -> None:
    """Save your API keys in ~/Signals/keys.env. Asks for each one; press Enter to keep a saved key."""
    from signals.settings import KEY_NAMES

    _ask_keys(KEY_NAMES)
    typer.echo("Check they work with:  uv run signals smoke --n 5")


@app.command()
def setup(
    ask_keys: Annotated[bool, typer.Option("--keys/--no-keys", help="Ask for any missing API keys")] = True,
) -> None:
    """First-time setup, safe to re-run. Run it from the code folder.

    Creates your Signals folder (~/Signals), which holds everything that is yours: keys, config (regions),
    database, digests and logs. Updating the code never touches it. Also moves these over from this folder if
    an older version kept them here, and asks for any missing API key.
    """
    import shutil

    from signals.settings import (
        BUSINESS_FILE,
        CONFIG_FILE,
        DEFAULT_BUSINESS_PATH,
        DEFAULT_CONFIG_PATH,
        KEY_NAMES,
        data_home,
        keys_path,
    )

    home = data_home()
    project = Path.cwd()
    home.mkdir(parents=True, exist_ok=True)
    done = []
    for name, template in ((CONFIG_FILE, DEFAULT_CONFIG_PATH), (BUSINESS_FILE, DEFAULT_BUSINESS_PATH)):
        if not (home / name).exists() and (project / template).exists():
            shutil.copy2(project / template, home / name)
            done.append(f"copied {template.name} to {home / name}")
    if not keys_path().exists() and (project / ".env").exists():
        shutil.copy2(project / ".env", keys_path())
        keys_path().chmod(0o600)
        done.append(f"copied your keys from {project / '.env'} to {keys_path()}")
    for name in ("data", "outputs", "logs"):
        old, new = project / name, home / name
        if old.resolve() == new.resolve() or not old.is_dir() or not any(old.iterdir()):
            continue
        if new.exists() and any(new.iterdir()):
            typer.secho(f"Both {old} and {new} exist: left {old} where it is. Keep whichever is newer.", fg="yellow")
            continue
        if new.exists():
            new.rmdir()
        shutil.move(str(old), str(new))
        done.append(f"moved {old} to {new}")
    typer.secho(f"Your Signals folder: {home}", fg="green", bold=True)
    for line in done:
        typer.echo(f"  - {line}")
    missing = tuple(name for name in KEY_NAMES if name not in _stored_keys())
    if missing and ask_keys:
        _ask_keys(missing)
    elif missing:
        typer.echo("Next, add your API keys:  uv run signals keys")
    typer.echo(
        "\nEverything that is yours now lives in that folder. To update the code later, delete the code folder and "
        "unzip the new version in its place: your data stays put."
    )


@app.command()
def init(config: ConfigOption = None) -> None:
    """Create the SQLite database (safe to re-run)."""
    settings = Settings.load(config)
    with _open_store(settings) as store:
        typer.echo(f"Database ready at {settings.config.database}")
        _echo_counts(store)


@app.command()
def backfill(
    days: Annotated[int, typer.Option(min=1, help="Days of Companies House incorporations to fetch")] = 90,
    dry_run: Annotated[bool, typer.Option(help="Only list the scope and print the estimate")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Don't ask for confirmation")] = False,
    all_england: Annotated[bool, typer.Option(help="Ignore customer regions and fetch all of England")] = False,
    fresh_hours: Annotated[float, typer.Option(help="Skip records fetched this recently (resume)")] = 24,
    only_new: Annotated[
        bool, typer.Option(help="Skip everything already stored: use after adding or widening a region")
    ] = False,
    config: ConfigOption = None,
) -> None:
    """Build the baseline: in-scope CQC locations and providers, plus recent care incorporations.

    Makes a few list calls first and prints an estimate of the API calls and duration before fetching.
    Re-running resumes: records fetched within --fresh-hours are skipped.
    """
    from signals.core.clock import utcnow
    from signals.verticals.care.collect import CareScope, plan_backfill, run_backfill

    settings = Settings.load(config)
    cqc, ch = _make_sources(settings)
    scope = CareScope(settings.config.regions, all_england=all_england)
    regions = "all of England" if scope.all_england else ", ".join(scope.regions)
    try:
        with _open_store(settings) as store:
            typer.echo(f"Listing in-scope CQC locations (regions: {regions})...")
            plan = plan_backfill(cqc, store, scope, days=days, now=utcnow(), fresh_hours=fresh_hours,
                                 only_new=only_new)
            for line in plan.describe():
                typer.echo(line)
            if dry_run:
                return
            if not yes:
                typer.confirm("Start the backfill?", abort=True)
            stats = run_backfill(plan, cqc, ch, store, fresh_hours=fresh_hours, progress=typer.echo)
            _report(stats, cqc, ch)
            _echo_counts(store)
    finally:
        cqc.client.close()
        ch.client.close()
    if stats.failures:
        raise typer.Exit(1)


@app.command()
def sync(config: ConfigOption = None) -> None:
    """Fetch everything that changed since the last backfill or sync."""
    from signals.core.clock import utcnow
    from signals.verticals.care.collect import CareScope, NotBackfilledError, run_sync

    settings = Settings.load(config)
    cqc, ch = _make_sources(settings)
    try:
        with _open_store(settings) as store:
            try:
                stats = run_sync(cqc, ch, store, CareScope(settings.config.regions), now=utcnow(), progress=typer.echo)
            except NotBackfilledError as exc:
                typer.secho(str(exc), fg="red", err=True)
                raise typer.Exit(2) from exc
            _report(stats, cqc, ch)
            _echo_counts(store)
    finally:
        cqc.client.close()
        ch.client.close()
    if stats.failures:
        raise typer.Exit(1)


def _report(stats: CollectStats, cqc: CqcSource, ch: CompaniesHouseSource) -> None:
    typer.echo("Results: " + ", ".join(f"{k} {v:,}" for k, v in sorted(stats.counts.items())))
    typer.echo(f"Requests made: CQC={cqc.client.request_count:,}, Companies House={ch.client.request_count:,}")
    if stats.failures:
        typer.secho(f"{len(stats.failures)} failure(s); re-run to retry them:", fg="yellow")
        for line in stats.failures[:20]:
            typer.secho(f"  - {line}", fg="yellow")


VERTICALS = ("care",)


@app.command()
def run(
    vertical: Annotated[str, typer.Option(help="Vertical to run")] = "care",
    week_ending: Annotated[
        datetime | None,
        typer.Option(formats=["%Y-%m-%d"], help="Last day of the digest week (default: the most recent Sunday)"),
    ] = None,
    weeks: Annotated[
        int, typer.Option(min=1, max=52, help="How many weeks to run, ending with --week-ending (oldest first)")
    ] = 1,
    do_sync: Annotated[bool, typer.Option("--sync/--no-sync", help="Fetch changes before evaluating")] = True,
    output: Annotated[bool, typer.Option("--output/--no-output", help="Write the digest and CSV files")] = True,
    examples: Annotated[int, typer.Option(min=0, help="Example leads to print per feed")] = 3,
    config: ConfigOption = None,
) -> None:
    """Record each week's new leads and write a digest per region (fetches changes first by default)."""
    from signals.core.clock import utcnow
    from signals.core.runner import run_week
    from signals.verticals.care.collect import CareScope, NotBackfilledError, run_sync
    from signals.verticals.care.digest import write_week
    from signals.verticals.care.feeds import CareVertical

    _check_vertical(vertical)
    settings = Settings.load(config)
    scope = CareScope(settings.config.regions)
    run_weeks = _weeks(week_ending, weeks)

    with _open_store(settings) as store:
        if do_sync:
            cqc, ch = _make_sources(settings)
            try:
                stats = run_sync(cqc, ch, store, scope, now=utcnow(), progress=typer.echo)
            except NotBackfilledError as exc:
                typer.secho(str(exc), fg="red", err=True)
                raise typer.Exit(2) from exc
            finally:
                cqc.client.close()
                ch.client.close()
            _report(stats, cqc, ch)
            if stats.failures:
                typer.secho("Sync incomplete; evaluating with the data fetched so far.", fg="yellow")
        for week in run_weeks:
            care = CareVertical(store, scope)
            results = run_week(care, store, week, now=utcnow())
            _print_week(week, results, examples)
            if output:
                paths = write_week(store, care, week, settings.config.regions, settings.config.outputs_dir)
                for path in paths:
                    typer.secho(f"  Digest: {path}", fg="green")


def _check_vertical(vertical: str) -> None:
    if vertical not in VERTICALS:
        raise typer.BadParameter(f"unknown vertical {vertical!r}; choose from {', '.join(VERTICALS)}")


def _weeks(week_ending: datetime | None, count: int) -> list:
    from signals.core.clock import utcnow
    from signals.core.feed import Week

    last = Week(week_ending.date()) if week_ending else Week.last_completed(utcnow().date())
    weeks = [last]
    while len(weeks) < count:
        weeks.insert(0, weeks[0].previous())
    return weeks


@app.command()
def sample(
    region: Annotated[str, typer.Option(help="Region key from config/signals.yaml, e.g. london")],
    vertical: Annotated[str, typer.Option(help="Vertical")] = "care",
    week_ending: Annotated[
        datetime | None,
        typer.Option(formats=["%Y-%m-%d"], help="Last day of the period (default: the most recent Sunday)"),
    ] = None,
    weeks: Annotated[int, typer.Option(min=1, max=52, help="Length of the period in weeks")] = 4,
    config: ConfigOption = None,
) -> None:
    """Write a sample digest for one region from the stored data. Fetches nothing and records nothing."""
    from signals.verticals.care.collect import CareScope
    from signals.verticals.care.digest import write_sample
    from signals.verticals.care.feeds import ALL_ENGLAND, CareVertical

    _check_vertical(vertical)
    settings = Settings.load(config)
    regions = settings.config.regions
    if region not in regions and not (region == ALL_ENGLAND and not regions):
        known = ", ".join(regions) or ALL_ENGLAND
        raise typer.BadParameter(f"unknown region {region!r}; configured regions: {known}")
    with _open_store(settings) as store:
        care = CareVertical(store, CareScope(regions))
        path = write_sample(care, _weeks(week_ending, weeks), region, regions.get(region),
                            settings.config.outputs_dir)
    typer.secho(f"Sample digest: {path}", fg="green")


QUALIFYING = {
    "new_companies": "care companies with a local registered office in the database",
    "location_unknown": "at formation-agent addresses in the database",
    "company_located": "formation-agent companies located so far",
    "never_inspected": "never inspected in total",
    "poor_ratings": "currently rated Requires improvement or Inadequate",
    "due_for_inspection": "due for inspection in total (rating 4+ years old, or a year unrated)",
}


def _print_week(week, results: dict[str, FeedResult], examples: int) -> None:
    typer.secho(f"\nWeek {week.start:%a %d %b} to {week.ending:%a %d %b %Y}", bold=True)
    for name, result in results.items():
        per_region = Counter(r for lead in result.leads for r in lead.regions)
        regions = ", ".join(f"{k} {v}" for k, v in sorted(per_region.items())) or "none"
        typer.echo(
            f"  {name}: {len(result.leads)} leads this week ({regions}); "
            f"{result.qualifying:,} {QUALIFYING.get(name, 'qualifying')}"
        )
        for lead in result.leads[:examples]:
            typer.echo(f"      - {_describe(name, lead.data)}")


def _describe(feed: str, d: dict) -> str:
    if feed == "company_located":
        return (
            f"{d['company_name']} ({d['company_number']}): {d['located_by']} on {d.get('located_date')}, "
            f"now {d.get('inferred_local_authority') or d.get('postcode')}"
        )
    if feed in ("new_companies", "location_unknown"):
        cqc = {"yes": "already CQC-registered", "possible": f"possible CQC match: {d.get('cqc_provider_name')}"}
        return (
            f"{d['company_name']} ({d['company_number']}), incorporated {d['incorporated']}, {d.get('postcode')}, "
            f"{cqc.get(d.get('cqc_registered'), 'not CQC-registered')}"
        )
    where = f"{d['location_name']}, {d.get('postcode')} ({d.get('provider_name') or 'provider unknown'})"
    if feed == "poor_ratings":
        was = f", was {d['previous_rating']}" if d.get("previous_rating") else ""
        return f"{where}: {d['rating']} ({d.get('rating_date') or 'undated'}{was}); {d['suggested_channel']}"
    if feed == "due_for_inspection":
        return f"{where}: {d.get('due_reason')}; {d.get('provider_group') or 'size unknown'}; {d['suggested_channel']}"
    return f"{where}: registered {d.get('registration_date')}; {d['suggested_channel']}"


@app.command()
def site(
    region: Annotated[str | None, typer.Option(help="Region for the live numbers (default: showcase_region)")] = None,
    weeks: Annotated[int, typer.Option(min=1, max=13, help="Weeks of numbers to show")] = 4,
    config: ConfigOption = None,
) -> None:
    """Build your website and sales sheet into ~/Signals/site, from business.yaml and the database.

    Upload the whole site folder to any static web host. The sample page shows live numbers with anonymised
    examples. Re-run it whenever you change business.yaml, or to refresh the numbers.
    """
    from signals.core.clock import utcnow
    from signals.settings import data_home, load_business
    from signals.site.build import build_site, site_data
    from signals.verticals.care.collect import CareScope
    from signals.verticals.care.digest import sample_leads
    from signals.verticals.care.feeds import ALL_ENGLAND, CareVertical

    settings = Settings.load(config)
    business = load_business()
    regions = settings.config.regions
    region = region or business.showcase_region or next(iter(regions), ALL_ENGLAND)
    if regions and region not in regions:
        raise typer.BadParameter(f"unknown region {region!r}; configured regions: {', '.join(regions)}")
    period = _weeks(None, weeks)
    leads = None
    if settings.config.database.exists():
        with _open_store(settings) as store:
            leads = sample_leads(CareVertical(store, CareScope(regions)), period, region, regions.get(region))
    folder = data_home() / "site"
    build_site(site_data(business, region, period, leads), folder, today=utcnow().date())
    typer.secho(f"Website built in {folder}", fg="green")
    typer.echo(f"  Look at it:        open {shlex.quote(str(folder / 'index.html'))}")
    typer.echo(f"  Sales sheet (PDF): open {shlex.quote(str(folder / 'sales-sheet.html'))}  then File, Print, Save as PDF")
    if leads is None:
        typer.secho("  No database yet, so the pages show no live numbers.", fg="yellow")
    missing = business.missing()
    if missing:
        typer.secho(
            f"  Before publishing, fill in {', '.join(missing)} in {data_home() / 'business.yaml'}: the privacy "
            "notice must say who you are and how to reach you. Highlighted [brackets] mark the gaps.",
            fg="yellow",
        )


def parse_age(text: str) -> timedelta:
    """Parse an age such as 365d, 52w or a bare number of days."""
    match = re.fullmatch(r"\s*(\d+)\s*([dw]?)\s*", text.lower())
    if not match:
        raise typer.BadParameter("use a number of days, e.g. 365d or 52w")
    n = int(match.group(1))
    return timedelta(weeks=n) if match.group(2) == "w" else timedelta(days=n)


@app.command()
def purge(
    older_than: Annotated[
        str | None, typer.Option(help="Age cutoff, e.g. 365d or 52w (default: retention_days from config)")
    ] = None,
    config: ConfigOption = None,
) -> None:
    """Delete data and output folders older than the retention period (keeps each live record's current version)."""
    from signals.core.clock import utcnow
    from signals.output.writers import purge_outputs

    settings = Settings.load(config)
    age = parse_age(older_than) if older_than else timedelta(days=settings.config.retention_days)
    cutoff = utcnow() - age
    with _open_store(settings) as store:
        removed = store.purge(cutoff)
    removed["output folders"] = purge_outputs(settings.config.outputs_dir, cutoff.date())
    typer.echo(f"Purged data older than {age.days} days: " + ", ".join(f"{k} {v:,}" for k, v in removed.items()))


@app.command()
def suppress(
    entity_id: Annotated[
        str | None, typer.Argument(help="CQC location or provider ID (e.g. 1-123456789) or company number")
    ] = None,
    note: Annotated[str | None, typer.Option(help="Why, e.g. 'asked not to be contacted, 1 Oct 2026'")] = None,
    remove: Annotated[bool, typer.Option("--remove", help="Take the ID off the list again")] = False,
    config: ConfigOption = None,
) -> None:
    """Opt someone out: erase what is stored about them and never store or list them again.

    Use it when a person or organisation asks not to be contacted or to have their data deleted. With no ID,
    lists everyone on the opt-out list. Suppressing a provider also covers all of its locations. Files
    already written to outputs/ are not changed; delete or re-run those weeks if needed.
    """
    from signals.core.clock import utcnow

    settings = Settings.load(config)
    with _open_store(settings) as store:
        if entity_id is None:
            rows = store.suppressed()
            typer.echo(f"{len(rows)} on the opt-out list")
            for sid, added, why in rows:
                typer.echo(f"  {sid}  added {added:%d %b %Y}{f'  ({why})' if why else ''}")
            return
        entity_id = entity_id.strip()
        if remove:
            found = store.unsuppress(entity_id)
            typer.echo(f"{entity_id} removed from the opt-out list" if found else f"{entity_id} was not on the list")
            return
        removed = store.suppress(entity_id, note, utcnow())
        typer.echo(
            f"{entity_id} is now opted out. Erased: " + ", ".join(f"{k} {v:,}" for k, v in removed.items())
        )


@app.command()
def schedule(
    day: Annotated[str, typer.Option(help="Day of the week to run")] = "monday",
    hour: Annotated[int, typer.Option(min=0, max=23, help="Hour (24-hour clock, local time)")] = 7,
    minute: Annotated[int, typer.Option(min=0, max=59)] = 0,
) -> None:
    """Set up the weekly run: on a Mac, writes a launchd job to switch on; elsewhere, prints a cron line.

    Run it from the project folder. It changes nothing until you run the command it prints.
    """
    import platform

    from signals.schedule import DAYS, cron_line, find_uv, launchd_plist, plist_path, protected_folder

    day = day.strip().lower()
    if day not in DAYS:
        raise typer.BadParameter(f"choose one of: {', '.join(DAYS)}")
    project = Path.cwd().resolve()
    if not (project / "pyproject.toml").exists() or not (project / "config").is_dir():
        typer.secho("Run this from the project folder (the one containing pyproject.toml).", fg="red", err=True)
        raise typer.Exit(2)
    uv = find_uv()
    if not uv:
        typer.secho("Couldn't find uv. Install it first (see README).", fg="red", err=True)
        raise typer.Exit(2)
    from signals.settings import data_home

    log = data_home() / "logs" / "weekly.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    home = Path.home()
    when = f"every {day.title()} at {hour:02d}:{minute:02d}"

    if platform.system() != "Darwin":
        typer.echo(f"Add this line with `crontab -e` to run {when}:\n")
        typer.echo(cron_line(project, uv, day, hour, minute, log))
        return

    for what, where in (("code folder", project), ("Signals folder", data_home())):
        folder = protected_folder(where, home)
        if folder:
            typer.secho(
                f"Warning: your {what} ({where}) is inside your {folder} folder, which macOS blocks background "
                f"jobs from reading.\nMove it into your home folder ({home}) first, open Terminal in the code "
                "folder, and run this command again.", fg="yellow",
            )
            raise typer.Exit(1)
    path = plist_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(launchd_plist(project, uv, day, hour, minute, log))
    typer.secho(f"Wrote {path}", fg="green")
    typer.echo(f"It will run {when} (or as soon as the Mac wakes, if it was asleep). To switch it on, run:\n")
    typer.echo(f"    launchctl load -w {shlex.quote(str(path))}\n")
    typer.echo(f"To switch it off later: launchctl unload -w {shlex.quote(str(path))}")
    typer.echo(f"Each run is logged to {log}")


if __name__ == "__main__":
    app()
