"""
Main migration script.
Reads all ADO work items and creates corresponding GitHub Issues.
Tracks progress in state.json to support resume-on-failure.
"""
import json
import time
import os
from ado_client import fetch_all_work_items, get_work_item_comments
from github_client import create_issue, close_issue, add_comment, list_milestones
from mapper import build_issue_body, build_labels, should_close, build_comment_body
from config import ADO_ORG, ADO_PROJECT

STATE_FILE = "state.json"

# ── Milestone cache ──────────────────────────────────────────────────────────

def load_milestone_map() -> dict[str, int]:
    """Returns a dict of { sprint_name: milestone_number }."""
    milestones = list_milestones()
    return {m["title"]: m["number"] for m in milestones}


# ── State / Resume support ───────────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}  # { "ado_id": github_issue_number }


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Iteration path → sprint name ─────────────────────────────────────────────

def iteration_to_sprint(iteration_path: str) -> str | None:
    """
    'MyProject\\Sprint 5' → 'Sprint 5'
    Returns the last segment of the ADO iteration path.
    """
    if not iteration_path:
        return None
    parts = iteration_path.replace("\\", "/").split("/")
    return parts[-1] if parts else None


# ── Migrate a single work item ────────────────────────────────────────────────

def migrate_work_item(work_item: dict, milestone_map: dict, state: dict) -> int:
    """
    Migrates one ADO work item to a GitHub issue.
    Returns the created GitHub issue number.
    """
    ado_id = work_item.get("id")
    title  = work_item.get("fields", {}).get("System.Title", f"Untitled #{ado_id}")

    # Build GitHub issue fields
    body        = build_issue_body(work_item, ADO_ORG, ADO_PROJECT)
    labels      = build_labels(work_item) + ["migrated-from-ado"]
    sprint_name = iteration_to_sprint(
        work_item.get("fields", {}).get("System.IterationPath", "")
    )
    milestone   = milestone_map.get(sprint_name) if sprint_name else None

    # Assignee: map ADO uniqueName to GitHub username if possible
    # ⚠️ Update this mapping with your team's real GitHub usernames
    assigned_to = work_item.get("fields", {}).get("System.AssignedTo", {})
    assignee_email = (
        assigned_to.get("uniqueName", "") if isinstance(assigned_to, dict) else ""
    )
    # Simple: strip domain from email as a best-effort guess, or leave empty
    assignees = []  # Populate with your own ADO email → GH username map

    # Create the GitHub issue
    gh_issue = create_issue(
        title=f"[ADO #{ado_id}] {title}",
        body=body,
        labels=labels,
        milestone=milestone,
        assignees=assignees,
    )
    gh_issue_number = gh_issue["number"]

    # Migrate comments
    comments = get_work_item_comments(ado_id)
    for comment in comments:
        comment_body = build_comment_body(comment)
        add_comment(gh_issue_number, comment_body)
        time.sleep(0.3)  # Be gentle with the API

    # Close the issue if it was Done/Closed/Resolved in ADO
    if should_close(work_item):
        close_issue(gh_issue_number)

    # Persist progress
    state[str(ado_id)] = gh_issue_number
    save_state(state)

    return gh_issue_number


# ── Test migration (single item) ─────────────────────────────────────────────

def migrate_test(ado_id: int):
    """Migrate a single ADO work item by ID for testing purposes."""
    print("=" * 60)
    print("  ADO → GitHub Work Item Migration (TEST - single item)")
    print("=" * 60)
    print()

    state = load_state()
    if str(ado_id) in state:
        print(f"⚠️  ADO #{ado_id} was already migrated as GitHub Issue #{state[str(ado_id)]}.")
        return

    print("📌 Loading GitHub milestones...")
    milestone_map = load_milestone_map()
    print(f"   Found {len(milestone_map)} milestones.\n")

    all_items = fetch_all_work_items()
    work_item = next((item for item in all_items if item.get("id") == ado_id), None)

    if not work_item:
        print(f"⚠️  ADO work item #{ado_id} not found.")
        return

    title = work_item.get("fields", {}).get("System.Title", f"Untitled #{ado_id}")
    print(f"🧪 Test-migrating ADO #{ado_id}: {title[:60]}...")

    try:
        gh_issue_number = migrate_work_item(work_item, milestone_map, state)
        print(f"   ✅ Created GitHub Issue #{gh_issue_number}")
    except Exception as e:
        print(f"   ❌ Error migrating ADO #{ado_id}: {e}")

    print()
    print("=" * 60)
    print(f"  Test migration complete! State saved to: {STATE_FILE}")
    print("=" * 60)


# ── Full migration ───────────────────────────────────────────────────────────

def migrate():
    """Migrate all pending ADO work items to GitHub issues."""
    print("=" * 60)
    print("  ADO → GitHub Work Item Migration")
    print("=" * 60)
    print()

    # Load resume state
    state = load_state()
    already_migrated = set(str(k) for k in state.keys())
    print(f"📂 Resuming: {len(already_migrated)} items already migrated.\n")

    # Load milestones
    print("📌 Loading GitHub milestones...")
    milestone_map = load_milestone_map()
    print(f"   Found {len(milestone_map)} milestones.\n")

    # Fetch all ADO work items
    all_items = fetch_all_work_items()

    # Filter already migrated
    pending = [
        item for item in all_items
        if str(item.get("id")) not in already_migrated
    ]
    print(f"🚀 {len(pending)} work items to migrate.\n")

    success_count = 0
    error_count   = 0

    for idx, work_item in enumerate(pending, start=1):
        ado_id = work_item.get("id")
        title  = work_item.get("fields", {}).get("System.Title", f"Untitled #{ado_id}")

        print(f"[{idx}/{len(pending)}] Migrating ADO #{ado_id}: {title[:60]}...")

        try:
            gh_issue_number = migrate_work_item(work_item, milestone_map, state)
            print(f"   ✅ Created GitHub Issue #{gh_issue_number}")
            success_count += 1
            time.sleep(0.5)  # Avoid secondary rate limits

        except Exception as e:
            print(f"   ❌ Error migrating ADO #{ado_id}: {e}")
            error_count += 1
            time.sleep(2)

    print()
    print("=" * 60)
    print(f"  Migration complete!")
    print(f"  ✅ Succeeded : {success_count}")
    print(f"  ❌ Failed    : {error_count}")
    print(f"  📄 State saved to: {STATE_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    migrate()