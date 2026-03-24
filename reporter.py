"""
Migration progress reporter.

Reads local state files (state.json, state_node_ids.json,
migration_errors.json, migration.log) and produces a structured
progress + issue report with no API calls required by default.

When --fetch-totals is requested the ADO API is queried once to get the
official total work-item count, enabling accurate percentage completion.

Usage (via migrate.py):
    python migrate.py report                 # summary report
    python migrate.py report --detailed      # full issue lists
    python migrate.py report --fetch-totals  # include ADO total count
    python migrate.py report --detailed --fetch-totals
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ── File paths (mirrors migrate.py constants) ────────────────────────────────
STATE_FILE   = "state.json"
NODE_ID_FILE = "state_node_ids.json"
ERRORS_FILE  = "migration_errors.json"
LOG_FILE     = "migration.log"

# ── Log-line regex patterns ───────────────────────────────────────────────────
# Timestamp at the start of every log line
_RE_TS = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"

# Successfully migrated item (two formats: with and without "MIGRATED" prefix)
_RE_MIGRATED = re.compile(
    r"^" + _RE_TS + r"\s+INFO\s+(?:MIGRATED\s+)?ADO #(\d+) \u2192 GH #(\d+)"
)

# Batch / full-run start marker
_RE_RUN_START = re.compile(
    r"^" + _RE_TS + r"\s+INFO\s+=== (?P<kind>Migration|Batch) run started"
    r"(?: \(size=(?P<size>\d+)\))?"
    r" \u2014 (?P<pending>\d+) pending, (?P<already>\d+) already migrated"
)

# Batch / full-run complete marker
_RE_RUN_COMPLETE = re.compile(
    r"^" + _RE_TS + r"\s+INFO\s+=== (?:Migration|Batch) run complete"
    r" \u2014 success=(\d+)\s+failed=(\d+)"
)

# Failed item entry
_RE_ITEM_FAILED = re.compile(
    r"^" + _RE_TS + r"\s+ERROR\s+ADO #(\d+) FAILED \| (.+?) \| (.+)$"
)

# PR link warning
_RE_PR_FAILED = re.compile(
    r"^" + _RE_TS + r"\s+WARNING\s+\s*\u21b3 PR link (?:FAILED|exception): (.+?) \u2192 GH #(\d+)"
)

# Parent link warning variants
_RE_PARENT_LINK_FAILED = re.compile(
    r"^" + _RE_TS + r"\s+WARNING\s+\s*\u21b3 parent link FAILED: GH #(\d+) \(ADO #(\d+)\) \u2192 ADO #(\d+)"
)
_RE_PARENT_NEVER_MIGRATED = re.compile(
    r"^" + _RE_TS + r"\s+WARNING\s+PARENT-NEVER-MIGRATED\s+ADO #(\d+) \u2014 (\d+) child"
)
_RE_AUTO_PARENT_FAILED = re.compile(
    r"^" + _RE_TS + r"\s+WARNING\s+AUTO-MIGRATE PARENT FAILED\s+ADO #(\d+) \|.+\u2014 child ADO #(\d+)"
)
_RE_AUTO_PARENT_NOT_FOUND = re.compile(
    r"^" + _RE_TS + r"\s+WARNING\s+AUTO-MIGRATE PARENT NOT FOUND\s+ADO #(\d+) \(child: ADO #(\d+)\)"
)
_RE_DEFERRED_LINK_FAILED = re.compile(
    r"^" + _RE_TS + r"\s+WARNING\s+DEFERRED-LINK-FAILED\s+GH #(\d+) \u2192 parent ADO #(\d+)"
)


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class BatchRun:
    """Represents a single migrate run (full or batch) as parsed from the log."""
    kind: str                           # "Migration" or "Batch"
    start_time: str                     # ISO-like timestamp from log
    end_time: Optional[str]             # None if run was interrupted
    batch_size: Optional[int]           # only set for "multiple N" runs
    pending_at_start: int               # pending items when run began
    already_at_start: int               # already migrated when run began
    success_count: int                  # items successfully created
    failed_count: int                   # items that errored out


@dataclass
class PRLinkIssue:
    """A PR link that failed during migration."""
    timestamp: str
    pr_url: str
    gh_issue: str   # GitHub issue number as string


@dataclass
class ParentLinkIssue:
    """A parent-child relationship that could not be established."""
    timestamp: str
    error_type: str         # FAILED | NEVER-MIGRATED | AUTO-FAILED | NOT-FOUND | DEFERRED-FAILED
    parent_ado_id: str
    child_ado_id: str       # empty string when not determinable from log entry
    child_gh_issue: str     # empty string when not determinable
    detail: str             # free-text detail from the log line


@dataclass
class MigrationReport:
    generated_at: str

    # ── Progress counters ────────────────────────────────────────────────────
    total_ado_count: Optional[int]   # None unless --fetch-totals
    migrated_count: int
    failed_count: int

    # ── Detailed item maps ───────────────────────────────────────────────────
    migrated_items: dict[str, int]           # ado_id_str → gh_issue_number
    failed_items: dict[str, dict]            # ado_id_str → {title, error, timestamp}

    # ── Issue lists ─────────────────────────────────────────────────────────
    pr_link_issues: list[PRLinkIssue]
    parent_link_issues: list[ParentLinkIssue]

    # ── Batch history ────────────────────────────────────────────────────────
    batch_runs: list[BatchRun]

    # ── Derived helpers ──────────────────────────────────────────────────────
    @property
    def completion_pct(self) -> Optional[float]:
        if self.total_ado_count and self.total_ado_count > 0:
            return 100.0 * self.migrated_count / self.total_ado_count
        return None

    @property
    def pending_count(self) -> Optional[int]:
        if self.total_ado_count is not None:
            return self.total_ado_count - self.migrated_count
        return None


# ── Log parser ───────────────────────────────────────────────────────────────

def _parse_log(log_path: str) -> tuple[
    list[BatchRun],
    list[PRLinkIssue],
    list[ParentLinkIssue],
]:
    """
    Parses migration.log and extracts:
    - Batch run history (start/complete pairs)
    - PR link failures
    - Parent link failures
    """
    if not os.path.exists(log_path):
        return [], [], []

    batch_runs: list[BatchRun] = []
    pr_issues: list[PRLinkIssue] = []
    parent_issues: list[ParentLinkIssue] = []

    # We track open (unfinished) runs as we scan
    open_run: Optional[dict] = None
    # Track which PR issues we've already recorded to avoid duplicates
    seen_pr_issues: set[tuple[str, str]] = set()
    # Track which parent issues we've already recorded to avoid duplicates
    seen_parent_keys: set[tuple[str, str, str]] = set()

    with open(log_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip()
            if not line:
                continue

            # ── Batch/run start ──────────────────────────────────────────────
            m = _RE_RUN_START.match(line)
            if m:
                open_run = {
                    "kind": m.group("kind"),
                    "start_time": m.group(1),
                    "batch_size": int(m.group("size")) if m.group("size") else None,
                    "pending_at_start": int(m.group("pending")),
                    "already_at_start": int(m.group("already")),
                }
                continue

            # ── Batch/run complete ───────────────────────────────────────────
            m = _RE_RUN_COMPLETE.match(line)
            if m:
                if open_run:
                    batch_runs.append(BatchRun(
                        kind=open_run["kind"],
                        start_time=open_run["start_time"],
                        end_time=m.group(1),
                        batch_size=open_run["batch_size"],
                        pending_at_start=open_run["pending_at_start"],
                        already_at_start=open_run["already_at_start"],
                        success_count=int(m.group(2)),
                        failed_count=int(m.group(3)),
                    ))
                    open_run = None
                continue

            # ── PR link failure ──────────────────────────────────────────────
            m = _RE_PR_FAILED.match(line)
            if m:
                key = (m.group(2), m.group(3))   # (pr_url, gh_issue)
                if key not in seen_pr_issues:
                    seen_pr_issues.add(key)
                    pr_issues.append(PRLinkIssue(
                        timestamp=m.group(1),
                        pr_url=m.group(2),
                        gh_issue=m.group(3),
                    ))
                continue

            # ── Parent link FAILED ───────────────────────────────────────────
            m = _RE_PARENT_LINK_FAILED.match(line)
            if m:
                key = ("FAILED", m.group(3), m.group(4))
                if key not in seen_parent_keys:
                    seen_parent_keys.add(key)
                    parent_issues.append(ParentLinkIssue(
                        timestamp=m.group(1),
                        error_type="FAILED",
                        parent_ado_id=m.group(4),
                        child_ado_id=m.group(3),
                        child_gh_issue=m.group(2),
                        detail=f"GH #{m.group(2)} (ADO #{m.group(3)}) could not be linked to parent ADO #{m.group(4)}",
                    ))
                continue

            # ── Parent never migrated ────────────────────────────────────────
            m = _RE_PARENT_NEVER_MIGRATED.match(line)
            if m:
                key = ("NEVER-MIGRATED", m.group(2), "")
                if key not in seen_parent_keys:
                    seen_parent_keys.add(key)
                    parent_issues.append(ParentLinkIssue(
                        timestamp=m.group(1),
                        error_type="NEVER-MIGRATED",
                        parent_ado_id=m.group(2),
                        child_ado_id="",
                        child_gh_issue="",
                        detail=f"ADO #{m.group(2)} was never migrated — {m.group(3)} child issue(s) unlinked",
                    ))
                continue

            # ── Auto-migrate parent failed ───────────────────────────────────
            m = _RE_AUTO_PARENT_FAILED.match(line)
            if m:
                key = ("AUTO-FAILED", m.group(2), m.group(3))
                if key not in seen_parent_keys:
                    seen_parent_keys.add(key)
                    parent_issues.append(ParentLinkIssue(
                        timestamp=m.group(1),
                        error_type="AUTO-FAILED",
                        parent_ado_id=m.group(2),
                        child_ado_id=m.group(3),
                        child_gh_issue="",
                        detail=f"Auto-migration of parent ADO #{m.group(2)} failed (child ADO #{m.group(3)})",
                    ))
                continue

            # ── Auto-migrate parent not found ────────────────────────────────
            m = _RE_AUTO_PARENT_NOT_FOUND.match(line)
            if m:
                key = ("NOT-FOUND", m.group(2), m.group(3))
                if key not in seen_parent_keys:
                    seen_parent_keys.add(key)
                    parent_issues.append(ParentLinkIssue(
                        timestamp=m.group(1),
                        error_type="NOT-FOUND",
                        parent_ado_id=m.group(2),
                        child_ado_id=m.group(3),
                        child_gh_issue="",
                        detail=f"Parent ADO #{m.group(2)} not found in ADO (child: ADO #{m.group(3)})",
                    ))
                continue

            # ── Deferred link failed ─────────────────────────────────────────
            m = _RE_DEFERRED_LINK_FAILED.match(line)
            if m:
                key = ("DEFERRED-FAILED", m.group(3), m.group(2))
                if key not in seen_parent_keys:
                    seen_parent_keys.add(key)
                    parent_issues.append(ParentLinkIssue(
                        timestamp=m.group(1),
                        error_type="DEFERRED-FAILED",
                        parent_ado_id=m.group(3),
                        child_ado_id="",
                        child_gh_issue=m.group(2),
                        detail=f"Deferred parent link for GH #{m.group(2)} → parent ADO #{m.group(3)} failed",
                    ))
                continue

    # If there's an open run (process was interrupted), record it without an end time
    if open_run:
        batch_runs.append(BatchRun(
            kind=open_run["kind"],
            start_time=open_run["start_time"],
            end_time=None,
            batch_size=open_run["batch_size"],
            pending_at_start=open_run["pending_at_start"],
            already_at_start=open_run["already_at_start"],
            success_count=0,
            failed_count=0,
        ))

    return batch_runs, pr_issues, parent_issues


# ── Data collection ──────────────────────────────────────────────────────────

def collect_report_data(fetch_totals: bool = False) -> MigrationReport:
    """
    Builds a ``MigrationReport`` from local state files.

    Args:
        fetch_totals: When True, queries ADO once for the official total
                      work-item count.  Requires ADO_PAT to be set.
    """
    # ── State files ──────────────────────────────────────────────────────────
    migrated_items: dict[str, int] = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as fh:
            raw = json.load(fh)
            migrated_items = {str(k): int(v) for k, v in raw.items()}

    failed_items: dict[str, dict] = {}
    if os.path.exists(ERRORS_FILE):
        with open(ERRORS_FILE, encoding="utf-8") as fh:
            raw = json.load(fh)
            failed_items = {str(k): v for k, v in raw.items()}

    # ── Log parsing ──────────────────────────────────────────────────────────
    batch_runs, pr_issues, parent_issues = _parse_log(LOG_FILE)

    # ── Optional ADO total ───────────────────────────────────────────────────
    total_ado_count: Optional[int] = None
    if fetch_totals:
        try:
            from clients.ado_client import count_work_items_by_type
            total, _ = count_work_items_by_type()
            total_ado_count = total
        except Exception as exc:
            print(f"  [WARN] Could not fetch ADO total: {exc}")

    return MigrationReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        total_ado_count=total_ado_count,
        migrated_count=len(migrated_items),
        failed_count=len(failed_items),
        migrated_items=migrated_items,
        failed_items=failed_items,
        pr_link_issues=pr_issues,
        parent_link_issues=parent_issues,
        batch_runs=batch_runs,
    )


# ── Formatters ───────────────────────────────────────────────────────────────

def _section(title: str, width: int = 64) -> None:
    print()
    print("─" * width)
    print(f"  {title}")
    print("─" * width)


def _progress_bar(pct: float, width: int = 30) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct:.1f}%"


def print_report(report: MigrationReport, *, detailed: bool = False) -> None:
    """
    Prints the migration report to stdout.

    Args:
        report:   The ``MigrationReport`` to display.
        detailed: When True, prints full item-level lists for issues.
    """
    W = 64
    print()
    print("=" * W)
    print("  ADO → GitHub Migration Progress Report")
    print(f"  Generated: {report.generated_at}")
    print("=" * W)

    # ── Overall progress ─────────────────────────────────────────────────────
    _section("OVERALL PROGRESS", W)
    print(f"  Migrated  : {report.migrated_count:>6,}")
    if report.total_ado_count is not None:
        pct = report.completion_pct or 0.0
        print(f"  Total     : {report.total_ado_count:>6,}")
        print(f"  Pending   : {report.pending_count:>6,}")
        print(f"  Progress  : {_progress_bar(pct)}")
    else:
        print("  Total     :        (run with --fetch-totals to include ADO total)")
    print(f"  Failed    : {report.failed_count:>6,}  (in {ERRORS_FILE})")

    # ── Batch run history ────────────────────────────────────────────────────
    if report.batch_runs:
        _section(f"BATCH RUN HISTORY  ({len(report.batch_runs)} run(s))", W)
        for i, run in enumerate(report.batch_runs, 1):
            kind_label = f"{run.kind} run"
            if run.batch_size:
                kind_label += f" (batch={run.batch_size})"
            end_label = run.end_time if run.end_time else "⚠  interrupted"
            print(f"  [{i:>2}] {kind_label}")
            print(f"        Start   : {run.start_time}")
            print(f"        End     : {end_label}")
            print(f"        Pending at start : {run.pending_at_start:,} "
                  f"(already done: {run.already_at_start:,})")
            if run.end_time:
                print(f"        Result  : ✅ {run.success_count}  ❌ {run.failed_count}")
            print()

    # ── Failed items ─────────────────────────────────────────────────────────
    _section(f"FAILED ITEMS  ({report.failed_count})", W)
    if report.failed_count == 0:
        print("  ✅ No failed items.")
    else:
        if detailed:
            print(f"  {'ADO ID':<10} {'Timestamp':<20} {'Error'}")
            print(f"  {'─'*9} {'─'*19} {'─'*30}")
            for ado_id, info in sorted(report.failed_items.items(), key=lambda x: int(x[0])):
                ts  = info.get("timestamp", "")[:19]
                err = info.get("error", "")[:60]
                title = info.get("title", "")[:45]
                print(f"  ADO #{ado_id:<7} {ts}  {title}")
                print(f"  {'':11} {'':20} ↳ {err}")
        else:
            print(f"  {report.failed_count} item(s) need attention. "
                  "Run with --detailed to see the full list.")
            print(f"  Quick view: open {ERRORS_FILE}")

    # ── PR link issues ───────────────────────────────────────────────────────
    unique_pr_issues = report.pr_link_issues
    _section(f"PR / BRANCH LINK ISSUES  ({len(unique_pr_issues)})", W)
    if not unique_pr_issues:
        print("  ✅ No PR link failures detected in the log.")
    else:
        print("  These Development-section links could not be established:")
        print()
        if detailed:
            for issue in unique_pr_issues:
                print(f"  GH Issue #  : {issue.gh_issue}")
                print(f"  PR URL      : {issue.pr_url}")
                print(f"  Detected at : {issue.timestamp}")
                print()
        else:
            print(f"  {len(unique_pr_issues)} PR link(s) failed. "
                  "Run with --detailed to see URLs.")
            print()
            # Always show the distinct GH issue numbers for easy filtering
            gh_issues = sorted({i.gh_issue for i in unique_pr_issues}, key=lambda x: int(x) if x.isdigit() else 0)
            print(f"  Affected GitHub issues: {', '.join(f'#{n}' for n in gh_issues)}")

    # ── Parent link issues ───────────────────────────────────────────────────
    unique_parent_issues = report.parent_link_issues
    _section(f"PARENT / HIERARCHY LINK ISSUES  ({len(unique_parent_issues)})", W)
    if not unique_parent_issues:
        print("  ✅ No parent link issues detected in the log.")
    else:
        # Group by error type for clarity
        by_type: dict[str, list[ParentLinkIssue]] = {}
        for issue in unique_parent_issues:
            by_type.setdefault(issue.error_type, []).append(issue)

        type_labels = {
            "NEVER-MIGRATED":  "Parent never migrated (children are unlinked)",
            "FAILED":          "Parent link API call failed",
            "AUTO-FAILED":     "Auto-migration of parent failed",
            "NOT-FOUND":       "Parent ADO item not found",
            "DEFERRED-FAILED": "Deferred parent link failed",
        }

        for etype, issues in by_type.items():
            label = type_labels.get(etype, etype)
            print(f"\n  [{etype}]  {label}  ({len(issues)} item(s))")
            if detailed:
                for issue in issues:
                    print(f"    • {issue.detail}")
                    print(f"      Detected at: {issue.timestamp}")
            else:
                parent_ids = sorted({i.parent_ado_id for i in issues if i.parent_ado_id},
                                     key=lambda x: int(x) if x.isdigit() else 0)
                if parent_ids:
                    print(f"    Parent ADO IDs: {', '.join(f'#{p}' for p in parent_ids)}")

    # ── Action checklist ──────────────────────────────────────────────────────
    issues_found = (
        report.failed_count > 0
        or len(unique_pr_issues) > 0
        or len(unique_parent_issues) > 0
    )
    if issues_found:
        _section("ACTION CHECKLIST", W)
        if report.failed_count > 0:
            print(f"  ☐  Re-run failed items:")
            print(f"       Review {ERRORS_FILE}, fix root causes, then re-run.")
            print(f"       Individual items can be re-run with:")
            print(f"         python migrate.py single <ADO_ID>")
        if unique_pr_issues:
            print(f"  ☐  Fix PR / Development section links:")
            print(f"       Check ADO_GITHUB_CONNECTION_MAP in config.py and ensure")
            print(f"       all GitHub connection GUIDs are mapped to their repos.")
            print(f"       Then re-run the affected items using migrate.py single.")
        if unique_parent_issues:
            print(f"  ☐  Fix parent hierarchy links:")
            if any(i.error_type == "NEVER-MIGRATED" for i in unique_parent_issues):
                print(f"       Some parent items were never migrated. Migrate them first")
                print(f"       with 'python migrate.py single <PARENT_ADO_ID>', then")
                print(f"       re-run the child items to establish the parent link.")
            if any(i.error_type in ("FAILED", "DEFERRED-FAILED") for i in unique_parent_issues):
                print(f"       Some parent links failed at the API level. Check that the")
                print(f"       GH_TOKEN has project write permissions, then re-run.")

    # ── Footer ───────────────────────────────────────────────────────────────
    print()
    print("=" * W)
    print(f"  State file  : {STATE_FILE}  ({report.migrated_count} migrated)")
    print(f"  Error file  : {ERRORS_FILE}  ({report.failed_count} failed)")
    print(f"  Full log    : {LOG_FILE}")
    print(f"  Tip: Use --detailed for full item lists, "
          "--fetch-totals for ADO count.")
    print("=" * W)
    print()


# ── Top-level entry point ─────────────────────────────────────────────────────

def generate_report(*, detailed: bool = False, fetch_totals: bool = False) -> MigrationReport:
    """
    Collects data from local state files and prints a migration report.

    Args:
        detailed:     Print full item-level lists inside each issue section.
        fetch_totals: Query ADO for the official total work-item count.

    Returns:
        The populated ``MigrationReport`` instance (useful for programmatic use).
    """
    report = collect_report_data(fetch_totals=fetch_totals)
    print_report(report, detailed=detailed)
    return report
