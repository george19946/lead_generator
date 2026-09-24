# Privacy notes

These notes describe what personal data the Signals engine processes, and the controls built into it. They are
a practical summary to help you meet UK GDPR and PECR, **not legal advice**. Have them checked before selling
leads commercially.

## 1. What personal data is processed

The leads are organisations, but some records identify living people:

| Data | Source | Personal data? | What the tool does |
|---|---|---|---|
| Sole-trader and partnership providers: name, business address, phone | CQC | **Yes**, the provider name is a person's name | Stored and shown in leads (needed to use the lead). Removable on request (section 5). |
| Registered managers, nominated individuals (`contacts`, `nominatedIndividual`, `person*` fields) | CQC | Yes | **Removed before anything is stored.** Kept only if `include_personal_names: true` is set in `config/signals.yaml` (off by default; don't switch it on without a documented reason). |
| Company names, numbers, registered offices, SIC codes | Companies House | Usually not (a company name can contain a person's name) | Stored and shown. |
| Company officers, directors, persons with significant control | Companies House | Yes | **Never fetched.** Directors' addresses are not used to place companies either. |
| Care service names, addresses, phone numbers, websites, ratings | CQC | Not for organisations | Stored and shown. |

No special category data is processed. Ratings concern services, not individuals.

## 2. Where it is kept

Everything lives in the **Signals folder**, `~/Signals` on the machine that runs the tool, kept apart from the code:

- **`data/signals.db`** (SQLite) holds:
  - the latest version of each record, plus earlier versions when a record changed;
  - the recorded leads;
  - sync positions;
  - a log of runs;
  - the opt-out list.
- **`outputs/`** holds the digests (HTML) and CSVs per week and region, and samples.
- **`logs/weekly.log`** holds the output of scheduled runs. It includes counts, and at most a few example lead
  names.
- **`keys.env`** holds the API keys, readable only by the user's account. The keys are never committed, printed
  or logged.

Recommended:
- keep the computer's disk encrypted (FileVault on a Mac);
- don't sync the Signals folder to a shared drive;
- send digests to customers through a secure channel rather than as plain email attachments, where
  sole-trader data is included.

## 3. Legal basis and transparency

- **Legal basis:** legitimate interests (UK GDPR Art. 6(1)(f)). The purpose is identifying care organisations that
  may need CQC compliance services, from registers published for transparency.
  - **Record a legitimate interests assessment** before commercial use.
  - It should cover sole traders in particular: their reasonable expectations, the minimal data used, and the
    easy opt-out.
- **Transparency (Art. 14):**
  - The data is not collected from the people it is about.
  - Publish a privacy notice (on your website) that covers the sources (CQC, Companies House), the purpose,
    who receives the leads, retention, and how to object.
  - Include a short version, or a link to it, in the first contact with any lead.
- **Recipients:** customers who receive digests use the leads for their own marketing, so they become
  controllers of that data.
  - Your contract with them should require PECR compliance, honouring objections, and passing opt-outs back
    to you so you can suppress the person centrally (section 5).

## 4. Retention

- **Default: 12 months** (`retention_days: 365` in `config/signals.yaml`).
- `signals purge` deletes, for anything older than that:
  - earlier versions of records, keeping each live record's current version;
  - records that disappeared from their register;
  - recorded leads and run logs;
  - output folders (weekly digests and samples).
- The scheduled weekly job runs `purge` after every run.
- `logs/weekly.log` is not purged automatically. Delete it from time to time.

## 5. Objections and erasure requests

When anyone asks not to be contacted, or asks for their data to be deleted:

```
uv run signals suppress <ID> --note "what they asked, and when"
```

- **The ID:** a CQC location or provider ID, or a company number, from any of the CSVs.
- **What it does:**
  - immediately erases every stored version of the record and every lead recorded for it;
  - for a provider, it also covers all its locations;
  - it adds the ID to a permanent opt-out list, so the record is never stored or listed again, even though it
    stays on the public register.
- **Keep the ID on the list.** Removing it (`--remove`) means the person can reappear.
- **Files already written** to `outputs/`, or already sent to customers, are not changed. Delete or regenerate
  them, and tell customers who received the lead.

Access requests can be answered from the CSVs (search for the name or ID), because the tool holds nothing about
a person beyond what the digests show.

## 6. PECR and legal form

Under PECR, unsolicited marketing emails may be sent to **corporate subscribers** without prior consent, with an
opt-out in every message. Corporate subscribers are limited companies, LLPs, PLCs, Scottish partnerships and
public bodies. They may **not** be sent to **individual subscribers**: sole traders and (non-Scottish)
partnerships. Every lead carries a legal form and a contact rule:

| Legal form (from Companies House type or number, or CQC ownership) | Contact rule |
|---|---|
| Limited company, LLP, other corporate body, public body | **email OK** |
| Sole trader, partnership or unknown, with a phone number | **phone – check TPS/CTPS first** |
| Sole trader, partnership or unknown, no phone number | **post only** |

- **Unknown legal form:** treated with the stricter rule. For example, a CQC "Organisation" with no company
  number may be an unincorporated charity.
- **Phone calls:** screen every number against **TPS/CTPS** before calling, including corporate numbers
  (CTPS).
- **Where email addresses come from:** the tool provides none; they come from organisations' own websites.

## 7. Sources and attribution

- Contains CQC data © Care Quality Commission, licensed under the Open Government Licence v3.0.
- Contains Companies House data.

Both lines appear at the foot of every digest.
