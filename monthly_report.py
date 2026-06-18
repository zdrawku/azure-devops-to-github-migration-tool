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
    python monthly_report.py --html report.html
"""

from __future__ import annotations

import argparse
import calendar
import html as html_mod
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv

load_dotenv()

SEARCH_URL = "https://api.github.com/search/issues"

PUBLIC_REPO  = "RevealBi/Reveal.Sdk"
PRIVATE_REPO = "Infragistics-BusinessTools/Reveal"

CRASH_PLATFORM_LABELS = ["Web", "WPF", "MacOS", "iOS", "Android"]


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


def search_issue_refs(repo: str, base_query: str, period: MonthRange,
                      date_field: str, limit: int = 8) -> dict:
    """Return issue references and a "view all" search URL for the given period query."""
    period_query = f"{base_query} {date_field}:{period.query_range()}"
    full_q = f"repo:{repo} is:issue {period_query}"
    headers = {
        "Authorization": f"Bearer {_token_for(repo)}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params = {
        "q": full_q,
        "per_page": max(1, min(limit, 100)),
        "sort": "updated" if date_field == "closed" else "created",
        "order": "desc",
    }

    payload = None
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
        payload = r.json()
        break

    if payload is None:
        raise RuntimeError(f"Search failed after retries: {full_q}")

    web_search_q = f"is:issue {period_query}"
    refs = [
        {
            "number": i.get("number"),
            "title": i.get("title"),
            "url": i.get("html_url"),
        }
        for i in payload.get("items", [])
    ]
    return {
        "total": payload.get("total_count", 0),
        "issues": refs,
        "search_url": f"https://github.com/{repo}/issues?q={quote_plus(web_search_q)}",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Metric helpers
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Metric:
    label: str
    current: int = 0
    previous: int = 0
    current_refs: dict = field(default_factory=dict)

    @property
    def delta(self) -> int:
        return self.current - self.previous

    def formatted(self) -> str:
        sign = "+" if self.delta >= 0 else "-"
        return f"{self.current} ({sign}{abs(self.delta)})"


@dataclass
class ReportSection:
    title: str
    url: str
    curr_label: str
    prev_label: str
    metrics: list[Metric] = field(default_factory=list)
    subsections: list[tuple[str, list[Metric]]] = field(default_factory=list)


def collect_metric(repo: str, label: str, base_query: str,
                   curr: MonthRange, prev: MonthRange,
                   date_field: str = "created") -> Metric:
    c = search_count(repo, f"{base_query} {date_field}:{curr.query_range()}")
    p = search_count(repo, f"{base_query} {date_field}:{prev.query_range()}")
    return Metric(label=label, current=c, previous=p)


def collect_metric_with_refs(repo: str, label: str, base_query: str,
                             curr: MonthRange, prev: MonthRange,
                             date_field: str = "created", ref_limit: int = 6) -> Metric:
    metric = collect_metric(repo, label, base_query, curr, prev, date_field)
    metric.current_refs = search_issue_refs(repo, base_query, curr, date_field, limit=ref_limit)
    return metric


# ──────────────────────────────────────────────────────────────────────────────
# Data collection
# ──────────────────────────────────────────────────────────────────────────────
def collect_public_sdk(curr: MonthRange, prev: MonthRange) -> ReportSection:
    section = ReportSection(
        title="Reveal SDK (Public) — Bugs & Features",
        url=f"https://github.com/{PUBLIC_REPO}/issues",
        curr_label=curr.label,
        prev_label=prev.label,
    )
    section.metrics = [
        collect_metric_with_refs(PUBLIC_REPO, "New bugs",     "type:Bug",     curr, prev, "created", ref_limit=6),
        collect_metric_with_refs(PUBLIC_REPO, "Closed bugs",  "type:Bug",     curr, prev, "closed", ref_limit=6),
        collect_metric(PUBLIC_REPO, "New feature requests",   "type:Feature", curr, prev, "created"),
        collect_metric(PUBLIC_REPO, "Closed feature requests","type:Feature", curr, prev, "closed"),
    ]
    return section


def collect_private_reveal(curr: MonthRange, prev: MonthRange) -> ReportSection:
    section = ReportSection(
        title="Reveal (Private) — Slingshot & Crash Reports",
        url=f"https://github.com/{PRIVATE_REPO}/issues",
        curr_label=curr.label,
        prev_label=prev.label,
    )
    section.metrics = [
        collect_metric(PRIVATE_REPO, "All new bugs (any label)", "type:Bug", curr, prev, "created"),
    ]

    # Crash Reports (label:"Crash Report")
    crash_q = 'type:Bug label:"Crash Report"'
    crash_metric = collect_metric(PRIVATE_REPO, "New Crash Reports",
                                  crash_q, curr, prev, "created")
    section.metrics.append(crash_metric)

    crash_platform_metrics = []
    for platform in CRASH_PLATFORM_LABELS:
        q = f'{crash_q} label:"{platform}"'
        crash_platform_metrics.append(
            collect_metric(PRIVATE_REPO, platform, q, curr, prev, "created")
        )
    section.subsections.append(("Crash Reports by platform", crash_platform_metrics))

    # Slingshot bugs (label:Slingshot, excluding Crash Report)
    slingshot_q = 'type:Bug label:Slingshot -label:"Crash Report"'
    slingshot_metric = collect_metric(PRIVATE_REPO, "New Slingshot Bugs",
                                     slingshot_q, curr, prev, "created")
    section.metrics.append(slingshot_metric)

    slingshot_platform_metrics = []
    for platform in CRASH_PLATFORM_LABELS:
        q = f'{slingshot_q} label:"{platform}"'
        slingshot_platform_metrics.append(
            collect_metric(PRIVATE_REPO, platform, q, curr, prev, "created")
        )
    section.subsections.append(("Slingshot Bugs by platform", slingshot_platform_metrics))
    return section


# ──────────────────────────────────────────────────────────────────────────────
# Summary / Dashboard metrics
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class SummaryCard:
    title: str
    total_open: int
    note: str
    curr_added: int
    curr_closed: int
    curr_delta: int
    prev_added: int
    prev_closed: int
    prev_delta: int
    curr_added_refs: dict = field(default_factory=dict)
    curr_closed_refs: dict = field(default_factory=dict)
    always_show_headline: bool = False


@dataclass
class PlatformCount:
    label: str
    count: int


def collect_summary(curr: MonthRange, prev: MonthRange) -> dict:
    """Collect dashboard summary: open counts + monthly added/closed for 3 KPI cards."""

    # Bugs excluding crash reports (open now)
    bugs_open = search_count(PRIVATE_REPO, 'is:open label:Slingshot type:Bug -label:"Crash Report"')
    bugs_curr_added = search_count(PRIVATE_REPO, f'type:Bug label:Slingshot -label:"Crash Report" created:{curr.query_range()}')
    bugs_curr_closed = search_count(PRIVATE_REPO, f'type:Bug label:Slingshot -label:"Crash Report" closed:{curr.query_range()}')
    bugs_prev_added = search_count(PRIVATE_REPO, f'type:Bug label:Slingshot -label:"Crash Report" created:{prev.query_range()}')
    bugs_prev_closed = search_count(PRIVATE_REPO, f'type:Bug label:Slingshot -label:"Crash Report" closed:{prev.query_range()}')

    bugs_card = SummaryCard(
        title="SLINGSHOT BUGS (EXCL. CRASH REPORTS)",
        total_open=bugs_open,
        note='label:Slingshot -label:"Crash Report" · Reveal private repo',
        curr_added=bugs_curr_added, curr_closed=bugs_curr_closed,
        curr_delta=bugs_curr_added - bugs_curr_closed,
        prev_added=bugs_prev_added, prev_closed=bugs_prev_closed,
        prev_delta=bugs_prev_added - bugs_prev_closed,
        curr_added_refs=search_issue_refs(PRIVATE_REPO, 'type:Bug label:Slingshot -label:"Crash Report"', curr, "created"),
        curr_closed_refs=search_issue_refs(PRIVATE_REPO, 'type:Bug label:Slingshot -label:"Crash Report"', curr, "closed"),
    )

    # Crash reports (open now)
    crash_open = search_count(PRIVATE_REPO, 'is:open type:Bug label:"Crash Report"')
    crash_curr_added = search_count(PRIVATE_REPO, f'type:Bug label:"Crash Report" created:{curr.query_range()}')
    crash_curr_closed = search_count(PRIVATE_REPO, f'type:Bug label:"Crash Report" closed:{curr.query_range()}')
    crash_prev_added = search_count(PRIVATE_REPO, f'type:Bug label:"Crash Report" created:{prev.query_range()}')
    crash_prev_closed = search_count(PRIVATE_REPO, f'type:Bug label:"Crash Report" closed:{prev.query_range()}')

    crash_card = SummaryCard(
        title="SLINGSHOT CRASH REPORTS",
        total_open=crash_open,
        note='label:"Crash Report" · Reveal private repo',
        curr_added=crash_curr_added, curr_closed=crash_curr_closed,
        curr_delta=crash_curr_added - crash_curr_closed,
        prev_added=crash_prev_added, prev_closed=crash_prev_closed,
        prev_delta=crash_prev_added - crash_prev_closed,
        curr_added_refs=search_issue_refs(PRIVATE_REPO, 'type:Bug label:"Crash Report"', curr, "created"),
        curr_closed_refs=search_issue_refs(PRIVATE_REPO, 'type:Bug label:"Crash Report"', curr, "closed"),
    )

    # All open slingshot issues
    all_open = search_count(PRIVATE_REPO, 'is:open label:Slingshot')
    all_curr_added = search_count(PRIVATE_REPO, f'label:Slingshot created:{curr.query_range()}')
    all_curr_closed = search_count(PRIVATE_REPO, f'label:Slingshot closed:{curr.query_range()}')
    all_prev_added = search_count(PRIVATE_REPO, f'label:Slingshot created:{prev.query_range()}')
    all_prev_closed = search_count(PRIVATE_REPO, f'label:Slingshot closed:{prev.query_range()}')

    all_card = SummaryCard(
        title="ALL OPEN SLINGSHOT ISSUES",
        total_open=all_open,
        note='label:Slingshot · all types (bugs, crash reports, features…)',
        curr_added=all_curr_added, curr_closed=all_curr_closed,
        curr_delta=all_curr_added - all_curr_closed,
        prev_added=all_prev_added, prev_closed=all_prev_closed,
        prev_delta=all_prev_added - all_prev_closed,
        curr_added_refs=search_issue_refs(PRIVATE_REPO, 'label:Slingshot', curr, "created"),
        curr_closed_refs=search_issue_refs(PRIVATE_REPO, 'label:Slingshot', curr, "closed"),
    )

    # All bugs in private repo regardless of label (new this month is the KPI)
    all_priv_curr_added = search_count(PRIVATE_REPO, f'type:Bug created:{curr.query_range()}')
    all_priv_curr_closed = search_count(PRIVATE_REPO, f'type:Bug closed:{curr.query_range()}')
    all_priv_prev_added = search_count(PRIVATE_REPO, f'type:Bug created:{prev.query_range()}')
    all_priv_prev_closed = search_count(PRIVATE_REPO, f'type:Bug closed:{prev.query_range()}')

    all_private_bugs_card = SummaryCard(
        title="ALL NEW BUGS · REVEAL (PRIVATE)",
        total_open=all_priv_curr_added,
        note='type:Bug · all labels · new this month vs prev month',
        curr_added=all_priv_curr_added, curr_closed=all_priv_curr_closed,
        curr_delta=all_priv_curr_added - all_priv_curr_closed,
        prev_added=all_priv_prev_added, prev_closed=all_priv_prev_closed,
        prev_delta=all_priv_prev_added - all_priv_prev_closed,
        curr_added_refs=search_issue_refs(PRIVATE_REPO, 'type:Bug', curr, "created"),
        curr_closed_refs=search_issue_refs(PRIVATE_REPO, 'type:Bug', curr, "closed"),
        always_show_headline=True,
    )

    # Crash reports by platform (currently open)
    crash_by_platform = []
    for platform in CRASH_PLATFORM_LABELS:
        count = search_count(PRIVATE_REPO, f'is:open type:Bug label:"Crash Report" label:"{platform}"')
        crash_by_platform.append(PlatformCount(label=platform, count=count))

    return {
        "bugs": asdict(bugs_card),
        "crash_reports": asdict(crash_card),
        "all_slingshot": asdict(all_card),
        "all_private_bugs": asdict(all_private_bugs_card),
        "crash_by_platform": [asdict(p) for p in crash_by_platform],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Text output
# ──────────────────────────────────────────────────────────────────────────────
def print_report(sections: list[ReportSection], curr: MonthRange, prev: MonthRange) -> None:
    print(f"📊 Monthly Reveal issue report — {curr.label}")
    print(f"   (comparison baseline: {prev.label})")

    for sec in sections:
        print(f"\n{sec.title} ({sec.url}):")
        print(f"  Window: {sec.curr_label}  (compared to {sec.prev_label})")
        for m in sec.metrics:
            print(f"  - {m.label:<25} - {m.formatted()}")
        for sub_title, sub_metrics in sec.subsections:
            print(f"    {sub_title}:")
            for m in sub_metrics:
                print(f"      - {m.label:<8} - {m.formatted()}")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# HTML output
# ──────────────────────────────────────────────────────────────────────────────
def delta_badge(metric: Metric) -> str:
    """Return an HTML badge for the delta."""
    if metric.delta > 0:
        cls = "badge up"
        text = f"+{metric.delta}"
    elif metric.delta < 0:
        cls = "badge down"
        text = f"{metric.delta}"
    else:
        cls = "badge neutral"
        text = "0"
    return f'<span class="{cls}">{html_mod.escape(text)}</span>'


def generate_html(sections: list[ReportSection], curr: MonthRange, prev: MonthRange) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows_html = ""
    for sec in sections:
        rows_html += f"""
        <div class="card">
          <h2><a href="{html_mod.escape(sec.url)}">{html_mod.escape(sec.title)}</a></h2>
          <p class="subtitle">{sec.curr_label} vs {sec.prev_label}</p>
          <table>
            <thead><tr><th>Metric</th><th>Count</th><th>Δ</th></tr></thead>
            <tbody>
"""
        for m in sec.metrics:
            rows_html += f"              <tr><td>{html_mod.escape(m.label)}</td><td>{m.current}</td><td>{delta_badge(m)}</td></tr>\n"

        for sub_title, sub_metrics in sec.subsections:
            rows_html += f'              <tr class="sub-header"><td colspan="3">{html_mod.escape(sub_title)}</td></tr>\n'
            for m in sub_metrics:
                rows_html += f"              <tr class='sub'><td>{html_mod.escape(m.label)}</td><td>{m.current}</td><td>{delta_badge(m)}</td></tr>\n"

        rows_html += """            </tbody>
          </table>
        </div>
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reveal Monthly Report — {html_mod.escape(curr.label)}</title>
<style>
  :root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #e6edf3;
           --muted: #8b949e; --green: #3fb950; --red: #f85149; --blue: #58a6ff; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
          background: var(--bg); color: var(--text); padding: 2rem; line-height: 1.5; }}
  h1 {{ margin-bottom: .25rem; }}
  .meta {{ color: var(--muted); margin-bottom: 2rem; font-size: .85rem; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px;
           padding: 1.5rem; margin-bottom: 1.5rem; }}
  .card h2 {{ font-size: 1.1rem; margin-bottom: .25rem; }}
  .card h2 a {{ color: var(--blue); text-decoration: none; }}
  .card h2 a:hover {{ text-decoration: underline; }}
  .subtitle {{ color: var(--muted); font-size: .85rem; margin-bottom: 1rem; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: .5rem .75rem; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 600; font-size: .8rem; text-transform: uppercase; }}
  tr.sub-header td {{ font-weight: 600; color: var(--muted); padding-top: 1rem; border-bottom: none; }}
  tr.sub td:first-child {{ padding-left: 1.5rem; }}
  .badge {{ display: inline-block; padding: .15rem .5rem; border-radius: 12px;
            font-size: .8rem; font-weight: 600; }}
  .badge.up {{ background: rgba(248,81,73,.15); color: var(--red); }}
  .badge.down {{ background: rgba(63,185,80,.15); color: var(--green); }}
  .badge.neutral {{ background: rgba(139,148,158,.15); color: var(--muted); }}
  @media (max-width: 600px) {{ body {{ padding: 1rem; }} }}
</style>
</head>
<body>
  <h1>📊 Reveal Monthly Report — {html_mod.escape(curr.label)}</h1>
  <p class="meta">Comparison baseline: {html_mod.escape(prev.label)} · Generated {generated}</p>
  {rows_html}
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# JSON output
# ──────────────────────────────────────────────────────────────────────────────
def generate_json(sections: list[ReportSection], curr: MonthRange, prev: MonthRange,
                   summary: dict | None = None) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {
        "generated": generated,
        "curr": curr.label,
        "prev": prev.label,
        "summary": summary,
        "sections": [
            {
                "title": sec.title,
                "url": sec.url,
                "metrics": [
                    {
                        "label": m.label,
                        "current": m.current,
                        "previous": m.previous,
                        "delta": m.delta,
                        "current_refs": m.current_refs,
                    }
                    for m in sec.metrics
                ],
                "subsections": [
                    {
                        "title": sub_title,
                        "metrics": [
                            {"label": m.label, "current": m.current, "previous": m.previous, "delta": m.delta}
                            for m in sub_metrics
                        ],
                    }
                    for sub_title, sub_metrics in sec.subsections
                ],
            }
            for sec in sections
        ],
    }
    return json.dumps(data, indent=2)


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
    ap.add_argument("--month", help="Target month as YYYY-MM (default: current month)")
    ap.add_argument("--html", metavar="FILE", help="Write HTML report to FILE")
    ap.add_argument("--json", metavar="FILE", help="Write JSON data to FILE (for GitHub Pages)")
    args = ap.parse_args()

    curr = parse_month(args.month)
    prev = previous_month(curr)

    sections = [
        collect_public_sdk(curr, prev),
        collect_private_reveal(curr, prev),
    ]

    summary = collect_summary(curr, prev)

    print_report(sections, curr, prev)

    if args.html:
        html_content = generate_html(sections, curr, prev)
        out_path = os.path.abspath(args.html)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"✅ HTML report written to {args.html}")

    if args.json:
        json_content = generate_json(sections, curr, prev, summary=summary)
        out_path = os.path.abspath(args.json)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json_content)
        print(f"✅ JSON data written to {args.json}")


if __name__ == "__main__":
    main()
