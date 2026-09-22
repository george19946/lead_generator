# Privacy notes

_Draft (milestone 1). To be finalised in milestone 5._

## What personal data is processed
The feeds target organisations, but some records contain personal data:

- **Sole traders and partnerships.** When a CQC provider is an individual or a partnership, the provider name
  (and its business address and phone number) identifies living people.
- **Registered managers and nominated individuals.** CQC records name these people. They are **not stored by
  default**: `regulatedActivities[].contacts` and other `person*` fields are removed before anything is written
  to the database. They are kept only if `include_personal_names: true` is set in `config/signals.yaml`.
- **Company records.** Companies House advanced-search results contain company data only. We don't fetch officer
  or PSC data.

We store only the fields the feeds need, plus raw snapshots (sanitised as above) for week-on-week comparison.

## Legal basis
Legitimate interests (UK GDPR Art. 6(1)(f)): identifying organisations that may need CQC compliance services
from public registers published for transparency. A legitimate interests assessment should be recorded before
commercial use.

## Retention
Snapshots, lead events and run records are kept for **12 months** by default (`retention_days: 365`).
`signals purge --older-than 365d` deletes older data. Run it as part of the weekly job.

## PECR and legal form
Under the Privacy and Electronic Communications Regulations, unsolicited marketing emails may be sent to
**corporate subscribers** (limited companies, LLPs, PLCs, Scottish partnerships, public bodies) without prior
consent, provided there is an opt-out. They may **not** be sent to **individual subscribers**: sole traders and
(non-Scottish) partnerships. Each lead therefore carries a legal-form flag and a suggested channel:

| Legal form | Suggested channel |
|---|---|
| Limited company / LLP / other corporate body | email OK |
| Sole trader / partnership / unknown, with phone | phone – check TPS/CTPS first |
| Sole trader / partnership / unknown, no phone | post only |

Calls to any number must first be screened against TPS/CTPS.

## Sources and attribution
- Contains CQC data © Care Quality Commission, licensed under the Open Government Licence v3.0.
- Contains Companies House data.
