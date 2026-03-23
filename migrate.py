"""
Main migration script.
Reads all ADO work items and creates corresponding GitHub Issues.
Tracks progress in state.json to support resume-on-failure.
"""
import json
import logging
import time
import os
import sys
from datetime import datetime, timezone
from ado_client import fetch_all_work_items, get_work_item_comments, get_work_items_batch, discover_work_item_fields, count_work_items_by_type, get_parent_ado_id
from github_client import create_issue, close_issue, add_comment, add_issue_to_project, set_project_item_iteration, set_project_item_single_select, set_issue_parent
from mapper import build_issue_body, build_labels, should_close, build_comment_body, resolve_github_issue_type_name
from milestone_map import build_milestone_map, resolve_milestone
from config import ADO_ORG, ADO_PROJECT, ADO_GH_USER_MAP, GH_PROJECT_NUMBERS, ADO_ITERATION_TO_PROJECT_ITERATION, ADO_PRIORITY_TO_PROJECT_PRIORITY

STATE_FILE   = "state.json"
NODE_ID_FILE = "state_node_ids.json"  # ado_id → github issue node_id (for parent linking)
ERRORS_FILE  = "migration_errors.json"
LOG_FILE     = "migration.log"


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("migration")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger


log = _setup_logger()

# ── ADO name → GitHub username resolver ─────────────────────────────────────

def resolve_github_username(display_name: str) -> str | None:
    """
    Fuzzy-match an ADO display name (e.g. 'Zdravko Kolev', 'Z Kolev', 'Zdravko K')
    against the ADO_GH_USER_MAP keys and return the corresponding GitHub username.
    Matches when both the first-name token and last-name token are satisfied
    by either a full word match or a single-initial match.
    """
    if not display_name:
        return None

    display_parts = set(display_name.lower().split())

    for full_name, gh_username in ADO_GH_USER_MAP.items():
        name_parts = full_name.lower().split()
        if len(name_parts) < 2:
            continue
        first, last = name_parts[0], name_parts[-1]

        first_match = first in display_parts or any(
            p == first[0] for p in display_parts if len(p) == 1
        )
        last_match = last in display_parts or any(
            p == last[0] for p in display_parts if len(p) == 1
        )

        if first_match and last_match:
            return gh_username

    return None


# ── State / Resume support ───────────────────────────────────────────────────

def load_errors() -> dict:
    """
    Returns the error ledger: { "ado_id": {"title", "error", "timestamp"} }.
    Items are removed automatically when successfully migrated in a later run.
    """
    if os.path.exists(ERRORS_FILE):
        with open(ERRORS_FILE) as f:
            return json.load(f)
    return {}


def save_errors(errors: dict):
    with open(ERRORS_FILE, "w") as f:
        json.dump(errors, f, indent=2)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}  # { "ado_id": github_issue_number }


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_node_ids() -> dict:
    """Returns {ado_id_str: github_issue_node_id} for parent-link resolution."""
    if os.path.exists(NODE_ID_FILE):
        with open(NODE_ID_FILE) as f:
            return json.load(f)
    return {}


def save_node_ids(node_ids: dict):
    with open(NODE_ID_FILE, "w") as f:
        json.dump(node_ids, f, indent=2)


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

def migrate_work_item(
    work_item: dict,
    state: dict,
    ms_map: dict[str, int] | None = None,
    node_ids: dict | None = None,
    _ancestors: set | None = None,  # cycle guard — ADO IDs currently in the call stack
) -> int:
    """
    Migrates one ADO work item to a GitHub issue.
    Automatically migrates any unmigrated parent first so the parent→child
    relationship can be established immediately.
    Returns the created GitHub issue number.
    """
    ado_id = work_item.get("id")
    title  = work_item.get("fields", {}).get("System.Title", f"Untitled #{ado_id}")

    if _ancestors is None:
        _ancestors = set()
    _ancestors = _ancestors | {ado_id}  # immutable update — don't mutate caller's set

    # ── Ensure parent is migrated first ──────────────────────────────────────
    parent_ado_id = get_parent_ado_id(work_item)
    if parent_ado_id and node_ids is not None:
        if str(parent_ado_id) not in state and parent_ado_id not in _ancestors:
            print(f"   ↳ Parent ADO #{parent_ado_id} not yet migrated — migrating it first...")
            log.info("AUTO-MIGRATE PARENT  ADO #%s before child ADO #%s", parent_ado_id, ado_id)
            parent_items = get_work_items_batch([parent_ado_id])
            if parent_items:
                try:
                    migrate_work_item(parent_items[0], state, ms_map, node_ids, _ancestors)
                    time.sleep(0.5)
                except Exception as ex:
                    log.warning(
                        "AUTO-MIGRATE PARENT FAILED  ADO #%s | %s — child ADO #%s will be deferred",
                        parent_ado_id, ex, ado_id,
                    )
                    print(f"   [WARN] Could not auto-migrate parent ADO #{parent_ado_id}: {ex}")
            else:
                log.warning("AUTO-MIGRATE PARENT NOT FOUND  ADO #%s (child: ADO #%s)", parent_ado_id, ado_id)
                print(f"   [WARN] Parent ADO #{parent_ado_id} not found in ADO — cannot migrate it.")
        elif parent_ado_id in _ancestors:
            log.warning(
                "CYCLE DETECTED  ADO #%s → ADO #%s — skipping auto-migrate of parent",
                ado_id, parent_ado_id,
            )

    # Build GitHub issue fields
    body        = build_issue_body(work_item, ADO_ORG, ADO_PROJECT)
    labels      = build_labels(work_item) + ["migrated-from-ado"]
    issue_type_name = resolve_github_issue_type_name(work_item)
    # Assignee: resolve ADO display name to GitHub username via ADO_GH_USER_MAP
    assigned_to = work_item.get("fields", {}).get("System.AssignedTo", {})
    display_name = (
        assigned_to.get("displayName", "") if isinstance(assigned_to, dict) else ""
    )
    gh_username = resolve_github_username(display_name)
    assignees = [gh_username] if gh_username else []

    # Resolve milestone from ADO iteration path
    iteration_path = work_item.get("fields", {}).get("System.IterationPath", "")
    milestone = resolve_milestone(iteration_path, ms_map) if ms_map else None

    # Create the GitHub issue
    gh_issue = create_issue(
        title=f"[ADO #{ado_id}] {title}",
        body=body,
        labels=labels,
        assignees=assignees,
        milestone=milestone,
        issue_type_name=issue_type_name,
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

    # ── Add to org projects and set iteration ────────────────────────────────
    # Resolve ADO iteration path → GitHub project iteration title
    project_iteration_title = None
    for ado_substr, proj_iter in ADO_ITERATION_TO_PROJECT_ITERATION.items():
        if ado_substr in iteration_path:
            project_iteration_title = proj_iter
            break

    # Resolve ADO priority → GitHub project priority option name
    ado_priority = work_item.get("fields", {}).get("Microsoft.VSTS.Common.Priority")
    project_priority = ADO_PRIORITY_TO_PROJECT_PRIORITY.get(ado_priority)

    # Resolve ADO area path → GitHub project Area single-select option name
    # System.AreaPath value (e.g. "BusinessTools\Reveal\Data Sources") maps
    # directly to the option names created by create_area_fields.py
    area_path = work_item.get("fields", {}).get("System.AreaPath")

    issue_node_id = gh_issue.get("node_id", "")
    for proj_num in GH_PROJECT_NUMBERS:
        try:
            proj_node_id, item_id = add_issue_to_project(proj_num, issue_node_id)
            if proj_node_id and item_id:
                if project_iteration_title:
                    set_project_item_iteration(proj_node_id, item_id, project_iteration_title)
                if project_priority:
                    set_project_item_single_select(proj_node_id, item_id, "Priority", project_priority)
                if area_path:
                    set_project_item_single_select(proj_node_id, item_id, "Area", area_path)
        except Exception as ex:
            print(f"   [WARN] Project #{proj_num}: {ex}")

    # Persist progress
    state[str(ado_id)] = gh_issue_number
    save_state(state)
    if node_ids is not None:
        node_ids[str(ado_id)] = gh_issue.get("node_id", "")
        save_node_ids(node_ids)

    # ── Link to parent issue (sub-issue relationship) ──────────────────────────
    parent_ado_id = get_parent_ado_id(work_item)
    if parent_ado_id and node_ids is not None:
        parent_gh_number = state.get(str(parent_ado_id))
        parent_node_id = node_ids.get(str(parent_ado_id))
        if parent_node_id:
            try:
                set_issue_parent(gh_issue.get("node_id", ""), parent_node_id)
                log.info(
                    "  ↳ parent linked: GH #%s (ADO #%s) is sub-issue of GH #%s (ADO #%s)",
                    gh_issue_number, ado_id, parent_gh_number, parent_ado_id,
                )
            except Exception as ex:
                log.warning(
                    "  ↳ parent link FAILED: GH #%s (ADO #%s) → ADO #%s | %s",
                    gh_issue_number, ado_id, parent_ado_id, ex,
                )
                print(f"   [WARN] Could not set parent relationship (ADO #{parent_ado_id}): {ex}")
        else:
            # Parent not yet in GitHub — record a deferred link for post-processing
            deferred = _deferred_parent_links.setdefault(str(parent_ado_id), [])
            deferred.append({"child_node_id": gh_issue.get("node_id", ""), "child_gh": gh_issue_number})
            log.info(
                "  ↳ parent deferred: GH #%s (ADO #%s) awaiting parent ADO #%s (not yet migrated)",
                gh_issue_number, ado_id, parent_ado_id,
            )
    elif parent_ado_id:
        log.info(
            "  ↳ parent noted: GH #%s (ADO #%s) has ADO parent #%s (node_id store unavailable)",
            gh_issue_number, ado_id, parent_ado_id,
        )
    else:
        log.info("  ↳ no parent: GH #%s (ADO #%s) is a root issue", gh_issue_number, ado_id)

    log.info("MIGRATED  ADO #%s → GH #%s | %s", ado_id, gh_issue_number, title)
    return gh_issue_number


# Holds child node_ids whose parent hadn't been migrated yet at link-time.
# Resolved at the end of the full migration run.
_deferred_parent_links: dict[str, list[dict]] = {}  # ado_parent_id_str → [{child_node_id, child_gh}]


def _resolve_deferred_parent_links(node_ids: dict):
    """Called once at end of migration to wire up any deferred parent links."""
    if not _deferred_parent_links:
        return
    print(f"\n🔗 Resolving {len(_deferred_parent_links)} deferred parent link(s)...")
    for parent_ado_id_str, children in _deferred_parent_links.items():
        parent_node_id = node_ids.get(parent_ado_id_str)
        if not parent_node_id:
            log.warning(
                "PARENT-NEVER-MIGRATED  ADO #%s — %d child issue(s) could not be linked: %s",
                parent_ado_id_str,
                len(children),
                ", ".join(f"GH #{c['child_gh']}" for c in children),
            )
            print(f"   [WARN] Parent ADO #{parent_ado_id_str} was never migrated — cannot link {len(children)} child issue(s).")
            continue
        for child in children:
            try:
                set_issue_parent(child["child_node_id"], parent_node_id)
                log.info(
                    "DEFERRED-LINK-OK  GH #%s → parent ADO #%s (GH #%s)",
                    child['child_gh'], parent_ado_id_str, node_ids.get(parent_ado_id_str, '?'),
                )
                print(f"   ✅ Linked GH #{child['child_gh']} → parent ADO #{parent_ado_id_str}")
            except Exception as ex:
                log.warning(
                    "DEFERRED-LINK-FAILED  GH #%s → parent ADO #%s | %s",
                    child['child_gh'], parent_ado_id_str, ex,
                )
                print(f"   [WARN] Deferred parent link for GH #{child['child_gh']}: {ex}")


# ── Test migration (single item) ─────────────────────────────────────────────

def migrate_test(ado_id: int):
    """Migrate a single ADO work item by ID for testing purposes."""
    print("=" * 60)
    print("  ADO → GitHub Work Item Migration (TEST - single item)")
    print("=" * 60)
    print()

    # Debug: show config
    from config import GH_TOKEN, GH_BASE_URL
    print(f"[DEBUG] GH_BASE_URL = {GH_BASE_URL}")
    print(f"[DEBUG] GH_TOKEN    = {GH_TOKEN[:10]}...{GH_TOKEN[-4:] if GH_TOKEN else 'EMPTY'}")
    print()

    state = load_state()
    if str(ado_id) in state:
        print(f"⚠️  ADO #{ado_id} was already migrated as GitHub Issue #{state[str(ado_id)]}.")
        return

    # Test basic GitHub connectivity first
    import requests
    print("📡 Testing GitHub API connectivity...")
    r = requests.get(GH_BASE_URL, headers={
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
    })
    print(f"   [DEBUG] GET {GH_BASE_URL} → {r.status_code} {r.reason}")
    if r.status_code != 200:
        print(f"   [DEBUG] Response: {r.text[:500]}")
        print(f"\n❌ Cannot access GitHub repo. Check GH_TOKEN permissions and repo name.")
        return
    print(f"   ✅ Repo accessible: {r.json().get('full_name', '?')}\n")

    print("📥 Fetching ADO work item #" + str(ado_id) + "...")
    items = get_work_items_batch([ado_id])
    work_item = items[0] if items else None

    if not work_item:
        print(f"⚠️  ADO work item #{ado_id} not found.")
        return

    fields = work_item.get("fields", {})
    title = fields.get("System.Title", f"Untitled #{ado_id}")
    description = fields.get("System.Description", "(no description)")
    wi_type = fields.get("System.WorkItemType", "?")
    state_val = fields.get("System.State", "?")
    iteration = fields.get("System.IterationPath", "?")

    print(f"\n📋 ADO Work Item #{ado_id} details:")
    print(f"   Title:       {title}")
    print(f"   Type:        {wi_type}")
    print(f"   State:       {state_val}")
    print(f"   Iteration:   {iteration}")
    print(f"   Description: {description[:200]}{'...' if len(description or '') > 200 else ''}")
    print()

    # ── Dry-run: build and print the GitHub issue payload without submitting ──
    issue_title  = f"[ADO #{ado_id}] {title}"
    issue_body   = build_issue_body(work_item, ADO_ORG, ADO_PROJECT)
    issue_labels = build_labels(work_item) + ["migrated-from-ado"]
    issue_type_name = resolve_github_issue_type_name(work_item)
    will_close   = should_close(work_item)

    comments = get_work_item_comments(ado_id)
    comment_bodies = [build_comment_body(c) for c in comments]

    print("=" * 60)
    print("  DRY-RUN: GitHub issue that would be created")
    print("=" * 60)
    print(f"\n📌 TITLE:\n   {issue_title}\n")
    print(f"🏷️  LABELS:\n   {', '.join(issue_labels)}\n")
    print(f"🧩 ISSUE TYPE:\n   {issue_type_name}\n")
    print(f"🔒 WILL BE CLOSED: {will_close}\n")
    parent_ado_id = get_parent_ado_id(work_item)
    if parent_ado_id:
        print(f"👆 PARENT ADO ID: #{parent_ado_id}\n")
    print("─" * 60)
    print("📄 BODY:")
    print("─" * 60)
    print(issue_body)
    if comment_bodies:
        print()
        print(f"─" * 60)
        print(f"💬 COMMENTS ({len(comment_bodies)}):")
        for i, cb in enumerate(comment_bodies, 1):
            print(f"─ comment {i} ─")
            print(cb)
    print()
    print("=" * 60)
    print("  Dry-run complete. Nothing was submitted to GitHub.")
    print("=" * 60)

# ── Single item migration ────────────────────────────────────────────────────

def migrate_single(ado_id: int):
    """
    Migrate a single ADO work item to GitHub and create the issue.
    Updates state.json and logs the result.
    """
    print("="*60)
    print("  ADO → GitHub Work Item Migration (SINGLE ITEM)")
    print("="*60)
    print()

    state = load_state()
    errors = load_errors()

    # Check if already migrated
    if str(ado_id) in state:
        gh_issue_num = state[str(ado_id)]
        print(f"⚠️  ADO #{ado_id} was already migrated as GitHub Issue #{gh_issue_num}.")
        print(f"   The issue has not been re-created.")
        return gh_issue_num

    # Fetch the work item
    print(f"📥 Fetching ADO work item #{ado_id}...")
    items = get_work_items_batch([ado_id])
    work_item = items[0] if items else None

    if not work_item:
        print(f"❌ ADO work item #{ado_id} not found.")
        return None

    fields = work_item.get("fields", {})
    title = fields.get("System.Title", f"Untitled #{ado_id}")
    print(f"   Title: {title}")
    print()

    # Build milestone mapping
    print("🗓️  Loading GitHub milestone mapping...")
    ms_map = build_milestone_map()
    print(f"   {len(ms_map)} milestone(s) mapped.\n")

    # Migrate the single item
    try:
        print(f"🚀 Creating GitHub issue for ADO #{ado_id}...")
        node_ids = load_node_ids()
        gh_issue_number = migrate_work_item(work_item, state, ms_map, node_ids)
        print(f"   ✅ Created GitHub Issue #{gh_issue_number}")
        # Resolve any deferred parent links accumulated during auto-parent migration
        _resolve_deferred_parent_links(node_ids)
        errors.pop(str(ado_id), None)  # Clear from error ledge on success
        save_errors(errors)
        print()
        print("="*60)
        print(f"  ✅ Migration successful!")
        print(f"     ADO #{ado_id} → GitHub Issue #{gh_issue_number}")
        print("="*60)
        return gh_issue_number

    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ Error: {error_msg}")
        errors[str(ado_id)] = {
            "title": title,
            "error": error_msg,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        save_errors(errors)
        log.error("ADO #%s FAILED | %s | %s", ado_id, title[:80], error_msg)
        print()
        print("="*60)
        print(f"  ❌ Migration failed!")
        print(f"     Error: {error_msg}")
        print(f"     See {ERRORS_FILE} for details.")
        print("="*60)
        return None

# ── Full migration ───────────────────────────────────────────────────────────

def migrate():
    """Migrate all pending ADO work items to GitHub issues."""
    print("=" * 60)
    print("  ADO → GitHub Work Item Migration")
    print("=" * 60)
    print()

    # Load resume state and error ledger
    state = load_state()
    errors = load_errors()
    node_ids = load_node_ids()
    already_migrated = set(str(k) for k in state.keys())
    print(f"📂 Resuming: {len(already_migrated)} items already migrated.")
    if errors:
        print(f"⚠️  {len(errors)} item(s) previously failed — they will be retried.")
    print()

    # Build milestone mapping from GitHub
    print("🗓️  Loading GitHub milestone mapping...")
    ms_map = build_milestone_map()
    print(f"   {len(ms_map)} milestone(s) mapped.\n")

    # Fetch all ADO work items
    all_items = fetch_all_work_items()

    # Filter already migrated
    pending = [
        item for item in all_items
        if str(item.get("id")) not in already_migrated
    ]
    # Build a lookup of all_items so we can log skipped items' parent info too
    all_items_by_id = {item.get("id"): item for item in all_items}
    for skipped_item in all_items:
        sid = skipped_item.get("id")
        if str(sid) in already_migrated:
            gh_num = state.get(str(sid))
            parent_ado_id = get_parent_ado_id(skipped_item)
            if parent_ado_id:
                parent_gh_num = state.get(str(parent_ado_id))
                if parent_gh_num:
                    log.info(
                        "SKIPPED   ADO #%s → GH #%s (already migrated) | parent: ADO #%s → GH #%s (already migrated)",
                        sid, gh_num, parent_ado_id, parent_gh_num,
                    )
                else:
                    log.info(
                        "SKIPPED   ADO #%s → GH #%s (already migrated) | parent: ADO #%s (not yet in GH)",
                        sid, gh_num, parent_ado_id,
                    )
            else:
                log.info("SKIPPED   ADO #%s → GH #%s (already migrated) | no parent", sid, gh_num)

    print(f"🚀 {len(pending)} work items to migrate.\n")
    log.info("=== Migration run started — %d pending, %d already migrated ===", len(pending), len(already_migrated))

    success_count = 0
    error_count   = 0

    for idx, work_item in enumerate(pending, start=1):
        ado_id = work_item.get("id")
        title  = work_item.get("fields", {}).get("System.Title", f"Untitled #{ado_id}")

        # Log items that are skipped because they're already in state.json
        # (These appear in `all_items` but were filtered out of `pending`;
        #  we log them here only for items whose parent is relevant.)
        print(f"[{idx}/{len(pending)}] Migrating ADO #{ado_id}: {title[:60]}...")

        try:
            gh_issue_number = migrate_work_item(work_item, state, ms_map, node_ids)
            print(f"   ✅ Created GitHub Issue #{gh_issue_number}")
            success_count += 1
            errors.pop(str(ado_id), None)  # Clear from error ledger on success
            save_errors(errors)
            time.sleep(0.5)  # Avoid secondary rate limits

        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ Error migrating ADO #{ado_id}: {error_msg}")
            log.error("ADO #%s FAILED | %s | %s", ado_id, title[:80], error_msg)
            errors[str(ado_id)] = {
                "title": title,
                "error": error_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            save_errors(errors)
            error_count += 1
            time.sleep(2)

    log.info(
        "=== Migration run complete — success=%d  failed=%d ===",
        success_count, error_count,
    )

    # Resolve any parent links where the parent was migrated after the child
    _resolve_deferred_parent_links(node_ids)

    print()
    print("=" * 60)
    print(f"  Migration complete!")
    print(f"  ✅ Succeeded : {success_count}")
    print(f"  ❌ Failed    : {error_count}")
    if errors:
        print(f"  ⚠️  Unresolved failures : {ERRORS_FILE}")
    print(f"  📄 State saved to      : {STATE_FILE}")
    print(f"  📋 Full log            : {LOG_FILE}")
    print("=" * 60)


def count_items():
    """
    Queries ADO for the full work item count broken down by type and state,
    then compares against state.json to show how many are still pending.
    Nothing is created or modified.
    """
    print("=" * 64)
    print("  ADO Work Item Count Preview")
    print("=" * 64)
    print()

    total, counts = count_work_items_by_type()
    migration_state = load_state()
    already_migrated = len(migration_state)

    print(f"  {'Work Item Type':<28} {'State':<22} {'Count':>6}")
    print(f"  {'─'*28} {'─'*22} {'─'*6}")

    type_totals: dict[str, int] = {}
    for wi_type in sorted(counts):
        type_total = sum(counts[wi_type].values())
        type_totals[wi_type] = type_total
        for state_name in sorted(counts[wi_type]):
            n = counts[wi_type][state_name]
            print(f"  {wi_type:<28} {state_name:<22} {n:>6}")
        print(f"  {'':28} {'  subtotal':<22} {type_total:>6}")
        print()

    print(f"  {'─'*58}")
    print(f"  {'TOTAL (all types)':<51} {total:>6}")
    print(f"  {'Already migrated (state.json)':<51} {already_migrated:>6}")
    print(f"  {'Pending':<51} {total - already_migrated:>6}")
    print()
    print("=" * 64)


def discover(ado_id: int):
    """Print all field reference names and values for a given ADO work item."""
    print(f"\n🔍 All fields for ADO work item #{ado_id}:\n")
    print(f"  {'Reference Name':<60} Value")
    print(f"  {'-'*59} {'-----'}")
    fields = discover_work_item_fields(ado_id)
    for f in fields:
        val = str(f["value"] or "")[:80]
        print(f"  {f['referenceName']:<60} {val}")
    print(f"\n✅ {len(fields)} fields found. Copy the reference names you need into ado_client.py.\n")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "test":
        migrate_test(int(sys.argv[2]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "single":
        migrate_single(int(sys.argv[2]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "discover":
        discover(int(sys.argv[2]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "count":
        count_items()
    else:
        migrate()