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
uv run signals setup                     # create ~/Signals (data home), move old in-folder data there, ask for keys
uv run signals keys                      # save/change API keys in ~/Signals/keys.env (hidden prompt)
uv run signals smoke --n 5               # live smoke test (needs keys + network access)
uv run signals smoke --save-fixtures     # ...and write sanitised fixtures to tests/fixtures/
uv run signals init                      # create the SQLite DB (config `database`)
uv run signals backfill --dry-run        # list the scope, print the API-call estimate (list calls only)
uv run signals backfill --days 90        # baseline; asks first, resumes if re-run (--fresh-hours)
uv run signals backfill --only-new       # after adding/widening a region: fetch only unstored locations
uv run signals sync                      # fetch changes since the last backfill/sync
uv run signals run --weeks 4             # sync, record each week's leads, write outputs/care/<week>/<region>/
uv run signals sample --region london    # preview digest from stored data (records nothing)
uv run signals purge --older-than 365d   # DB data and output folders past retention
uv run signals suppress ID --note "..."  # opt-out: erase + never store/list again (no ID: list; --remove)
uv run signals schedule                  # macOS launchd weekly job (prints the launchctl command); cron elsewhere
uv run signals site                      # website + sales sheet into ~/Signals/site from business.yaml + live data
uv run signals prospects --region london # CQC consultancies (companies/LLPs) from Companies House -> ~/Signals/prospects/
```

## Layout
- `src/signals/core/`: vertical-agnostic interfaces (Source, Feed, Vertical, region filter,
  legal form/PECR, matching, runner). **Nothing care-specific goes here.**
- `src/signals/sources/<source>/`: API client, pydantic models and Source adapter per register.
- `src/signals/verticals/care/`: care feeds, SIC codes, CH↔CQC linking. `collect.py`: scope, backfill and sync.
- `src/signals/db/`: SQLite schema and store (stdlib sqlite3). A snapshot is written only when a payload changes.
- `src/signals/output/`: CSV and jinja2 HTML digest.
- `src/signals/schedule.py`: launchd plist / cron line for the weekly job. `src/signals/verticals/care/watch.py`:
  re-checks formation-agent companies. `README.md` is the user guide (beginner, Mac); `PRIVACY_NOTES.md` is final.
- `src/signals/site/`: static business website (index, sample, privacy notice, opt-out, sales sheet); examples are
  anonymised (masked names, postcode district, no sole traders). `config/business.yaml`: template for business details.
- `business/`: LIA, customer terms, outreach templates, launch & automation plan, £0 interest test (do first), 8-week trial plan (for the user,
  not code).
- `config/signals.yaml`: the config **template**; `setup` copies it to `~/Signals/signals.yaml`, which is the one used.
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
- Due-for-inspection feed: current rating ≥ 4 years old (not inspected since) or unrated a year after registering.
  Event date = the day it became due; `due_for_inspection_all.csv` holds every one due, oldest first. The feed
  counts only what's due by `CareData.as_of` (today unless given).
- Provider size: "large group" = a CQC brand (`brandId`/`brandName`) or ≥ 10 registered locations in our data;
  "independent" = one location ever (`locationIds` also lists closed ones); else "multi-site". Location leads from
  large groups are left out of digests unless the region sets `include_large_groups`. Labels are re-derived at
  render time, like the company flags.
- **Companies-only mode** (`companies_only`, default true): every CLI store open/close erases stored sole-trader and
  partnership providers (and their locations/leads) and blocks them via the suppressed table with
  `policy.COMPANIES_ONLY_NOTE`; turning it off lifts only those rows. So leads hold no personal data (no ICO fee needed
  for the £0 test; see business/zero-cost-test.md).
- `signals sample` also writes `email-teaser.txt` (numbers + organisation-only examples for sales emails).
  `signals prospects`: CH name search (company/LLP types only), names must contain a care word AND a consultancy word.
- Area limits (`places_per_area`, `exclusive_price` in business.yaml) are a sales policy shown on the site; nothing
  enforces them yet.
- A lead is recorded once, for the week whose window (the week + 14 days' grace) holds its event date (core/runner.py).
- Companies at a registered-office postcode shared by ≥ 5 stored care companies (formation agents) get no region;
  they form the `location_unknown` feed (pseudo-region `national`), listed in every region's digest.
- Watched companies: shared-address companies < 365 days old get their CH profile re-read every 28 days (≤ 300/run,
  inside `sync`); a move to a regional postcode or an exact CQC provider link becomes a `company_located` lead.
- Opt-outs live in the `suppressed` table (schema v2): `save_record` refuses suppressed IDs (and locations of a
  suppressed provider); `suppress` also erases stored data and leads. Schema changes need a `MIGRATIONS` step.
- **Data home** `~/Signals` (or $SIGNALS_HOME) holds everything that is the user's: `keys.env`, `signals.yaml`,
  `data/`, `outputs/`, `logs/`. The code folder is disposable (updating = replace it). Relative config paths resolve
  against the data home. Key precedence: env vars > `~/Signals/keys.env` > `./.env`. Tests set SIGNALS_HOME=tmp_path.
- The real database lives on the user's Mac, not in the cloud container; the user is a beginner, so give exact steps.
- Idempotency: lead events are unique on (vertical, feed, entity_key, trigger_key). Outputs are
  deterministic per (vertical, region, week_ending).
- Fuzzy matching uses stdlib difflib (no rapidfuzz), to keep dependencies minimal.
- Dependencies: httpx, pydantic, pydantic-settings, pyyaml, typer, jinja2. Dev: pytest. Ask before adding more.

## Conventions
- Tests never call live APIs: use `httpx.MockTransport`. The autouse guard in `tests/conftest.py` makes real I/O raise.
- Clients take an injectable `transport` and `sleep` so tests are fast and offline.
- Never log or print API keys (error messages list key names only). Never commit `.env` or `keys.env`.
- Before any large backfill, estimate the API calls and duration and tell the user first.
- Milestones: stop after each one, update PROGRESS.md, commit with a clear message, and wait for the go-ahead.
- Work on branch `claude/sharp-turing-c0z2m0`.
