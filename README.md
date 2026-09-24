# Signals engine: weekly care leads

Signals watches two UK public registers, the **Care Quality Commission (CQC)** and **Companies House**. Every
week it writes a digest of sales leads for each of your customer regions. It is built for CQC compliance
consultancies. Each digest lists:

| List | Who is in it | Why they may need help |
|---|---|---|
| **New poor ratings** | Care services newly rated *Requires improvement* or *Inadequate* | They need an action plan before CQC re-inspects |
| **Newly registered, not yet inspected** | Care services that just registered with CQC | Their first inspection is coming |
| **New care companies** | Companies just set up with a care activity code, based in your region | Most will need to register with CQC |
| **Now located in your region** | New companies (see next row) that have since moved here or registered with CQC here | As above, now with a known location |
| **Location unknown** (national) | New care companies registered at a formation agent's address | As above, for consultancies working nationally |

Each lead appears **once**, in the week it happens, and carries the contact rule you must follow (see
[Contact rules](#contact-rules-pecr)).

**Two folders.** The **code folder** is what you download; it can be deleted and replaced at any time. Everything
that is yours lives in a separate **Signals folder** in your home folder (`~/Signals`), which updating never
touches:

| In `~/Signals` | What it is |
|---|---|
| `keys.env` | Your API keys (readable only by you) |
| `signals.yaml` | Settings, including your customer regions |
| `data/` | The database |
| `outputs/` | The weekly digests and spreadsheets |
| `logs/` | Logs of the automatic weekly runs |

---

## Contents
1. [First-time setup](#1-first-time-setup-mac)
2. [Every week](#2-every-week)
3. [Run it automatically](#3-run-it-automatically-every-week)
4. [Your customer regions](#4-your-customer-regions)
5. [When someone opts out](#5-when-someone-opts-out)
6. [Updating to a new version](#6-updating-to-a-new-version)
7. [Troubleshooting](#7-troubleshooting)
8. [Command reference](#8-command-reference)
9. [How it works](#9-how-it-works)
10. [Limitations](#10-limitations)

In the instructions below, a grey box is something to type into **Terminal**. Paste **one line at a time**,
press **Enter**, and wait until you can type again before the next one.

---

## 1. First-time setup (Mac)

You need two free API keys:
- **CQC**: sign up at the [CQC API portal](https://api-portal.service.cqc.org.uk/). Your key is under **Profile**
  ("Primary key").
- **Companies House**: register at the [Companies House developer hub](https://developer.company-information.service.gov.uk/),
  create an application for the **Live** environment, and add a **REST** API key.

**Step 1: get the code.** On the GitHub page for this project, choose the right branch, click the green
**Code** button, then **Download ZIP**. Double-click the ZIP to unzip it.

**Step 2: put the folder in your home folder.** In Finder, choose **Go → Home**, then drag the unzipped folder
there. Do this rather than leaving it in Downloads, Desktop or Documents: macOS stops scheduled jobs from reading
those folders (see [step 3](#3-run-it-automatically-every-week)).

**Step 3: open Terminal in the folder.** Right-click the folder and choose **Services → New Terminal at Folder**.
If you can't see that option, switch it on under **System Settings → Keyboard → Keyboard Shortcuts… → Services →
Files and Folders**. To check you're in the right place, type `ls`: you should see `pyproject.toml` listed.

**Step 4: install uv** (it installs Python and everything else for you):
```
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Then **quit Terminal completely (Cmd + Q)**, and open it again in the folder as in step 3.

**Step 5: install the project:**
```
uv sync
```

**Step 6: create your Signals folder and add your keys:**
```
uv run signals setup
```
It creates `~/Signals` and asks for each key. Copy the key, paste it and press Enter. **Nothing appears on screen
while you paste; that's normal.** The keys are saved in `~/Signals/keys.env`, which only you can read. Never share
that file or paste your keys anywhere else.

**Step 7: check both APIs work:**
```
uv run signals smoke --n 5
```
It should end with **Smoke test OK**.

**Step 8: build the database.** This takes about an hour for London. First look at the estimate:
```
uv run signals backfill --dry-run
```
Then run it, keeping the Mac awake while it works:
```
caffeinate -i uv run signals backfill --days 90
```
Type `y` when asked. If it stops partway (sleep, Wi-Fi), run the same command again: it carries on from where
it stopped. The database is saved in `~/Signals/data/`. You only ever need to do this once.

---

## 2. Every week

```
uv run signals run
```
This does three things:
1. fetches everything that changed on both registers since last time (about 5 minutes);
2. records last week's leads (Monday to Sunday);
3. writes the digests.

It prints where it saved each one. To open the London digest, for example:
```
open ~/Signals/outputs/care/2026-09-20/london/digest.html
```
(Use the date it printed, which is the Sunday the week ended.) In Finder: **Go → Home → Signals → outputs → care**.

Each region's folder `~/Signals/outputs/care/<week>/<region>/` contains:

| File | What it is |
|---|---|
| `digest.html` | The digest: open it in any browser, print it, or save it as PDF |
| `poor_ratings.csv` | New poor ratings |
| `never_inspected.csv` | Newly registered, not yet inspected |
| `new_companies.csv` | New care companies in the region |
| `company_located.csv` | Formation-agent companies now located in the region |
| `location_unknown.csv` | New care companies at formation-agent addresses (national) |
| `never_inspected_all.csv` | **Every** never-inspected location in the region, not just this week's |

The `.csv` files open in Excel or Numbers: double-click them in Finder.

Other useful forms:
- `uv run signals run --weeks 4`: catch up on the last four weeks (oldest first).
- `uv run signals run --week-ending 2026-09-20`: redo a particular week. You get exactly the same files.
- `uv run signals sample --region london`: a four-week preview for one region, for example to show a prospective
  customer. It records nothing.

---

## 3. Run it automatically every week

Make sure the code folder is in your **home folder** (see setup step 2). Open Terminal in the code folder and run:
```
uv run signals schedule
```
It sets up a job for **Monday 07:00** and prints a `launchctl load -w …` command. Copy that command and run it
to switch the job on. For another time, use for example `uv run signals schedule --day sunday --hour 21`.

- If the Mac is **asleep** at that time, the job runs as soon as it wakes. If it is **switched off**, that week is
  skipped. Run `uv run signals run --weeks 2` to catch up.
- Each run also deletes data older than 12 months (`signals purge`).
- Everything is logged to `~/Signals/logs/weekly.log`.
- To switch it off, run the `launchctl unload -w …` command that `schedule` printed.

On a Linux server, `uv run signals schedule` prints a line to add with `crontab -e` instead.

---

## 4. Your customer regions

Regions live in `~/Signals/signals.yaml`. To open it:
```
open -e ~/Signals/signals.yaml
```
Each region gets its own digest. A region can use any mix of the settings below; a lead is included if it
matches **any** of them.

```yaml
regions:
  london:
    cqc_region: London                       # CQC's region name
  east-london:
    postcode_areas: [E, IG, RM]              # postcode areas (E) or districts (SE1, N16)
  kent-medway:
    local_authorities: [Kent, Medway]        # council names, as CQC spells them
    location_unknown: false                  # leave out the national "location unknown" list
```

CQC region names are: London, South East, South West, East, East Midlands, West Midlands,
Yorkshire & Humberside, North West, North East.

Keep the spacing exactly as shown: two spaces before each setting, and no tabs.

**After adding or widening a region**, fetch its care services once:
```
uv run signals backfill --dry-run --only-new
```
```
uv run signals backfill --only-new
```

---

## 5. When someone opts out

If a person or organisation asks not to be contacted, or asks for their data to be deleted, find their ID in a
CSV file:
- a **CQC location ID** or **CQC provider ID**, which looks like `1-123456789`;
- or a **company number**.

Then run:
```
uv run signals suppress 1-123456789 --note "asked not to be contacted, 1 Oct 2026"
```
- **What it does:** erases everything stored about them, and they are never stored or listed again.
  Suppressing a provider covers all its locations.
- **See the list:** `uv run signals suppress`.
- **Undo:** add `--remove` to the command above.
- **Files already written:** these are not changed. Delete them, or re-run those weeks.

---

## 6. Updating to a new version

Your keys, settings, database and digests are in `~/Signals`, so updating only replaces the code:

1. Drag your old **code folder** to the Bin. Don't touch the `Signals` folder.
2. Download the new ZIP, unzip it, and move the folder into your home folder, exactly where the old one was.
   Keep the same name, so the weekly schedule still finds it.
3. Open Terminal in the new code folder (right-click it, then **New Terminal at Folder**) and run:
   ```
   uv sync
   ```
   ```
   uv run signals setup
   ```
   `setup` just checks that everything is in place. It asks for nothing if your keys are already saved.

**Coming from an older version** that kept `data/` and `.env` inside the code folder? Run `uv run signals setup` in
that old folder **before** deleting it. It moves your database, digests and keys into `~/Signals` for you.

---

## 7. Troubleshooting

| Message | What to do |
|---|---|
| `command not found: uv` | Quit Terminal fully (Cmd + Q), reopen it in the folder, and try again. If it still fails, repeat setup step 4. |
| `No pyproject.toml found` | Terminal isn't in the project folder. Open it with **New Terminal at Folder**, and check that `ls` lists `pyproject.toml`. |
| `CQC_API_KEY is not set` | Run `uv run signals keys` and paste your keys again. |
| `returned HTTP 401` | The key is wrong or expired. Check you used the right key for each service, and the **Live** Companies House key. |
| `no sync cursor yet: run signals backfill first` | There's no database in `~/Signals/data/` yet. Build it first (setup step 8). |
| Yellow `failure(s); re-run to retry them` | A few records couldn't be fetched (network or API hiccup). Run the same command again. |
| The schedule never runs / `Operation not permitted` in `~/Signals/logs/weekly.log` | The code folder is inside Downloads, Desktop or Documents. Move it to your home folder, then run `schedule` and `launchctl load -w …` again. |
| Nothing happens on the Monday after an update | The code folder's name or place changed. Open Terminal in it and run `uv run signals schedule` and the `launchctl load -w …` line again. |

---

## 8. Command reference

All commands start with `uv run signals`. Add `--help` to any of them for details.

| Command | What it does |
|---|---|
| `setup` | Create `~/Signals`, move data from an older version, ask for missing keys. Safe to re-run |
| `keys` | Save or change your API keys (press Enter to keep a saved one) |
| `smoke --n 5` | Live check that both APIs and keys work |
| `init` | Create the database (optional: other commands do it) |
| `backfill [--dry-run] [--days 90] [--only-new]` | Build the baseline for your regions. Prints an estimate and asks before fetching |
| `sync` | Fetch changes since last time (`run` does this for you) |
| `run [--weeks N] [--week-ending DATE] [--no-sync] [--no-output]` | The weekly job: sync, record leads, write digests |
| `sample --region NAME [--weeks 4]` | Preview digest for one region. Records nothing |
| `suppress [ID] [--note …] [--remove]` | Opt-outs (see section 5) |
| `purge [--older-than 365d]` | Delete data and output folders past the retention period |
| `schedule [--day monday] [--hour 7]` | Set up the automatic weekly run |

---

## 9. How it works

- **Collection** (`backfill`, `sync`):
  - Every adult social care location in your regions, and its provider, is stored from the CQC API.
  - Each week, CQC's change feed says which records changed nationally, and the changed ones in your regions
    (or already tracked) are re-fetched.
  - New companies with care SIC codes (87100, 87200, 87300, 87900, 88100) come from Companies House advanced search.
  - Personal names (registered managers, nominated individuals) are removed before anything is stored.
- **Snapshots:** every record is kept with its history (a new version only when it changes), so changes such as a
  new rating can be detected week on week.
- **Feeds:** each list is a *feed* that finds its leads in the stored data. Every lead has a *trigger*, meaning
  what happened and when. A lead is recorded once, for the week its event falls in, with 14 days' grace for
  events published late. That is why re-running a week gives the same files.
- **Linking:**
  - Companies are matched to CQC providers by company number, or by similar name and postcode.
  - Regions for companies (which only have a postcode) are worked out from the CQC records near them.
  - Registered offices shared by five or more new care companies are treated as formation agents: see
    *Location unknown* and *Now located*.
- **Watching:** during each sync, formation-agent companies up to a year old have their Companies House record
  re-checked every four weeks, up to 300 per run. A move to a real address, or a CQC registration, makes them a
  regional lead.
- **Contact rules:** each lead's legal form comes from Companies House and CQC data, and sets its PECR contact
  rule.

Code layout, for developers: see `CLAUDE.md`. Tests: `uv run pytest` (offline, about 180 tests).

### Contact rules (PECR)

| Contact rule | Meaning |
|---|---|
| **email OK** | A corporate subscriber (company, LLP, public body). Marketing email is allowed, with an opt-out in every message. |
| **phone – check TPS/CTPS first** | Sole trader, partnership or unknown legal form with a phone number. Screen the number against TPS/CTPS before calling. |
| **post only** | Sole trader, partnership or unknown legal form with no phone number. |

See [PRIVACY_NOTES.md](PRIVACY_NOTES.md) for the data protection position.

---

## 10. Limitations

- **Coverage:** only adult social care in England (CQC's remit). Children's homes are regulated by Ofsted, and
  appear only as flagged new companies.
- **CQC change feed:** it lists only IDs, nationally. So each week every changed location in England is fetched
  (about 900 calls, 5 minutes) to find the ones in your regions.
- **Timing depends on CQC:** ratings appear when CQC publishes them, sometimes days after the report date (the
  14-day grace window covers this). Under CQC's newer assessment framework, fewer ratings are published each
  week than before.
- **New companies' contact details:** Companies House publishes no phone numbers or email addresses. Post to a
  formation agent may not be forwarded.
- **Formation-agent detection** is a rule of thumb: five or more new care companies at one postcode. A real
  shared office (a business centre) can be caught by it.
- **Company regions are inferred** from nearby CQC records. A postcode district with no care services in your
  regions can't be placed, so the company is left out.
- **Care SIC codes are broad:** some recruitment, training and children's-services companies get through. These
  are flagged "Check", not removed.
- **Fuzzy name matching** (company to CQC provider) is shown as "possible" and should be checked by a person.
- **`never_inspected_all.csv`** reflects the database when it is written, so unlike the weekly lists it can differ
  if a week is re-run later.
- **Companies House history** only goes back as far as the backfill (90 days by default), so samples and
  catch-up runs before then show no new companies.
- **The Mac must be on** (asleep is fine) for the scheduled run. For unattended use, run it on a small server:
  copy the project folder, including `data/`, and use the cron line from `schedule`.
- **Rate limits:** CQC's limit is undocumented, so the tool stays at 10 requests a second. Companies House
  allows 600 requests per 5 minutes.
