"""`signals` command-line interface."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from signals.settings import MissingSecretError, Settings

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


if __name__ == "__main__":
    app()
