"""`signals` command-line interface."""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from signals.settings import MissingSecretError, Settings

if TYPE_CHECKING:
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
            plan = plan_backfill(cqc, store, scope, days=days, now=utcnow(), fresh_hours=fresh_hours)
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
    """Delete data older than the retention period (keeps each live record's current version)."""
    from signals.core.clock import utcnow

    settings = Settings.load(config)
    age = parse_age(older_than) if older_than else timedelta(days=settings.config.retention_days)
    with _open_store(settings) as store:
        removed = store.purge(utcnow() - age)
        typer.echo(f"Purged data older than {age.days} days: " + ", ".join(f"{k} {v:,}" for k, v in removed.items()))


if __name__ == "__main__":
    app()
