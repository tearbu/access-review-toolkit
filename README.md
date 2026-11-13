# Access Review Toolkit

Builds an **access-review worklist** by comparing application account exports against an HR roster — and flags the accounts a reviewer should look at first, instead of handing them an unfiltered spreadsheet. It catches the three findings that drive every entitlement-review campaign: orphaned accounts, dormant access, and a segregation-of-duties conflict.

## Why it matters

Periodic access reviews are a control auditors actually test (ISO 27001 A.5.15/A.8.2, SOC 2 CC6) — and a common source of findings, because reviews stall when reviewers get raw account dumps. The failures are predictable: people who left keep working accounts, unused access accumulates silently, and toxic role combinations hide in the finance system. This tool does the comparison work up front, so the campaign manager starts from a short, explained exception list rather than 18 undifferentiated rows.

Skills it demonstrates: identity and access management (IAM), user entitlement reviews, joiner/mover/leaver reconciliation against HR data, segregation-of-duties analysis, Python automation with the standard library only.

## How it works

Inputs:

- `data/hr-roster.csv` — employee, department, manager, status (`Active`/`Terminated`), termination date
- `data/app-users.csv` — application, username, employee, role, last login

Checks applied to every application account:

| Flag | Rule |
| --- | --- |
| `OrphanedAccount` | Employee is `Terminated` in the roster — or missing from it entirely |
| `DormantAccess` | No login in 90+ days as of `--as-of` |
| `SoDConflict` | The same employee holds both **Payments Create** and **Payments Approve** in FinanceApp — one person could create *and* approve a payment |

Outputs (into `output/`):

- `review-items.csv` — one row per account, with flags and a suggested reviewer action per flag (disable now, confirm need with manager, remove a conflicting role)
- `access-review-summary.md` — campaign summary: counts by flag and by application, plus the flagged-account list

## Run it

```bash
python3 src/access_review.py                 # bundled sample data, as-of 2026-11-12
python3 src/access_review.py --as-of 2027-02-01
python3 src/access_review.py --roster path/to/roster.csv --app-users path/to/accounts.csv
```

`--as-of` defaults to `2026-11-12` so demo output is deterministic. No dependencies — Python 3 standard library only.

## Sample output (actual run on the bundled data)

The sample set has 18 accounts across 3 applications (FinanceApp, HRSystem, VPN) for a 12-person fictional company — including two people who have left and one who never appears in HR's roster at all:

```text
Access review summary
  Accounts reviewed : 18
  Flagged accounts  : 7
  Clean accounts    : 11
    - OrphanedAccount : 2
    - DormantAccess   : 3
    - SoDConflict     : 2
```

| Application | Accounts | Flagged | Clean |
| --- | --- | --- | --- |
| FinanceApp | 6 | 5 | 1 |
| HRSystem | 5 | 1 | 4 |
| VPN | 7 | 1 | 6 |

Findings worth a second look in the detail file:

- A **terminated** finance user still holds **Payments Approve** — and logged in *after* his termination date. That's the first row a reviewer should escalate.
- An **Expense Reports** account belongs to someone who isn't in the HR roster at all (the classic contractor-account blind spot).
- The **SoD conflict** is one employee holding both Payments Create and Payments Approve — flagged on both role rows so the campaign summary counts 2 flagged accounts for 1 conflict.
- The 3 dormant accounts include a VPN user idle for 103 days and a finance read-only account idle for 145 days.

## Repository layout

```text
src/access_review.py   the review builder (single file, stdlib only)
data/hr-roster.csv     fictional HR roster: 12 employees, 2 terminated
data/app-users.csv     fictional accounts: 18 across 3 applications
output/                generated review-items.csv + summary (created on run)
```

## Limitations (honest ones)

- **Name matching is exact** (case/whitespace-normalized). Real HR-to-app reconciliation drowns in name variants, IDs, and contractors; a production tool would join on employee ID, not display name.
- **One hard-coded SoD rule.** Real SoD is a matrix per application, maintained with the business. The rule list at the top of the script is deliberately small and readable so it can be extended.
- **"Missing from roster" and "terminated" share one flag.** Both need disabling first and questions second, but a mature process would triage them separately.
- **It produces a worklist, not decisions.** Reviewers still have to confirm, revoke, and evidence the outcome — the tool doesn't write back to any application or ticketing system.

## Sample data

Every person, account, and date in `data/` is fictional. No real company's access data is represented.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Araf Abubakar.
