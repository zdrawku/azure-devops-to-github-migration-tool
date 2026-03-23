import os
import json
from dotenv import load_dotenv

load_dotenv()

# ── Azure DevOps ────────────────────────────────────────────────────────────
ADO_ORG        = os.getenv("ADO_ORG")          # e.g. "MyCompany"
ADO_PROJECT    = os.getenv("ADO_PROJECT")       # e.g. "Reveal"
ADO_PAT        = os.getenv("ADO_PAT")           # Personal Access Token (read)
ADO_BASE_URL   = f"https://dev.azure.com/{ADO_ORG}/{ADO_PROJECT}/_apis"
ADO_API_VER    = "7.1"

# ── GitHub ───────────────────────────────────────────────────────────────────
GH_TOKEN       = os.getenv("GH_TOKEN")          # GitHub PAT (repo + issues scope)
GH_REPO_OWNER  = "Infragistics-BusinessTools"
GH_REPO_NAME   = "Reveal"
GH_BASE_URL    = f"https://api.github.com/repos/{GH_REPO_OWNER}/{GH_REPO_NAME}"

# ── User mapping ────────────────────────────────────────────────────────────
# ADO display name → GitHub username (loaded from ADO_GH_USER_MAP in .env)
ADO_GH_USER_MAP: dict[str, str] = json.loads(os.getenv("ADO_GH_USER_MAP", "{}"))

# ── Migration settings ───────────────────────────────────────────────────────
# How many work items to fetch per page from ADO
BATCH_SIZE = 200

# Map ADO work item types → GitHub label names
WORK_ITEM_TYPE_LABELS = {
    "Bug":              "bug",
    "Task":             "task",
    "User Story":       "user-story",
    "Feature":          "feature",
    "Epic":             "epic",
    "Product Backlog Item": "backlog",
    "Issue":            "ado-issue",
    "Test Case":        "test-case",
    "Test Plan":        "test-plan",
    "Test Suite":       "test-suite",
    "Impediment":       "impediment",
}

# Map ADO priority values → GitHub label names
PRIORITY_LABELS = {
    1: "priority: critical",
    2: "priority: high",
    3: "priority: medium",
    4: "priority: low",
}

# Map ADO severity values → GitHub label names
SEVERITY_LABELS = {
    "1 - Critical": "severity: critical",
    "2 - High":     "severity: high",
    "3 - Medium":   "severity: medium",
    "4 - Low":      "severity: low",
}

# Map ADO triage values → GitHub label names
TRIAGE_LABELS = {
    "Pending":       "triage: pending",
    "Info Received": "triage: info-received",
    "Triaged":       "triage: triaged",
}

# Map ADO states → GitHub label names
STATE_LABELS = {
    "Active":      "state: active",
    "In Progress": "state: in-progress",
    "Resolved":    "state: resolved",
    "Closed":      "closed",   # will also close the GH issue
    "Done":        "closed",   # will also close the GH issue
    "Removed":     "state: removed",
    "New":         "state: new",
    "Open":        "state: open",
}

# ADO states that should result in a CLOSED GitHub issue (used as fallback for
# work item types not explicitly listed in mapper.should_close)
CLOSED_STATES = {"Resolved", "Closed", "Done", "Removed"}