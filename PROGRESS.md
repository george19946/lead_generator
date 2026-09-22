# Progress

## Milestone 1: scaffold, config, API clients (code done; live smoke test pending)

### Done
- uv project (Python 3.12). Dependencies: httpx, pydantic, pydantic-settings, pyyaml, typer, jinja2; pytest for dev.
- `.env` handling (`CQC_API_KEY`, `COMPANIES_HOUSE_API_KEY`; real env vars win). `.env.example` added, `.env` is gitignored.
- `config/signals.yaml`: DB path, per-source rate limits, retention, the `include_personal_names` switch, and customer regions.
- `signals/http.py`: sliding-window rate limiter, and a JSON GET client with backoff on 429/5xx/transport errors.
- `CqcClient`: changes (location/provider) with pagination and dedupe, location list with filters, location/provider detail.
- `CompaniesHouseClient`: advanced search. Weekly date slices, `start_index` paging, automatic range splitting
  above 10,000 hits, and a 404 treated as empty.
- CQC sanitiser that strips personal names (`contacts`, `person*` keys).
- Pydantic models for CQC location/provider and Companies House company.
- `signals smoke [--n 5] [--save-fixtures]`:
  - fetches changes, location and provider details, an adult-social-care list page, and a Companies House search;
  - reports missing or unexpected fields, response sizes and timings;
  - writes sanitised fixtures.
- 28 offline tests (`uv run pytest`) using synthetic, schema-shaped fixtures. Real network I/O raises inside tests.

### Blocked / next
- **The live smoke test hasn't run yet.** This environment's egress policy blocks `api.service.cqc.org.uk` and
  `api.company-information.service.gov.uk`, and no keys are set. Once the hosts are allowlisted and the keys are set:
  `uv run signals smoke --n 5 --save-fixtures`, then review the fixtures and commit them.
- Measure the CQC rate limit and weekly changes volume. They feed the backfill estimate in M2.
- Then milestone 2: SQLite schema, snapshot storage, `init`, `backfill`.

### To verify live (secondary sources only so far; the official docs are blocked from this sandbox)
1. CQC base URL `https://api.service.cqc.org.uk/public/v1` and header `Ocp-Apim-Subscription-Key`
   (source: birdiecare/tap-cqc-org-uk). The older docs also mention `https://api.cqc.org.uk/public/v1`.
2. Changes response shape: `changes` as a list of ID strings, plus `total`/`totalPages`/`nextPageUri`.
3. Filter value `inspectionDirectorate=Adult social care` on `/locations`.
4. **Likely difference from the brief:** locations have no `website` field. The website is on the provider.
5. Rating shape `currentRatings.overall.{rating, reportDate}` and `historicRatings[].overall.rating`.
6. Companies House `company_type` values (`ltd`, `llp`, …), and whether advanced search returns 404 or an empty list when nothing matches.

### Open questions
- None blocking. The CQC rate limit is undocumented, so the default is 10 req/s until measured.

## Milestones
1. Scaffold + clients + smoke test: code done, live run pending
2. SQLite schema, snapshots, backfill: not started
3. Feeds + CH↔CQC matching + tests: not started
4. CSV/HTML output, region filtering, `sample`: not started
5. README, cron example, limitations, final PRIVACY_NOTES: not started
