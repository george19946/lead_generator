# CLAUDE.md — Signals engine

**At the start of every session, read this file and PROGRESS.md before doing anything else.**

## What this is
A weekly lead generator. It watches UK public registers for trigger events and writes a digest of
sales leads per customer region. The first vertical is **care**: CQC-registered adult social care,
sold to CQC compliance consultancies. There are three feeds: new care companies (Companies House),
never-inspected locations (CQC), and poor ratings (CQC).

## Commands
```bash
uv sync                                  # install (Python 3.12, managed by uv)
uv run pytest                            # tests: offline only, real network raises
uv run signals smoke --n 5               # live smoke test (needs keys + network access)
uv run signals smoke --save-fixtures     # ...and write sanitised fixtures to tests/fixtures/
uv run signals init                      # create the SQLite DB (config `database`)
uv run signals backfill --dry-run        # list the scope, print the API-call estimate (list calls only)
uv run signals backfill --days 90        # baseline; asks first, resumes if re-run (--fresh-hours)
uv run signals sync                      # fetch changes since the last backfill/sync
uv run signals run --weeks 4             # sync, then record and print each week's leads (--no-sync, --week-ending)
uv run signals purge --older-than 365d
# Planned (later milestones): CSV/HTML outputs from `run`, sample --region london
```

## Layout
- `src/signals/core/`: vertical-agnostic interfaces (Source, Feed, Vertical, region filter,
  legal form/PECR, matching, runner). **Nothing care-specific goes here.**
- `src/signals/sources/<source>/`: API client, pydantic models and Source adapter per register.
- `src/signals/verticals/care/`: care feeds, SIC codes, CH↔CQC linking. `collect.py`: scope, backfill and sync.
- `src/signals/db/`: SQLite schema and store (stdlib sqlite3). A snapshot is written only when a payload changes.
- `src/signals/output/`: CSV and jinja2 HTML digest.
- `config/signals.yaml`: non-secret config, including customer regions. Secrets go in `.env` only.
- `tests/fixtures/synthetic/`: hand-built records. `tests/fixtures/{cqc,companies_house}/`: sanitised live captures.

## Key decisions
- **Trust the live API over the brief.** Log any difference in PROGRESS.md and tell the user.
- CQC ("Syndication" product): base `https://api.service.cqc.org.uk/public/v1`, header `Ocp-Apim-Subscription-Key`.
  Changes: `/changes/{location|provider}?startTimestamp&endTimestamp&page&perPage` (UTC `%Y-%m-%dT%H:%M:%SZ`,
  start inclusive, end exclusive). Official operation specs are readable from
  `https://api-portal.service.cqc.org.uk/developer/apis/syndication/operations?api-version=2022-04-01-preview`.
- CQC ratings live in `currentRatings.overall` **or** the Single Assessment Framework `assessment[].ratings.asgRatings[]`.
  Always use `CqcLocation.overall_rating`, which checks both and normalises the spelling.
- Companies House: `/advanced-search/companies`, basic auth (key as username). Size ≤ 5000,
  errors past start_index ≈ 10,000, so queries are sliced by week and split further if needed. A 404 means no results.
- Rate limiting: a sliding-window limiter per source (config `sources.*.max_requests/per_seconds`),
  plus exponential backoff with jitter on 429/5xx/transport errors, honouring Retry-After.
- Personal data: `contacts`, `nominatedIndividual` and other `person*` fields are stripped before storage
  unless `include_personal_names: true`. Sole-trader provider names are redacted in committed fixtures.
- Never-inspected feed: the digest and feed CSV show **new entries only**. `never_inspected_all.csv` holds the full list.
- A lead is recorded once, for the week whose window (the week + 14 days' grace) holds its event date (core/runner.py).
- Companies at a registered-office postcode shared by ≥ 5 stored care companies (formation agents) get no region.
- The real database lives on the user's Mac, not in the cloud container; the user is a beginner, so give exact steps.
- Idempotency: lead events are unique on (vertical, feed, entity_key, trigger_key). Outputs are
  deterministic per (vertical, region, week_ending).
- Fuzzy matching uses stdlib difflib (no rapidfuzz), to keep dependencies minimal.
- Dependencies: httpx, pydantic, pydantic-settings, pyyaml, typer, jinja2. Dev: pytest. Ask before adding more.

## Conventions
- Tests never call live APIs: use `httpx.MockTransport`. The autouse guard in `tests/conftest.py` makes real I/O raise.
- Clients take an injectable `transport` and `sleep` so tests are fast and offline.
- Never log or print API keys. Never commit `.env`.
- Before any large backfill, estimate the API calls and duration and tell the user first.
- Milestones: stop after each one, update PROGRESS.md, commit with a clear message, and wait for the go-ahead.
- Work on branch `claude/sharp-turing-c0z2m0`.
