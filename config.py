import os
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

# ADO states that should result in a CLOSED GitHub issue
CLOSED_STATES = {"Resolved", "Closed", "Done", "Removed"}