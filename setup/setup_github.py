"""
Run this script ONCE before migration to set up labels and milestones
in the GitHub repository.

  python setup/setup_github.py           # create labels + milestones
  python setup/setup_github.py verify    # check which required labels are missing
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from clients.github_client import create_label, create_milestone, list_labels
from clients.ado_client import get_iterations
from config import (
    WORK_ITEM_TYPE_LABELS,
    PRIORITY_LABELS,
    SEVERITY_LABELS,
    TRIAGE_LABELS,
    STATE_LABELS,
)

# ── Label definitions: (name, hex_color, description) ────────────────────────
# Names MUST match what mapper.py emits (type: prefix, priority: prefix, etc.)
LABELS_TO_CREATE = [
    # ── Work item types (mapper.resolve_github_type adds "type: " prefix) ──
    ("type: bug",        "d73a4a", "ADO Bug"),
    ("type: task",       "0075ca", "ADO Task"),
    ("type: feature",    "a2eeef", "ADO Feature / User Story"),
    ("type: epic",       "d876e3", "ADO Epic"),
    ("type: backlog",    "f9d0c4", "ADO Product Backlog Item"),
    ("type: ado-issue",  "ee0701", "ADO Issue type"),
    ("type: test-case",  "bfd4f2", "ADO Test Case"),
    ("type: test-plan",  "c5def5", "ADO Test Plan"),
    ("type: test-suite", "c2e0c6", "ADO Test Suite"),
    ("type: impediment", "e11d48", "ADO Impediment"),
    # ── Priorities ──────────────────────────────────────────────────────────
    ("priority: critical", "b60205", "Critical priority"),
    ("priority: high",     "d93f0b", "High priority"),
    ("priority: medium",   "fbca04", "Medium priority"),
    ("priority: low",      "0e8a16", "Low priority"),
    # ── Severities ──────────────────────────────────────────────────────────
    ("severity: critical", "b60205", "Severity: Critical"),
    ("severity: high",     "d93f0b", "Severity: High"),
    ("severity: medium",   "fbca04", "Severity: Medium"),
    ("severity: low",      "0e8a16", "Severity: Low"),
    # ── Triage ──────────────────────────────────────────────────────────────
    ("triage: pending",        "e4e669", "Triage: Pending"),
    ("triage: info-received",  "fef2c0", "Triage: Info Received"),
    ("triage: triaged",        "0e8a16", "Triage: Triaged"),
    # ── States ──────────────────────────────────────────────────────────────
    ("state: new",         "ededed", "ADO State: New"),
    ("state: open",        "ededed", "ADO State: Open"),
    ("state: active",      "1d76db", "ADO State: Active"),
    ("state: in-progress", "0052cc", "ADO State: In Progress"),
    ("state: resolved",    "0e8a16", "ADO State: Resolved"),
    ("state: removed",     "b60205", "ADO State: Removed"),
    # ── Source marker ───────────────────────────────────────────────────────
    ("migrated-from-ado",  "f1e05a", "Migrated from Azure DevOps"),
]

# The full set of label names that migration will try to apply to issues.
# Built from config at import time so it always stays in sync.
_REQUIRED_LABELS: set[str] = (
    {f"type: {v}" for v in WORK_ITEM_TYPE_LABELS.values()}
    | set(PRIORITY_LABELS.values())
    | set(SEVERITY_LABELS.values())
    | set(TRIAGE_LABELS.values())
    | {v for v in STATE_LABELS.values() if v != "closed"}
    | {"migrated-from-ado"}
)


def setup_labels():
    """
    Creates every label in LABELS_TO_CREATE that does not yet exist in the repo.
    Labels already present are left unchanged and reported as such.
    """
    print("🏷️  Fetching existing GitHub labels...")
    existing = set(list_labels())
    print(f"   {len(existing)} label(s) already in the repo.\n")

    to_create = [(n, c, d) for n, c, d in LABELS_TO_CREATE if n not in existing]
    already   = [n          for n, _, _ in LABELS_TO_CREATE if n in existing]

    if already:
        print(f"🏷️  Skipping {len(already)} label(s) that already exist:")
        for name in already:
            print(f"   [exists] {name}")
        print()

    if to_create:
        print(f"🏷️  Creating {len(to_create)} missing label(s):")
        for name, color, desc in to_create:
            create_label(name, color, desc)
            print(f"   [created] {name}")
    else:
        print("🏷️  All required labels are already present — nothing to create.")
    print()


def setup_milestones():
    print("🗓️  Creating GitHub milestones from ADO iterations...")
    try:
        iterations = get_iterations()
        for iteration in iterations:
            name     = iteration.get("name", "Unknown Sprint")
            attrs    = iteration.get("attributes", {})
            finish   = attrs.get("finishDate")  # ISO 8601 or None
            due_on   = f"{finish[:10]}T00:00:00Z" if finish else None
            ms_num   = create_milestone(title=name, due_on=due_on)
            print(f"   Milestone '{name}' → #{ms_num}")
    except Exception as e:
        print(f"   ⚠️  Could not fetch iterations: {e}")
    print()


def verify_labels():
    """
    Compares the labels that migration will try to use against what currently
    exists in the GitHub repo.  Prints a clear OK / MISSING report and returns
    True only when every required label is present.
    """
    print("🔎 Verifying GitHub labels against migration requirements...")
    existing  = set(list_labels())
    missing   = sorted(_REQUIRED_LABELS - existing)
    present   = sorted(_REQUIRED_LABELS & existing)
    extra     = sorted(existing - _REQUIRED_LABELS)

    print(f"\n   ✅ Present  ({len(present)}):")
    for name in present:
        print(f"      {name}")

    if missing:
        print(f"\n   ❌ Missing  ({len(missing)}) — will be silently dropped on issues:")
        for name in missing:
            print(f"      {name}")
    else:
        print("\n   ✅ No missing labels — repo is fully ready.")

    if extra:
        print(f"\n   ℹ️  Extra labels in repo not used by migration ({len(extra)}):")
        for name in extra:
            print(f"      {name}")

    print()
    return len(missing) == 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "verify":
        ok = verify_labels()
        sys.exit(0 if ok else 1)
    else:
        setup_labels()
        setup_milestones()
        print("✅ GitHub repository is ready for migration.")