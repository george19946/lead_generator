# Progress

## Milestone 1: scaffold, config, API clients (code done; live smoke test waiting on real API keys)

### Done
- uv project (Python 3.12). Dependencies: httpx, pydantic, pydantic-settings, pyyaml, typer, jinja2; pytest for dev.
- `.env` handling (`CQC_API_KEY`, `COMPANIES_HOUSE_API_KEY`; real env vars win). `.env.example` added, `.env` is gitignored.
- `config/signals.yaml`: DB path, per-source rate limits, retention, the `include_personal_names` switch, and customer regions.
- `signals/http.py`: sliding-window rate limiter, and a JSON GET client with backoff on 429/5xx/transport errors.
- `CqcClient`: changes (location/provider, with `perPage`) with pagination and dedupe, location list with filters,
  and location/provider detail.
- `CompaniesHouseClient`: advanced search. Weekly date slices, `start_index` paging, automatic range splitting
  above 10,000 hits, and a 404 treated as empty.
- CQC sanitiser that strips personal names (`contacts`, `nominatedIndividual`, `person*` keys).
- Pydantic models for CQC location/provider and Companies House company.
  - `CqcLocation.overall_rating` reads `currentRatings` **or** the Single Assessment Framework `assessment` block,
    and normalises the rating spelling.
- `signals smoke [--n 5] [--save-fixtures]`:
  - fetches changes, location and provider details, an adult-social-care list page, and a Companies House search;
  - reports missing or unexpected fields, the rating framework, and timings;
  - writes sanitised fixtures.
- 31 offline tests (`uv run pytest`) using synthetic, schema-shaped fixtures. Real network I/O raises inside tests.

### Session 2 (2026-09-22)
- Both API hosts and the CQC developer portal are now reachable. I read the official CQC operation specs through the
  portal's developer API, and the Companies House advanced-search spec.
- **The keys are placeholders.** `CQC_API_KEY` holds the text `CQC` and `COMPANIES_HOUSE_API_KEY` holds `Companies_House`.
  Both APIs return 401. The user has been sent step-by-step instructions for getting real keys.

### Blocked / next
- **The live smoke test is blocked on real API keys.** Then: `uv run signals smoke --n 5 --save-fixtures`, check the fixtures
  for personal data (`grep -ri 'person\|nominated\|contacts' tests/fixtures`), and commit them.
- Measure the CQC rate limit and the weekly changes volume, for the M2 backfill estimate.
- Then milestone 2: SQLite schema, snapshot storage, `init`, `backfill`.

### API facts: confirmed vs the brief (official docs, 2026-09-22)
1. ✅ CQC base `https://api.service.cqc.org.uk/public/v1` (alternative server: `api-management.service.cqc.org.uk`).
   The key goes in the `Ocp-Apim-Subscription-Key` header, or the `subscription-key` query parameter. The product is "Syndication".
   The subscription is approved automatically.
2. ✅ `/changes/{location|provider}` takes `startTimestamp` (inclusive), `endTimestamp` (**exclusive**), `page` and `perPage`.
   The response is `{total, page, totalPages, perPage, nextPageUri, ..., changes: [ids]}`.
3. ✅ `/locations` filters: `inspectionDirectorate`, `region`, `localAuthority`, `careHome` (Y/N), `overallRating`,
   `gacServiceTypeDescription`, `regulatedActivity`, `constituency`, `page`, `perPage`. A repeated parameter means OR.
   The list items are only `{locationId, locationName, postalCode}`.
4. ✅ Locations **do** have `website`. That corrects an earlier note from a third-party schema.
5. ⚠️ **Difference from the brief: the Single Assessment Framework.** Newer assessments appear under
   `assessment[].ratings.asgRatings[]` (`rating`, `status: "Current"`, `assessmentDate`), and
   `assessment[].assessmentPlanPublishedDateTime`, sometimes with no `currentRatings` at all. The spelling differs too:
   "Requires Improvement" rather than "Requires improvement". The poor-ratings and never-inspected feeds must check both.
6. ⚠️ Providers name the nominated individual in `regulatedActivities[].nominatedIndividual` (personal data, now stripped).
7. ✅ Companies House `/advanced-search/companies` takes `sic_codes`, `incorporated_from/to`, `company_type`, `company_status`,
   `size` (1–5000) and `start_index`, and returns **404 when no companies are found**.
8. Still to confirm live: the CQC rate limit, whether `inspectionDirectorate=Adult social care` is the exact filter
   value, the Companies House `company_type` values, and how often each rating framework appears in real data.

### Open questions
- None blocking. The CQC rate limit is undocumented, so the default is 10 req/s until measured.

## Milestones
1. Scaffold + clients + smoke test: code done, live run waiting on keys
2. SQLite schema, snapshots, backfill: not started
3. Feeds + CH↔CQC matching + tests: not started
4. CSV/HTML output, region filtering, `sample`: not started
5. README, cron example, limitations, final PRIVACY_NOTES: not started
