#!/usr/bin/env python3
"""
access_review.py - build an access-review worklist from an HR roster and
application account exports.

Access reviews (user entitlement reviews) fail in spreadsheets because
nobody flags the obvious problems up front. This tool compares every
application account against the HR roster and flags:

  * OrphanedAccount - the account's employee has left the company
    (roster status Terminated) or does not appear in the roster at all.
    These are the accounts that should already be disabled.
  * DormantAccess   - no login in 90+ days. Access nobody uses is access
    nobody needs - and a quiet target for attackers.
  * SoDConflict     - segregation-of-duties conflict. Concrete rule in
    this version: in the finance application, the same employee holds
    both the "Payments Create" and "Payments Approve" roles, meaning one
    person could create and approve the same payment.

Outputs:
  * review-items.csv      - one row per application account, with flags
                            and a suggested reviewer action.
  * access-review-summary.md - counts by flag and by application for the
                            review campaign manager.

Usage:
    python3 src/access_review.py
    python3 src/access_review.py --as-of 2026-11-12

Standard library only. Demo data is fictional.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

DEFAULT_AS_OF = "2026-11-12"
DORMANT_DAYS = 90

# One concrete segregation-of-duties rule:
# (application, role A, role B) - one employee must not hold both.
SOD_RULES = [("FinanceApp", "Payments Create", "Payments Approve")]

ACTIONS = {
    "OrphanedAccount": "Disable the account now and confirm removal with the application owner",
    "DormantAccess": "Confirm continued business need with the employee's manager; disable if unconfirmed",
    "SoDConflict": "Remove one of the conflicting roles or document a compensating control",
}


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def norm(name: str) -> str:
    return " ".join(name.strip().lower().split())


def find_sod_conflicts(app_users: list[dict]) -> set[str]:
    """Return normalized employee names that violate a SoD rule."""
    roles_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in app_users:
        roles_by_key[(row["application"], norm(row["employee"]))].add(row["role"])
    conflicts = set()
    for application, role_a, role_b in SOD_RULES:
        for (app, employee), roles in roles_by_key.items():
            if app == application and role_a in roles and role_b in roles:
                conflicts.add(employee)
    return conflicts


def review(
    roster: list[dict], app_users: list[dict], as_of: date
) -> list[dict]:
    roster_by_name = {norm(r["employee"]): r for r in roster}
    sod_conflicts = find_sod_conflicts(app_users)
    items = []
    for row in app_users:
        employee_key = norm(row["employee"])
        person = roster_by_name.get(employee_key)
        last_login = (
            date.fromisoformat(row["last_login"]) if row["last_login"] else None
        )
        days_since = (as_of - last_login).days if last_login else None

        flags: list[str] = []
        if person is None or person["status"].strip().lower() == "terminated":
            flags.append("OrphanedAccount")
        if days_since is None or days_since >= DORMANT_DAYS:
            flags.append("DormantAccess")
        for application, role_a, role_b in SOD_RULES:
            if (
                row["application"] == application
                and employee_key in sod_conflicts
                and row["role"] in (role_a, role_b)
            ):
                flags.append("SoDConflict")

        items.append(
            {
                "Application": row["application"],
                "Username": row["username"],
                "Employee": row["employee"],
                "Role": row["role"],
                "Last Login": row["last_login"] or "Never",
                "Days Since Login": days_since if days_since is not None else "",
                "Flags": "; ".join(flags),
                "Review Action": (
                    "; ".join(ACTIONS[f] for f in flags)
                    if flags
                    else "No action - access looks current"
                ),
            }
        )
    items.sort(key=lambda i: (i["Application"], i["Employee"], i["Role"]))
    return items


def build_summary(items: list[dict], as_of: date) -> tuple[str, Counter]:
    flag_counts: Counter = Counter()
    flagged_per_app: Counter = Counter()
    total_per_app: Counter = Counter()
    for item in items:
        total_per_app[item["Application"]] += 1
        flags = [f for f in item["Flags"].split("; ") if f]
        if flags:
            flagged_per_app[item["Application"]] += 1
        for f in flags:
            flag_counts[f] += 1
    flagged_total = sum(1 for i in items if i["Flags"])

    lines = [
        "# Access Review - Campaign Summary",
        "",
        f"- As-of date: {as_of}",
        f"- Accounts reviewed: {len(items)}",
        f"- Accounts with at least one flag: {flagged_total}",
        f"- Clean accounts: {len(items) - flagged_total}",
        "",
        "## Flags by type",
        "",
        "| Flag | Accounts | What it means |",
        "| --- | --- | --- |",
        f"| OrphanedAccount | {flag_counts.get('OrphanedAccount', 0)} | "
        "Employee terminated or missing from the HR roster |",
        f"| DormantAccess | {flag_counts.get('DormantAccess', 0)} | "
        f"No login in {DORMANT_DAYS}+ days |",
        f"| SoDConflict | {flag_counts.get('SoDConflict', 0)} | "
        "One employee holds both sides of a segregation-of-duties rule |",
        "",
        "## Accounts by application",
        "",
        "| Application | Accounts | Flagged | Clean |",
        "| --- | --- | --- | --- |",
    ]
    for app in sorted(total_per_app):
        total = total_per_app[app]
        flagged = flagged_per_app.get(app, 0)
        lines.append(f"| {app} | {total} | {flagged} | {total - flagged} |")
    lines += ["", "## Flagged accounts", ""]
    flagged_items = [i for i in items if i["Flags"]]
    if flagged_items:
        lines += [
            "| Application | Employee | Role | Last login | Flags |",
            "| --- | --- | --- | --- | --- |",
        ]
        for i in flagged_items:
            lines.append(
                f"| {i['Application']} | {i['Employee']} | {i['Role']} | "
                f"{i['Last Login']} | {i['Flags']} |"
            )
    else:
        lines.append("None. Every account passed the review checks.")
    lines.append("")
    return "\n".join(lines), flag_counts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Build an access-review worklist from an HR roster and app account exports."
    )
    parser.add_argument(
        "--roster", type=Path, default=root / "data" / "hr-roster.csv",
        help="HR roster CSV (default: bundled sample data).",
    )
    parser.add_argument(
        "--app-users", type=Path, default=root / "data" / "app-users.csv",
        help="Application accounts CSV (default: bundled sample data).",
    )
    parser.add_argument(
        "--as-of", default=DEFAULT_AS_OF, metavar="YYYY-MM-DD",
        help=f"'Today' for dormancy math (default: {DEFAULT_AS_OF}).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=root / "output",
        help="Where to write review-items.csv and access-review-summary.md.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    as_of = date.fromisoformat(args.as_of)
    try:
        roster = read_csv(args.roster)
        app_users = read_csv(args.app_users)
    except FileNotFoundError as exc:
        sys.exit(f"error: input file not found: {exc.filename}")

    items = review(roster, app_users, as_of)
    summary, flag_counts = build_summary(items, as_of)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    items_path = args.output_dir / "review-items.csv"
    with items_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(items[0].keys()))
        writer.writeheader()
        writer.writerows(items)
    summary_path = args.output_dir / "access-review-summary.md"
    summary_path.write_text(summary, encoding="utf-8")

    flagged_total = sum(1 for i in items if i["Flags"])
    print("Access review summary")
    print(f"  Accounts reviewed : {len(items)}")
    print(f"  Flagged accounts  : {flagged_total}")
    print(f"  Clean accounts    : {len(items) - flagged_total}")
    for flag in ("OrphanedAccount", "DormantAccess", "SoDConflict"):
        print(f"    - {flag:<16}: {flag_counts.get(flag, 0)}")
    print(f"\nWrote {items_path}")
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
