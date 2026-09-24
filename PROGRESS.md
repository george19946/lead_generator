# Progress

## £0 interest test: companies-only mode, email teaser, prospects (2026-09-24)
- **Why:** the user won't spend the ~£70 of the 8-week plan before seeing interest. Everything needed for a first
  test is now free.
- **Companies-only mode** (`AppConfig.companies_only`, default **true**; `verticals/care/policy.py`):
  - on every CLI store open and close, stored sole-trader and partnership providers are erased (with their
    locations and leads) and blocked through the suppressed table, with a note of their own;
  - turning the mode off lifts only those rows, never real opt-outs, and prints the backfill command;
  - the privacy notice and FAQ adapt to the mode, and `business.missing()` no longer requires an address.
  - It costs ~1–2% of leads: 2 of 133 providers in the test boroughs.
- **`email-teaser.txt`**, written by `signals sample`: live counts, the longest-waiting due services (independents
  first) and recent poor ratings, **organisations only**, plus a ready-made sentence.
- **`signals prospects [--region]`**: CH advanced search by name phrase (company_type limited to ltd/llp/plc/guarantee,
  so emailing is allowed under PECR).
  - A name must contain a care word and a consultancy word; obvious non-care names are dropped.
  - Rows are sorted in-region first, then newest. Columns to fill: approved/email/first_name/website/notes.
  - Live: 594 prospects (144 in London) from 11 requests.
  - `CompaniesHouseClient.search_by_name` added.
- `business/zero-cost-test.md`: the £0 plan (free Gmail, Netlify subdomain, Claude-drafted Gmail drafts, manual
  Monday digests), emails, decision gates, and every free option considered. The 8-week plan is now phase 2.
- 201 tests.

## Stress test follow-ups: due-for-inspection list, group filter, area limits (2026-09-24)
- **Why:** the viability stress test found weekly volumes thin (London: about 3 poor ratings and 5 new registrations a
  week), many "hot" leads belonging to big groups, and the same leads going to every customer.
- **`due_for_inspection` feed** (`feeds.DueForInspectionFeed`): registered adult social care locations whose current
  rating is ≥ 4 years old (and not inspected since), or unrated ≥ 365 days after registering. CQC is prioritising
  aged ratings (83.5% of community services unrated or rated 4+ years ago, Homecare Association, May 2026).
  - Weekly leads = what became due that week. `due_for_inspection_all.csv` lists every one, longest waiting first.
  - Real data (two boroughs, scratchpad DB): 77 due, of which 39 are never rated and 50 are independents.
- **Provider size labels**: independent / multi-site / large group, from CQC `brandId`/`brandName` (now in the
  models) and registered-location counts. Live check: a provider's `locationIds` includes deregistered locations
  (MiHomecare: 18 of 20 sampled were deregistered), so it's only used to prove "independent".
  - Large groups are hidden by default (`RegionConfig.include_large_groups`), with a count in the digest notes.
- **Area limits**: `places_per_area` (2) and `exclusive_price` (£249) in `business.yaml`, shown on the site, the sales
  sheet and in the terms. The site also shows the due-for-inspection total and anonymised examples.
- `business/8-week-trial-plan.md`: an email-only trial for about £70 and 15 hours, with decision rules.
  - Its automation is the revised **Milestone 6** (awaiting go-ahead): `signals prospects`, `signals outreach` (3-email
    sequence, 25/day cap, stops on reply via IMAP, do-not-contact list), `signals customer`, `signals send`
    (digests plus lifecycle emails), and a Monday scoreboard email.
- 197 tests.

## Business launch kit (2026-09-24)
- **`signals site`** (`src/signals/site/`) builds a static website into `~/Signals/site` from `~/Signals/business.yaml`
  (template `config/business.yaml`, copied by `setup`) and the database:
  - `index.html`: landing page, live numbers, what you get, how it works, compliance, pricing, FAQ;
  - `sample.html`: live counts plus **anonymised** examples. Names are masked except generic words, only the postcode
    district is shown, sole traders, partnerships and unknown legal forms are excluded, flagged companies are
    excluded, and there are no phones, websites or IDs;
  - `privacy.html`: an Article 14 notice (controller, sources, purposes, legitimate interests, recipients,
    retention, rights, ICO complaint, no cookies);
  - `opt-out.html`;
  - `sales-sheet.html`: prints to a one-page A4 PDF.
  - The pages have no scripts and no cookies. Missing controller details are highlighted as [brackets], and the
    command warns about them. Zero-valued stats and empty example lists are hidden.
- `business/`:
  - `legitimate-interests-assessment.md` (ICO three-part test, with sole traders addressed);
  - `customer-terms.md` (customers are independent controllers, PECR duties, opt-outs passed back within 5 days);
  - `outreach-emails.md` (PECR rules for the user's own outreach, where to find prospects, a 3-email sequence,
    LinkedIn, a phone script, replies);
  - `launch-and-automation.md` (launch checklist; automation split into deterministic code, Claude-assisted work
    with human approval, and things not to automate).
- `digest.sample_leads()` split out of `write_sample` for reuse. 191 tests.
- **Proposed Milestone 6 (not started, awaiting go-ahead):**
  - `~/Signals/customers.yaml` and customer commands;
  - `signals send` (stdlib smtplib, SMTP credentials in `keys.env`) to email each customer their region digest
    after the Monday run;
  - trial reminders with a Stripe link;
  - opt-out notifications to customers who received the lead;
  - a new-consultancy prospect list from Companies House.
  - (Superseded by the revised Milestone 6 in the entry above.)

## Data home: user data kept apart from the code (2026-09-24)
- **Problem:** the user updated by pasting the new code over the old folder and lost `.env` and `data/`, so had to
  re-enter the keys and backfill again. The update method (and a hidden `.env` inside the code folder) was fragile.
- **Fix:** everything that is the user's now lives in a **data home**, `~/Signals` (or `$SIGNALS_HOME`):
  `keys.env`, `signals.yaml`, `data/`, `outputs/` and `logs/`. The code folder is disposable, so updating means
  deleting it and unzipping the new version in its place.
  - Relative config paths resolve against the data home.
  - Config lookup: `$SIGNALS_CONFIG`, then `~/Signals/signals.yaml`, then the template `config/signals.yaml`.
  - Keys: environment variables win, then `~/Signals/keys.env`, then a local `.env` (kept for development).
- **`signals setup`** (safe to re-run):
  - creates `~/Signals` and copies the config template there;
  - copies an old `.env` to `keys.env` (mode 600);
  - moves `data/`, `outputs/` and `logs/` out of the code folder (leaving both in place if both exist);
  - asks for any missing key.
- **`signals keys`**: hidden prompts, rejects values with spaces, quotes or `=`, and Enter keeps a saved key.
- The missing-key error now names `~/Signals/keys.env` and says to run `signals keys`, listing key names only.
- `schedule` logs to `~/Signals/logs/weekly.log`, and refuses to schedule if the code folder or data home is in a
  macOS-protected folder.
- Rehearsed end to end: old layout, then `setup`, then delete the code folder, fresh copy, `uv sync`, `run`.
  Keys, database and regions were all found, and the digest was written to `~/Signals/outputs`.
- README (setup step 6, updating, paths, troubleshooting), PRIVACY_NOTES §2 and `.env.example` updated. 186 tests.

## Milestone 5: README, scheduling, opt-outs, retention, final privacy notes (done)
- **README.md**, a beginner user guide for the Mac:
  - setup from the ZIP (move to the home folder, New Terminal at Folder, uv, `.env` with a check command, smoke, backfill);
  - the weekly run and what each output file is;
  - scheduling, regions config, opt-outs, updating, and a troubleshooting table (built from the errors we actually hit);
  - command reference, how it works, PECR table, and **limitations**.
- **PRIVACY_NOTES.md (final)**:
  - personal data inventory, storage and security advice;
  - legal basis (write an LIA) and transparency (Art. 14 privacy notice); customers become controllers;
  - retention (now covers outputs); the objection/erasure process; PECR table; attribution.
- **`signals schedule`** (`schedule.py`):
  - on macOS it writes `~/Library/LaunchAgents/com.signals.weekly.plist` for Monday 07:00 (`--day/--hour/--minute`)
    and prints the `launchctl load -w` command for the user to run (nothing is switched on automatically);
  - the job runs `/bin/zsh -lc "cd <project> && <uv> run signals run && <uv> run signals purge"`, logging to
    `logs/weekly.log`;
  - it **refuses to schedule from Downloads/Desktop/Documents/iCloud** (macOS privacy protection blocks background
    jobs there);
  - on other systems it prints a cron line.
  - launchd runs a job missed while asleep on wake; a job missed while the Mac was off is skipped.
- **Opt-outs**: `signals suppress ID [--note] [--remove]`, with no ID to list.
  - A new `suppressed` table (schema **v2**, with a migration step from v1, tested).
  - Suppressing erases the entity, its versions and its leads. For a provider, it also covers its locations
    (found with `json_extract`).
  - `save_record` refuses suppressed IDs, and locations whose provider is suppressed.
- **Retention**: `purge` also deletes output week folders and samples older than the cutoff. `logs/` is gitignored.
- **`backfill --only-new`**: skips every location and provider already stored. Use it after adding or widening
  a region; sync keeps stored ones current.
- 176 offline tests.

### For the user to do
- Update the code (ZIP copy method), `uv sync`, then:
  - move the project folder to the home folder if it's in Downloads;
  - run `uv run signals schedule`, then the printed `launchctl load -w …`.
- Before selling leads: record a legitimate interests assessment, and publish a privacy notice (PRIVACY_NOTES §3).

### Possible next steps (not started)
- Email the digests automatically (would need an SMTP account; ask before adding dependencies).
- More verticals (the core is vertical-agnostic), e.g. Ofsted children's homes for the flagged companies.
- Run on a small server for unattended weekly runs (copy the folder incl. `data/`, use the cron line).

## Watching location-unknown companies (done)
- `verticals/care/watch.py`: during `sync`, each company at a shared (formation-agent) registered office that was
  incorporated within **365 days** has its Companies House profile (`GET /company/{number}`) re-read every **28 days**,
  oldest-checked first, up to **300 per run** (about 3 minutes).
  - The registered office is replaced only when the **postcode** differs (profiles format addresses differently),
    so re-checks don't record false changes (live: 25 re-checks, 0 new versions).
  - A failed re-check is only counted (`company_recheck_failed`) and retried next run; it doesn't hold the sync cursors back.
- New feed **company_located** (digest section "Now located in your region", `company_located.csv`):
  - "moved registered office": the company moved from a shared postcode to one in a customer region.
    Trigger `moved:<postcode>`, dated when our snapshots first showed it.
  - "registered with CQC": a company still at a formation agent appears as a CQC provider in the database, matched
    by company number, in a customer region. Trigger `cqc:<provider id>`, dated by the CQC registration date.
- `Store.ids_with_history()`; `CompaniesHouseClient.get_company()`.
- Live: the profile shape was confirmed (`registered_office_address` with `premises`/`address_line_1`/`postal_code`).
- Steady-state cost: about 1,000 watched companies a year, so about 250 profile calls a week (2–4 minutes).
- 164 offline tests.

## Milestone 4: CSV/HTML digest per region, location-unknown list, flags, `sample` (done)

### Done
- New feed **location_unknown**: new care companies at a shared registered office (formation agent, ≥ 5 stored
  care companies at the postcode). They're recorded once, under the pseudo-region `national`, and listed in every
  region's digest. A region can opt out with `location_unknown: false` in `config/signals.yaml`.
  `new_companies` now holds only companies that can be placed in a region.
- `verticals/care/flags.py`:
  - SIC code labels (care codes, plus codes often listed with them; any other code shows as "SIC n");
  - name flags, as a hint for a person to check, never a filter: children's services (Ofsted, not CQC),
    recruitment/staffing, training/consultancy. Flagged companies sort last.
  - Both are worked out when the files are written, so older recorded leads get the current labels too.
- Output, vertical-agnostic (`signals/output/`):
  - `model.py`: Digest, Section, Column, Cell, Tile;
  - `writers.py`: CSV with a UTF-8 BOM so Excel reads it correctly, yes/no for booleans;
  - a jinja2 HTML template: self-contained page, no scripts, light and dark mode, prints cleanly,
    and its tables scroll sideways on narrow screens.
- Care digest (`verticals/care/digest.py`): `outputs/care/<week_ending>/<region>/`, containing
  `digest.html`, `poor_ratings.csv`, `never_inspected.csv`, `new_companies.csv`, `location_unknown.csv` and
  `never_inspected_all.csv`.
  - The weekly files come from recorded lead events, so re-running a week writes byte-identical files (tested).
  - `never_inspected_all.csv` reflects the database when it's written (the one exception to determinism),
    with days registered counted to the week's end.
  - Sort order: Inadequate before Requires improvement, then newest first.
- CLI:
  - `run` now writes each region's files (`--no-output` to skip) and prints their paths;
  - new `signals sample --region london [--weeks 4] [--week-ending]` writes a preview digest to
    `outputs/samples/care/<region>_<start>_to_<end>/` straight from the data. It fetches and records nothing.
    Note: Companies House data only goes back to the backfill (90 days).
- 159 offline tests.

### Live check (throwaway two-borough DB)
- Two weeks written. A 26-week sample: 1 new poor rating, 1 newly registered (dormant), 27 new companies,
  239 location unknown, 50 never inspected in total. Screenshots checked at desktop width and at 500px (the
  narrowest headless Chrome allows).

### Next
- The user updates their copy and runs `uv run signals run --weeks 4`, then opens the digests.

## Milestone 3: feeds, CH↔CQC matching, lead events (done)

### Done
- Core (vertical-agnostic):
  - `core/feed.py`: `Week` (Mon–Sun, `last_completed`), `Lead`, and the `Feed` and `Vertical` protocols.
  - `core/runner.py`: `run_week` records each lead **once**, using `INSERT OR IGNORE` on (vertical, feed, entity_key, trigger_key),
    for the week whose window contains its event date. The window is the week plus **14 days' grace** for late publication.
    Undated events are recorded when first seen. Re-running a week returns the same leads.
    A lead is never reported again in a later week.
  - `core/legal_form.py`: `LegalForm` and PECR `suggested_channel`: email OK for corporate subscribers;
    otherwise "phone - check TPS/CTPS first" if there is a phone number, else "post only". An unknown form uses the stricter rule.
  - `core/matching.py`: name normalisation (case, punctuation, &, legal suffixes) and difflib similarity.
    `NameIndex` blocks candidates by first token and postcode district.
    A match needs a score ≥ 0.93, or ≥ 0.85 with the same district.
  - `core/regions.py`: `PostcodeLookup` infers region and local authority for postcode-only records (Companies House)
    from stored CQC records. It votes per district, and falls back to the area only at ≥ 90% agreement.
- Source mappings:
  - Companies House `company_type` and company-number prefix → legal form
    (e.g. `limited-partnership`/LP = partnership; Scottish partnership/SL = corporate).
  - CQC provider `ownershipType` + `companiesHouseNumber` → legal form. An "Organisation" with no company number is unknown.
- Care vertical:
  - `verticals/care/linking.py`: CH company → CQC provider, by exact company number, else fuzzy name (+postcode).
  - `verticals/care/feeds.py`:
    - **new_companies**:
      - trigger: incorporation date;
      - `cqc_registered` yes (number) / possible (fuzzy) / no;
      - legal form and channel (phone unknown).
    - **never_inspected**:
      - qualifies: registered adult social care, with no rating in either framework, no `historicRatings`
        and no `lastInspection` date (live data showed a rated location with no `lastInspection`);
      - trigger: registration date, so weekly leads are **new registrations only**. `leads()` returns the full list
        for `never_inspected_all.csv` (M4). Dormant locations are included, flagged `dormant`.
    - **poor_ratings**:
      - qualifies: current rating Requires improvement or Inadequate;
      - trigger: rating + publication date, so a re-rating is a new lead;
      - previous rating from `historicRatings` (or the old `currentRatings`, for an assessment-framework rating),
        else from our snapshots;
      - `rating_change`: downgrade / first rating / no change / improved but still poor;
      - undated ratings are dated by when our snapshots first showed them.
  - Every CQC lead carries location, provider, contact, legal form, channel and profile URL fields for M4's CSV.
- `CqcLocation.overall_rating` now returns the **newer** of `currentRatings` and the assessment-framework rating.
  Previously `currentRatings` always won, which could hide a newer poor rating.
- CLI: `signals run [--week-ending YYYY-MM-DD] [--weeks N] [--no-sync] [--examples 5]`.
  It syncs first, records the leads, and prints per-feed counts, region counts and example leads. Files come in M4.
- 144 offline tests.

### Live check (2026-09-23, throwaway DB: Tower Hamlets + Hackney, 90 days)
- Backfill: 288 locations, 133 providers, 1,874 companies (435 calls). No parse failures.
- **Finding: formation-agent addresses.** 246 of 1,874 new care companies (13%) share a registered-office postcode
  with ≥ 5 others: LS25 2DY 50, WC2H 9JQ 44, EC1V 2NX 38, EC2A 4NA 28, N1 7GU 21, SL3 9LL 19.
  These are virtual offices, so their postcodes say nothing about where the business operates.
  Such companies are now flagged `shared_registered_office` and get **no customer region**. That cut the Hackney/Tower Hamlets
  new-company leads over 3 weeks from 32 to 12. (User to confirm; they could be listed as "location unknown" in M4.)
- Poor ratings: 9 current, 2 of them from the assessment framework. Previous ratings and downgrades came out right.
  "Inspected but not rated" appears as a historic rating value; its `rating_change` is "unknown".
- Never inspected: 50 in the two boroughs (8 dormant), some registered since 2019–2023.
- New companies linked to existing CQC providers: 0 of 1,874. That's expected, since new companies aren't registered yet.
- Observation: care SIC codes also catch children's services (Ofsted-regulated, not CQC) and recruitment firms,
  e.g. "OPEN ARMS CHILDRENS SERVICES LTD", "LICHT RECRUITMENT SERVICES LIMITED". Could be flagged by name in M4 if wanted.

### Real-data run (user's Mac, 2026-09-23: London + east-london, `run --weeks 4`)
- Sync after the backfill: nothing had changed yet (0 CQC changes, 169 Companies House records unchanged).
- Leads per week:

  | Week ending | New companies | New never inspected | New poor ratings |
  |---|---|---|---|
  | 30 Aug | 76 | 11 | 6 |
  | 6 Sep | 33 | 3 | 2 |
  | 13 Sep | 22 | 1 | 2 |
  | 20 Sep | 30 | 4 | 2 |

  The first week is larger because the 14-day grace window pulls in 10–23 Aug on a first run.
  Steady state is about 20–35 new companies, 1–4 never inspected and about 2 poor ratings a week.
- Currently qualifying: 1,118 never inspected (the full list, for `never_inspected_all.csv`), and 334 rated Requires improvement or Inadequate.
- Region tags look right, e.g. RM16 (Grays, Thurrock) is east-london only, and E6 is both.
- Noise seen in new_companies: children's homes (Ofsted, not CQC), e.g. "DIAMOND CUT CHILDRENS CARE HOME LTD",
  and recruitment firms, e.g. "KEMY SOLUTIONS RECRUITMENT LTD". Candidates for a name flag in M4.
- "Inspected but not rated" appears as a previous rating; M4 should word it more clearly.
- **Decision (user):** formation-agent / shared registered-office companies stay out of regional leads.
  I've proposed options for using them anyway, and am waiting on the user's choice:
  - (a) a separate national "location unknown" list;
  - (b) watch them: re-check the registered office (one Companies House call per company) and look for a CQC
    registration under the company number. When either gives a real address, it becomes a regional lead.
  - Not recommended: using director or PSC addresses, which is personal data.

## Milestone 2: SQLite store, snapshots, backfill and sync (done)

### Done
- `db/schema.py`, `db/store.py` (stdlib sqlite3, WAL, schema version in `PRAGMA user_version`):
  - `entities`: the latest sanitised payload per (source, entity_type, entity_id), with first seen, last fetched,
    last changed and `gone_at` (set on a 404).
  - `snapshots`: one row per **distinct** version. A new row is written only when the payload hash changes.
    `snapshot_as_of(t)` gives the week-on-week view the feeds need in milestone 3.
  - `sync_state` (cursors), `runs` (audit trail with stats), and `lead_events`, which is unique on
    (vertical, feed, entity_key, trigger_key) and gets filled in milestone 3.
  - `purge(before)`: deletes superseded snapshots, entities gone before the cutoff, old lead events and finished runs.
    It always keeps each live entity's current version.
- `core/regions.py`: `RegionMatcher` (a region matches on ANY of CQC region, local authority, postcode area/district)
  and postcode parsing. "E1" matches E1 and E1W but not E14; "EC1" matches EC1A.
- Source adapters `CqcSource` / `CompaniesHouseSource` turn API responses into `RawRecord`s. CQC payloads are
  sanitised (personal names stripped) **before** they reach the store.
- `verticals/care/collect.py`:
  - `CareScope`: region and LA regions use filtered CQC list queries. Postcode regions use the full adult social care
    list, filtered locally on `postalCode`. With no regions configured, or with `--all-england`, the scope is all of England.
  - `plan_backfill` makes list calls only and returns the in-scope IDs plus an estimate (calls and minutes).
  - `run_backfill` fetches:
    - every in-scope location's detail;
    - the provider of every **registered** location;
    - N days of care-SIC incorporations (all of England, filtered by region at output time).
    It then sets the cursors. It **resumes**: records fetched within `--fresh-hours` (default 24) are skipped.
    Each record commits as it's written. A failed record is logged, and the run carries on and is marked `partial`.
  - `run_sync`:
    - reads CQC changes since the cursor (national, IDs only) and fetches each changed location's detail;
    - keeps it if it's in scope or already tracked, and marks tracked 404s as gone;
    - fetches changed providers that are tracked, plus new providers of new locations;
    - re-reads Companies House incorporations with a 7-day overlap.
    The cursors only advance when there were no failures.
- CLI:
  - `signals init`;
  - `signals backfill [--days 90] [--dry-run] [--yes] [--all-england] [--fresh-hours 24]`, which prints the estimate and asks before fetching;
  - `signals sync`;
  - `signals purge [--older-than 365d]` (default `retention_days`).
- 111 offline tests, including a fake CQC API (`tests/fakes.py`) covering scope, resume, failures, sync and cursors.

### Live checks (2026-09-22)
- `backfill --dry-run` (66 list calls, 51 s): **7,705 in-scope locations** for the configured regions:
  - London: 7,492;
  - an extra 213 from the east-london postcode areas that lie outside CQC London, e.g. IG10 Loughton and RM16 Grays.
- Small end-to-end backfill on a throwaway DB, one local authority (Rutland): 52 locations, 22 providers
  (**0.42 providers per location**, close to the 0.4 used in the estimate), 180 companies, 75 CQC calls.
- Real weekly sync on that DB, with the cursor wound back 7 days:
  - 871 changed locations and 378 changed providers nationally, all fetched: 873 calls in 4 min 32 s (**0.31 s per call**);
  - 860 out of scope, and 11 were 404s for untracked IDs (now counted as `location_not_found`).
  - The estimate now assumes 0.3 s per CQC call.
- **Full backfill estimate (London + east-london, 90 days):**
  - CQC: 7,705 location details + about 3,100 provider details ≈ **10.8k calls, about 55 min** at 0.3 s each;
  - Companies House: about 13 calls.
- Weekly sync estimate: about 870 national location details + tracked providers ≈ **5 min**.

### Full backfill (user's device, 2026-09-23)
- The user ran `signals backfill --days 90` on their own machine; the DB lives there at `data/signals.db`.
  The cloud container is ephemeral and isn't used for the real database.
- Result in one run:
  - 7,707 CQC locations (the plan said 7,705);
  - 3,069 providers (0.40 per location, matching the estimate);
  - 1,874 care-SIC companies (90 days);
  - 12,650 snapshots, exactly one per record.
- Hosting advice given: build and run on the device for now, and move the single DB file to a small VPS with cron if
  unattended weekly runs are wanted. Vercel is unsuitable: function time limits, and no persistent disk for SQLite.
- Setup notes for a beginner user (Mac/Windows): download the branch ZIP, open Terminal in the project folder,
  install uv, `uv sync`, and create `.env` with `NAME=value` lines. The README (milestone 5) should cover these steps,
  including checking `.env` with `cut -d= -f1 .env`.

## Milestone 1: scaffold, config, API clients (done: both APIs verified live)

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

### Session 4 (2026-09-22): both APIs live
- The keys now come from environment variables (there is no `.env` in this container), and they are two different keys.
- **Companies House: working.** A 7-day care-SIC search returned 180 hits in 0.83 s. The sanitised fixture
  `tests/fixtures/companies_house/advanced_search.json` holds 5 items: company data only, with no officer names.
  A new test parses it. The CQC fixtures were re-captured unchanged, apart from timestamps, which were reverted.
- **`company_type` values, confirmed live.** 90 days of care-SIC incorporations: 1,876 companies, all `active`.
  - `ltd`: 1,724
  - `private-limited-guarant-nsc`: 147
  - `private-limited-guarant-nsc-limited-exemption`: 5
  - No `llp` appeared, but the synthetic fixture still covers it.
  - All three types are corporate subscribers for PECR.
- Companies House volume: 7 days ≈ 180 companies; 90 days took 15 calls with weekly slicing, well under a minute.

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
11. ✅ Live: Companies House `company_type` values for care SIC codes are `ltd`, `private-limited-guarant-nsc`
    and `private-limited-guarant-nsc-limited-exemption`. Search items have no officer or person fields.

### Open questions
- None blocking. The CQC rate limit is undocumented, so the default is 10 req/s until measured.

## Milestones
1. Scaffold + clients + smoke test: done (both APIs verified live)
2. SQLite schema, snapshots, backfill: done (full backfill run on the user's device)
3. Feeds + CH↔CQC matching + tests: done
4. CSV/HTML output, region filtering, `sample`: done (plus watching location-unknown companies)
5. README, scheduling, limitations, opt-outs, final PRIVACY_NOTES: done
