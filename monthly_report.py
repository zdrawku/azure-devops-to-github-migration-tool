"""
Monthly issue metrics for Reveal repositories.

Reports for the current month (vs. previous month) on:
  • RevealBi/Reveal.Sdk        — public bugs & feature requests
  • Infragistics-BusinessTools/Reveal — bugs and Slingshot/Crash reports

Counts are produced via the GitHub Search API using the same syntax as the
`gh issue list --search` CLI, e.g.:
    repo:RevealBi/Reveal.Sdk is:issue type:Bug created:2026-04-01..2026-04-30

Usage:
    python monthly_report.py
    python monthly_report.py --month 2026-04
"""

from __future__ import annotations

import argparse
import calendar
import os
import sys
import time
from dataclasses import dataclass
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()

SEARCH_URL = "https://api.github.com/search/issues"

PUBLIC_REPO  = "RevealBi/Reveal.Sdk"
PRIVATE_REPO = "Infragistics-BusinessTools/Reveal"

CRASH_PLATFORM_LABELS = ["Web", "WPF", "Mac", "iOS", "Android"]


# ──────────────────────────────────────────────────────────────────────────────
# Date helpers
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MonthRange:
    label: str       # "2026-04"
    start: date      # inclusive
    end: date        # inclusive

    def query_range(self) -> str:
        return f"{self.start.isoformat()}..{self.end.isoformat()}"


def month_range(year: int, month: int) -> MonthRange:
    last_day = calendar.monthrange(year, month)[1]
    return MonthRange(
        label=f"{year:04d}-{month:02d}",
        start=date(year, month, 1),
        end=date(year, month, last_day),
    )


def previous_month(mr: MonthRange) -> MonthRange:
    y, m = mr.start.year, mr.start.month
    if m == 1:
        return month_range(y - 1, 12)
    return month_range(y, m - 1)


# ──────────────────────────────────────────────────────────────────────────────
# GitHub Search
# ──────────────────────────────────────────────────────────────────────────────
def _token_for(repo: str) -> str:
    # GH_TOKEN (org PAT) usually works for both public and private repos.
    # Fall back to GH_TOKEN_PUBLIC_REVEAL only if the main token is missing.
    if repo == PUBLIC_REPO:
        tok = os.getenv("GH_TOKEN") or os.getenv("GH_TOKEN_PUBLIC_REVEAL")
    else:
        tok = os.getenv("GH_TOKEN")
    if not tok:
        sys.exit(f"❌ Missing GitHub token for {repo}")
    return tok


def search_count(repo: str, query: str) -> int:
    """Return the total_count from the Search API for the given query."""
    full_q = f"repo:{repo} is:issue {query}"
    headers = {
        "Authorization": f"Bearer {_token_for(repo)}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params = {"q": full_q, "per_page": 1}

    for attempt in range(5):
        r = requests.get(SEARCH_URL, headers=headers, params=params, timeout=30)
        if r.status_code == 403 and "rate limit" in r.text.lower():
            wait = int(r.headers.get("Retry-After", 30))
            print(f"⏳ Rate limited. Waiting {wait}s…")
            time.sleep(wait)
            continue
        if r.status_code == 422:
            raise RuntimeError(f"Invalid search query: {full_q}\n{r.text}")
        r.raise_for_status()
        return r.json().get("total_count", 0)
    raise RuntimeError(f"Search failed after retries: {full_q}")


# ──────────────────────────────────────────────────────────────────────────────
# Metric helpers
# ──────────────────────────────────────────────────────────────────────────────
def fmt_delta(curr: int, prev: int) -> str:
    diff = curr - prev
    sign = "+" if diff >= 0 else "-"
    return f"{curr} ({sign}{abs(diff)})"


def count_with_compare(repo: str, base_query: str, curr: MonthRange, prev: MonthRange,
                       date_field: str = "created") -> str:
    c = search_count(repo, f"{base_query} {date_field}:{curr.query_range()}")
    p = search_count(repo, f"{base_query} {date_field}:{prev.query_range()}")
    return fmt_delta(c, p)


# ──────────────────────────────────────────────────────────────────────────────
# Report sections
# ──────────────────────────────────────────────────────────────────────────────
def report_public_sdk(curr: MonthRange, prev: MonthRange) -> None:
    print(f"\nReveal SDK Public Bugs (https://github.com/{PUBLIC_REPO}/issues):")
    print(f"  Window: {curr.label}  (compared to {prev.label})")

    new_bugs     = count_with_compare(PUBLIC_REPO, "type:Bug",     curr, prev, "created")
    closed_bugs  = count_with_compare(PUBLIC_REPO, "type:Bug",     curr, prev, "closed")
    new_feats    = count_with_compare(PUBLIC_REPO, "type:Feature", curr, prev, "created")
    closed_feats = count_with_compare(PUBLIC_REPO, "type:Feature", curr, prev, "closed")

    print(f"  - New bugs              - {new_bugs}")
    print(f"  - Closed bugs           - {closed_bugs}")
    print(f"  - New feature requests  - {new_feats}")
    print(f"  - Closed feature requests - {closed_feats}")


def report_private_reveal(curr: MonthRange, prev: MonthRange) -> None:
    print(f"\nReveal Slingshot/Crash reports and bugs "
          f"(from https://github.com/{PRIVATE_REPO}/issues):")
    print(f"  Window: {curr.label}  (compared to {prev.label})")

    # New bugs (any Bug opened in window)
    new_bugs = count_with_compare(PRIVATE_REPO, "type:Bug", curr, prev, "created")
    print(f"  - New bugs since last month: {new_bugs}")

    # New crash reports / Slingshot — comma in label list = OR semantics in GH search
    crash_q = 'type:Bug label:"Crash Report","Slingshot"'
    new_crash = count_with_compare(PRIVATE_REPO, crash_q, curr, prev, "created")
    print(f"  - New Crash Reports since last month: {new_crash}")

    # Per-platform breakdown — AND of crash label + platform label
    for platform in CRASH_PLATFORM_LABELS:
        q = f'{crash_q} label:"{platform}"'
        line = count_with_compare(PRIVATE_REPO, q, curr, prev, "created")
        print(f"      - {platform:<8} - {line}")


# ──────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────────────
def parse_month(value: str | None) -> MonthRange:
    if not value:
        # Default to the current month (report is run at end of month)
        today = date.today()
        return month_range(today.year, today.month)
    try:
        y, m = value.split("-")
        return month_range(int(y), int(m))
    except Exception:
        sys.exit(f"❌ Invalid --month value '{value}'. Expected YYYY-MM.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--month", help="Target month as YYYY-MM (default: last month)")
    args = ap.parse_args()

    curr = parse_month(args.month)
    prev = previous_month(curr)

    print(f"📊 Monthly Reveal issue report — {curr.label}")
    print(f"   (comparison baseline: {prev.label})")

    report_public_sdk(curr, prev)
    report_private_reveal(curr, prev)
    print()


if __name__ == "__main__":
    main()
