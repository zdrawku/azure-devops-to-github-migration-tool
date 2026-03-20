"""
Run this script ONCE before migration to set up labels and milestones
in the GitHub repository.
"""
from github_client import create_label, create_milestone
from ado_client import get_iterations
from config import WORK_ITEM_TYPE_LABELS, PRIORITY_LABELS, STATE_LABELS

# ── Label definitions: (name, hex_color, description) ───────────────────────
LABELS_TO_CREATE = [
    # Work item types
    ("bug",           "d73a4a", "ADO Bug"),
    ("task",          "0075ca", "ADO Task"),
    ("user-story",    "e4e669", "ADO User Story"),
    ("feature",       "a2eeef", "ADO Feature"),
    ("epic",          "d876e3", "ADO Epic"),
    ("backlog",       "f9d0c4", "ADO Product Backlog Item"),
    ("ado-issue",     "ee0701", "ADO Issue type"),
    ("test-case",     "bfd4f2", "ADO Test Case"),
    ("test-plan",     "c5def5", "ADO Test Plan"),
    ("test-suite",    "c2e0c6", "ADO Test Suite"),
    ("impediment",    "e11d48", "ADO Impediment"),
    # Priorities
    ("priority: critical", "b60205", "Critical priority"),
    ("priority: high",     "d93f0b", "High priority"),
    ("priority: medium",   "fbca04", "Medium priority"),
    ("priority: low",      "0e8a16", "Low priority"),
    # States
    ("state: new",        "ededed", "ADO State: New"),
    ("state: open",       "ededed", "ADO State: Open"),
    ("state: active",     "1d76db", "ADO State: Active"),
    ("state: in-progress","0052cc", "ADO State: In Progress"),
    ("state: resolved",   "0e8a16", "ADO State: Resolved"),
    ("state: removed",    "b60205", "ADO State: Removed"),
    # Source marker
    ("migrated-from-ado", "f1e05a", "Migrated from Azure DevOps"),
]


def setup_labels():
    print("🏷️  Creating GitHub labels...")
    for name, color, desc in LABELS_TO_CREATE:
        result = create_label(name, color, desc)
        status = "already existed" if result.get("already_existed") else "created"
        print(f"   [{status}] {name}")
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


if __name__ == "__main__":
    setup_labels()
    setup_milestones()
    print("✅ GitHub repository is ready for migration.")