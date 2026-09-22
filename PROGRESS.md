# Progress

## Milestone 1: scaffold, config, API clients (CQC verified live; Companies House waiting on a valid key)

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
- 60+ offline tests (`uv run pytest`), including tests over the live-captured CQC fixtures, using synthetic, schema-shaped fixtures. Real network I/O raises inside tests.

### Session 2 (2026-09-22)
- Both API hosts and the CQC developer portal are now reachable. I read the official CQC operation specs through the
  portal's developer API, and the Companies House advanced-search spec.
- **The keys are placeholders.** `CQC_API_KEY` holds the text `CQC` and `COMPANIES_HOUSE_API_KEY` holds `Companies_House`.
  Both APIs return 401. The user has been sent step-by-step instructions for getting real keys.

### Session 3 (2026-09-22): live smoke test
- **CQC: working.** Sanitised live fixtures are in `tests/fixtures/cqc/`: 10 locations (including one dental and
  one deregistered), 5 providers, a changes page and a list page. A grep confirmed no person-name fields in them.
- **Companies House: 401.** `COMPANIES_HOUSE_API_KEY` holds **the same value as `CQC_API_KEY`**, so the CQC key was
  pasted twice. The user needs to create a Companies House REST key (Live environment) and set it.
- The smoke test now reports each API's failure separately. Empty optional fields are counted rather than flagged.

### Live measurements (2026-09-22)
- CQC latency is about 0.17 s per request, sequential. A burst of 40 requests at 10 concurrent (about 12 req/s) got no 429s.
  CQC sends no rate-limit headers. The default of 10 req/s stays.
- CQC changes over 7 days: **871 locations, 379 providers**, one page at `perPage=1000`.
- `/locations?inspectionDirectorate=Adult social care`: 57,909. The list **includes deregistered locations**
  (there's no `registrationStatus` filter), so the baseline must filter locally. London adult social care: 7,492.
  Care homes (`careHome=Y`): 27,344. Not care homes: 30,565.
- Early backfill estimate for London only:
  - about 7.5k location details + 8 list pages + about 3k providers ≈ **10.5k CQC calls, 20–35 min**;
  - Companies House: 90 days ≈ 13 calls, under a minute.
  - A weekly run ≈ 1,250 CQC detail calls (≈ 4 min) + 1–2 Companies House calls.
  - To be firmed up in M2.

### Blocked / next
- **Companies House key.** Once it's valid, re-run `uv run signals smoke --n 5 --save-fixtures` to capture the
  Companies House fixture, and confirm the `company_type` values.
- Then milestone 2: SQLite schema, snapshot storage, `init`, `backfill` (with the call estimate shown to the user first).

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
8. ✅ Live: `inspectionDirectorate=Adult social care` is the right filter value. CQC region names use CQC spellings,
   e.g. "Yorkshire & Humberside". Location `type` for care is "Social Care Org". `gacServiceTypes[].name` includes
   "Homecare agencies", "Residential homes", "Nursing homes" and "Supported living".
9. ✅ Live: `website`, `mainPhoneNumber`, `currentRatings` and `companiesHouseNumber` are **left out entirely** when
   empty, not set to null. Website coverage was low in the sample (locations 4/10, providers 4/5).
   None of the 10 sampled locations used the `assessment` block.
10. ⚠️ All 5 sampled providers had `companiesHouseNumber`, so exact CH↔CQC matching should cover many providers.
11. Still to confirm: the Companies House `company_type` values (needs a valid key).

### Open questions
- None blocking. The CQC rate limit is undocumented, so the default is 10 req/s until measured.

## Milestones
1. Scaffold + clients + smoke test: code done, live run waiting on keys
2. SQLite schema, snapshots, backfill: not started
3. Feeds + CH↔CQC matching + tests: not started
4. CSV/HTML output, region filtering, `sample`: not started
5. README, cron example, limitations, final PRIVACY_NOTES: not started
