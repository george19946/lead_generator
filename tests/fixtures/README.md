# Test fixtures

Tests load these files and **never** call live APIs.

- `synthetic/`: hand-built records that follow the documented CQC and Companies House schemas.
  All names, IDs, phone numbers and addresses are invented. They cover edge cases that
  live samples may not contain (never inspected, a rating downgrade, sole trader, LLP).
- `cqc/`, `companies_house/`: real responses captured by `signals smoke --save-fixtures`,
  with personal names stripped (`regulatedActivities[].contacts`) and individual
  (sole-trader) provider names redacted.
