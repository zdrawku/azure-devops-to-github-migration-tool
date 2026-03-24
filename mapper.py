import re
import html
import urllib.parse
from config import (
    WORK_ITEM_TYPE_LABELS,
    PRIORITY_LABELS,
    SEVERITY_LABELS,
    TRIAGE_LABELS,
    STATE_LABELS,
    CLOSED_STATES,
    ADO_GITHUB_CONNECTION_MAP,
    GH_REPO_OWNER,
)


# ---------------------------------------------------------------------------
# Development-link helpers
# ---------------------------------------------------------------------------

# Cache: GitHub PR number → GitHub URL (discovered via search, per org-run)
_gh_pr_url_cache: dict[str, str] = {}  # "owner/repo#num" or "?#num" → url


def _resolve_vstfs_github_url(vstfs_url: str) -> str | None:
    """
    Converts a vstfs:///GitHub/PullRequest/{guid}%2F{num} URL into a real
    GitHub PR URL.

    Resolution order:
    1. ``ADO_GITHUB_CONNECTION_MAP`` config dict (GUID → "owner/repo").
    2. GitHub org-search via the GraphQL API (best-effort, cached per run).

    Returns None if the URL is not a vstfs GitHub link or cannot be resolved.
    """
    prefix = "vstfs:///GitHub/"
    if not vstfs_url.startswith(prefix):
        return None

    rest  = vstfs_url[len(prefix):]        # e.g. "PullRequest/guid%2Fnum"
    parts = rest.split("/", 1)
    raw_type = parts[0].lower()            # "pullrequest", "ref", "commit" …
    if len(parts) < 2:
        return None

    encoded = parts[1]                     # e.g. "guid%2Fnum"
    decoded = urllib.parse.unquote(encoded)  # "guid/num"
    tokens  = decoded.split("/")
    if len(tokens) < 2:
        return None

    guid    = tokens[0].lower()
    num_str = tokens[-1]                   # last token is the PR/commit number

    # ── 1. Config map ────────────────────────────────────────────────────────
    repo = ADO_GITHUB_CONNECTION_MAP.get(guid)
    if repo:
        if raw_type == "pullrequest":
            return f"https://github.com/{repo}/pull/{num_str}"
        if raw_type in ("ref", "gitref"):
            return f"https://github.com/{repo}/tree/{urllib.parse.quote(num_str, safe='/')}"
        if raw_type in ("commit", "githubcommit"):
            return f"https://github.com/{repo}/commit/{num_str}"
        if raw_type in ("issue", "githubissue"):
            return f"https://github.com/{repo}/issues/{num_str}"
        return f"https://github.com/{repo}"

    # ── 2. GitHub org search (PR only, best-effort) ──────────────────────────
    if raw_type == "pullrequest":
        cache_key = f"?#{num_str}"
        if cache_key in _gh_pr_url_cache:
            return _gh_pr_url_cache[cache_key]
        url = _search_gh_pr_in_org(num_str)
        if url:
            _gh_pr_url_cache[cache_key] = url
            print(
                f"   [INFO] Auto-resolved PR #{num_str} → {url}  "
                f"(add connection GUID '{guid}' to ADO_GITHUB_CONNECTION_MAP for speed)"
            )
        return url

    # ── 3. GitHub org search (Issues, best-effort) ───────────────────────────
    if raw_type in ("issue", "githubissue"):
        cache_key = f"issue?#{num_str}"
        if cache_key in _gh_pr_url_cache:
            return _gh_pr_url_cache[cache_key]
        url = _search_gh_issue_in_org(num_str)
        if url:
            _gh_pr_url_cache[cache_key] = url
            print(
                f"   [INFO] Auto-resolved Issue #{num_str} → {url}  "
                f"(add connection GUID '{guid}' to ADO_GITHUB_CONNECTION_MAP for speed)"
            )
        return url

    return None


def _search_gh_pr_in_org(pr_number: str) -> str | None:
    """
    Searches the GitHub org for a PR with the given number using the REST
    search API.  Filters strictly to items whose ``.number`` equals the target
    so text-match noise is excluded.

    Returns the PR's html_url if exactly one repo has a PR with that number,
    otherwise None (callers should fall back to the config map).
    """
    try:
        import requests as _req
        from config import GH_TOKEN

        r = _req.get(
            "https://api.github.com/search/issues",
            params={"q": f"is:pr org:{GH_REPO_OWNER} {pr_number}", "per_page": 30},
            headers={
                "Authorization": f"Bearer {GH_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )
        if not r.ok:
            return None

        exact = [
            item for item in r.json().get("items", [])
            if item.get("number") == int(pr_number)
        ]
        if len(exact) == 1:
            return exact[0]["html_url"]
        if len(exact) > 1:
            print(
                f"   [WARN] PR #{pr_number} found in {len(exact)} repos: "
                + ", ".join(i["html_url"] for i in exact)
                + " — cannot auto-select. Add the connection GUID to ADO_GITHUB_CONNECTION_MAP."
            )
    except Exception as _ex:
        print(f"   [WARN] GitHub PR search failed: {_ex}")
    return None


def _search_gh_issue_in_org(issue_number: str) -> str | None:
    """
    Searches the GitHub org for an issue with the given number using the REST
    search API.  Filters to items whose ``.number`` equals the target and whose
    ``pull_request`` key is absent (i.e. a real issue, not a PR).

    Returns the issue's html_url if exactly one repo has an issue with that
    number, otherwise None.
    """
    try:
        import requests as _req
        from config import GH_TOKEN

        r = _req.get(
            "https://api.github.com/search/issues",
            params={"q": f"is:issue org:{GH_REPO_OWNER} {issue_number}", "per_page": 30},
            headers={
                "Authorization": f"Bearer {GH_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )
        if not r.ok:
            return None

        exact = [
            item for item in r.json().get("items", [])
            if item.get("number") == int(issue_number)
            and "pull_request" not in item  # exclude PRs whose number matches
        ]
        if len(exact) == 1:
            return exact[0]["html_url"]
        if len(exact) > 1:
            print(
                f"   [WARN] Issue #{issue_number} found in {len(exact)} repos: "
                + ", ".join(i["html_url"] for i in exact)
                + " — cannot auto-select. Add the connection GUID to ADO_GITHUB_CONNECTION_MAP."
            )
    except Exception as _ex:
        print(f"   [WARN] GitHub issue search failed: {_ex}")
    return None


_VSTFS_TYPE_MAP = {
    "PullRequest":       "Pull Request",
    "GitHubPullRequest": "Pull Request",
    "Ref":               "Branch",
    "GitRef":            "Branch",
    "Commit":            "Commit",
    "GitHubCommit":      "Commit",
    "Issue":             "Issue",
    "GitHubIssue":       "Issue",
}


def _infer_github_link_type(url: str) -> str:
    """Infers the human-readable type of a github.com URL."""
    u = url.lower()
    if "/pull/" in u:
        return "Pull Request"
    if "/issues/" in u:
        return "Issue"
    if "/commit/" in u:
        return "Commit"
    if "/tree/" in u or "/blob/" in u:
        return "Branch"
    if "/releases/" in u:
        return "Release"
    return "Link"


def _parse_vstfs_github(url: str, attr_name: str = "") -> dict | None:
    """
    Parses a ``vstfs:///GitHub/`` URL and returns a dict with keys:
      - type  : human-readable link type (e.g. 'Pull Request', 'Branch')
      - source: 'artifact'
      - url   : original vstfs:// URL
      - github_url: resolved GitHub URL (or None if resolution failed)
    """
    prefix = "vstfs:///GitHub/"
    if not url.startswith(prefix):
        return None

    rest = url[len(prefix):]
    parts = rest.split("/", 1)
    raw_type = parts[0]  # e.g. "PullRequest"

    # Prefer the attribute name when it's informative (not just the raw type).
    link_type = attr_name or _VSTFS_TYPE_MAP.get(raw_type, raw_type)

    # Try to resolve the vstfs URL to a real GitHub URL
    github_url = _resolve_vstfs_github_url(url)

    return {
        "type":       link_type,
        "source":     "artifact",
        "url":        url,
        "github_url": github_url,
    }


def extract_dev_links(relations: list) -> list[dict]:
    """
    Extracts development-related links from an ADO work item's ``relations`` list.

    Each returned dict has:
      - type      : 'Pull Request', 'Branch', 'Commit', or generic label
      - source    : 'artifact'  (vstfs:///GitHub/ link from the Dev section)
                    'hyperlink' (explicit github.com hyperlink)
      - url       : original URL
      - github_url: actual GitHub URL when available, else None
    """
    dev_links: list[dict] = []
    seen_github_urls: set[str] = set()  # deduplicate if same PR appears as both artifact + hyperlink

    for rel in (relations or []):
        rel_type = rel.get("rel", "")
        url = rel.get("url", "")
        attrs = rel.get("attributes") or {}
        attr_name = attrs.get("name", "")

        if rel_type == "ArtifactLink" and "vstfs:///GitHub/" in url:
            link = _parse_vstfs_github(url, attr_name)
            if link:
                if link["github_url"]:
                    seen_github_urls.add(link["github_url"])
                dev_links.append(link)

        elif rel_type == "Hyperlink" and "github.com" in url.lower():
            # Skip if we already have the same GitHub URL from an artifact link
            if url not in seen_github_urls:
                seen_github_urls.add(url)
                dev_links.append({
                    "type":       _infer_github_link_type(url),
                    "source":     "hyperlink",
                    "url":        url,
                    "github_url": url,
                })

    return dev_links


def _format_dev_links_section(dev_links: list[dict], ado_url: str) -> list[str]:
    """
    Builds the Markdown lines for the '## Development Links' section and
    the accompanying warning callout.
    """
    lines: list[str] = []

    link_count = len(dev_links)
    lines += [
        "> [!WARNING]",
        f"> **Development links not fully migrated** — this work item had "
        f"**{link_count} development link(s)** in Azure DevOps.",
        f"> Please verify all links are properly reflected in GitHub by checking "
        f"the [original ADO work item]({ado_url}).",
        "",
        "## Development Links (from Azure DevOps)",
        "",
        "| Type | Link |",
        "|---|---|",
    ]

    for link in dev_links:
        ltype = link["type"]
        github_url = link.get("github_url")
        if github_url:
            lines.append(f"| **{ltype}** | [{github_url}]({github_url}) |")
        else:
            lines.append(
                f"| **{ltype}** | _(linked in ADO — see [work item]({ado_url}))_ |"
            )

    lines.append("")
    return lines


def _strip_html(text: str) -> str:
    """Converts basic ADO HTML fields to Markdown-friendly plain text."""
    if not text:
        return ""
    # Replace common HTML tags with Markdown equivalents
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<i>(.*?)</i>", r"_\1_", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<em>(.*?)</em>", r"_\1_", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<li>(.*?)</li>", r"- \1", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)  # Remove remaining HTML tags
    text = html.unescape(text)
    return text.strip()


def _get_field(work_item: dict, field: str, default=None):
    return work_item.get("fields", {}).get(field, default)


def build_issue_body(work_item: dict, ado_org: str, ado_project: str) -> str:
    """Constructs a rich GitHub Issue body from an ADO work item."""
    fields = work_item.get("fields", {})
    wi_id           = work_item.get("id")
    wi_type         = fields.get("System.WorkItemType", "Unknown")
    description     = _strip_html(fields.get("System.Description", ""))
    acceptance      = _strip_html(fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", ""))
    repro_steps     = _strip_html(fields.get("Microsoft.VSTS.TCM.ReproSteps", ""))
    symptom         = _strip_html(fields.get("Microsoft.VSTS.CMMI.Symptom", ""))
    expected_result = _strip_html(fields.get("Custom.Infragistics_ExpectedResult", ""))
    category          = fields.get("Custom.Infragistics_Category", "")
    regression        = fields.get("Custom.Infragistics_Regression", "")
    visibility        = fields.get("Custom.Infragistics_Visibility", "")
    reason            = fields.get("System.Reason", "")
    triage            = fields.get("Microsoft.VSTS.Common.Triage", "")
    resolved_reason   = fields.get("Microsoft.VSTS.Common.ResolvedReason", "")
    priority          = fields.get("Microsoft.VSTS.Common.Priority", "")
    severity          = fields.get("Microsoft.VSTS.Common.Severity", "")
    activity          = fields.get("Microsoft.VSTS.Common.Activity", "")
    original_estimate = fields.get("Microsoft.VSTS.Scheduling.OriginalEstimate")
    remaining_work    = fields.get("Microsoft.VSTS.Scheduling.RemainingWork")
    completed_work    = fields.get("Microsoft.VSTS.Scheduling.CompletedWork")
    area            = fields.get("System.AreaPath", "")
    iteration       = fields.get("System.IterationPath", "")
    created_by      = fields.get("System.CreatedBy", {})
    created_date    = fields.get("System.CreatedDate", "")
    tags            = fields.get("System.Tags", "")
    state           = fields.get("System.State", "")
    assigned_to     = fields.get("System.AssignedTo", {})
    story_points    = fields.get("Microsoft.VSTS.Scheduling.StoryPoints")
    risk            = fields.get("Microsoft.VSTS.Common.Risk", "")
    value_area      = fields.get("Microsoft.VSTS.Common.ValueArea", "")

    # Detect attachments and development links from work item relations
    relations = work_item.get("relations") or []
    attachment_count = sum(
        1 for r in relations if r.get("rel") == "AttachedFile"
    )
    dev_links = extract_dev_links(relations)

    ado_url = (
        f"https://dev.azure.com/{ado_org}/{ado_project}/_workitems/edit/{wi_id}"
    )
    created_by_name = (
        created_by.get("displayName", "Unknown") if isinstance(created_by, dict)
        else str(created_by)
    )
    assigned_to_name = (
        assigned_to.get("displayName", "") if isinstance(assigned_to, dict)
        else str(assigned_to) if assigned_to else ""
    )

    header_line = f"> **Migrated from Azure DevOps** · [{wi_type} #{wi_id}]({ado_url})"
    if assigned_to_name:
        header_line += f" · **Assigned To:** {assigned_to_name}"

    lines = [
        header_line,
        "",
    ]

    if description:
        lines += ["## Description", "", description, ""]

    if repro_steps:
        lines += ["## Repro Steps", "", repro_steps, ""]

    if symptom:
        lines += ["## Symptom", "", symptom, ""]

    if expected_result:
        lines += ["## Expected Result", "", expected_result, ""]

    if acceptance:
        lines += ["## Acceptance Criteria", "", acceptance, ""]

    # Planning section — shown when at least one of story points, priority, or risk is present
    planning_rows = [
        ("Story Points", str(story_points) if story_points is not None else ""),
        ("Priority",     str(priority) if priority else ""),
        ("Risk",         risk),
    ]
    planning_values = [(label, val) for label, val in planning_rows if val]
    if planning_values:
        lines += ["## Planning", "", "| Field | Value |", "|---|---|"]
        for label, val in planning_values:
            lines.append(f"| **{label}** | {val} |")
        lines.append("")

    # Classification section — shown when Value Area is present
    if value_area:
        lines += [
            "## Classification",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| **Value Area** | {value_area} |",
            "",
        ]

    # Effort section — only shown when at least one scheduling field is present
    effort_rows = [
        ("Original Estimate", original_estimate),
        ("Remaining",         remaining_work),
        ("Completed",         completed_work),
    ]
    effort_values = [(label, val) for label, val in effort_rows if val is not None]
    if effort_values:
        lines += ["## Effort (Hours)", "", "| | Hours |", "|---|---|"]  
        for label, val in effort_values:
            lines.append(f"| **{label}** | {val} |")
        lines.append("")


    if attachment_count:
        wiki_url = "https://github.com/Infragistics-BusinessTools/Reveal/wiki/ADO-to-GitHub-Migration-Guide"
        lines += [
            f"> [!WARNING]",
            f"> **Attachments not migrated** — this work item had **{attachment_count} attachment(s)** in Azure DevOps.",
            f"> They could not be transferred automatically due to GitHub API limitations.",
            f"> Please retrieve them manually from the [original ADO work item]({ado_url}).",
            f"> See the [Attachment Migration Guide]({wiki_url}) for step-by-step instructions.",
            "",
        ]

    if dev_links:
        lines += _format_dev_links_section(dev_links, ado_url)

    # Metadata table — build rows explicitly to avoid duplicates
    meta_rows = [
        ("ADO ID",         f"#{wi_id}"),
        ("Type",           wi_type),
        ("State",          state),
        ("Reason",         reason),
        # Planning
        ("Triage",         triage),
        ("Resolved Reason",resolved_reason),
        ("Priority",       str(priority) if priority else ""),
        ("Severity",       severity),
        ("Activity",       activity),
        # ── Classification ────────────────────────────────────────────
        ("Area Path",      area),
        ("Iteration",      iteration),
        ("Category",       str(category) if category else ""),
        ("Regression",     str(regression) if regression else ""),
        ("Visibility",     str(visibility) if visibility else ""),
        # Origin
        ("Created By",     created_by_name),
        ("Created Date",   created_date[:10] if created_date else ""),
        ("Tags",           tags),
    ]

    lines += [
        "---",
        "### ADO Metadata",
        "",
        "| Field | Value |",
        "|---|---|",
    ]
    for label, value in meta_rows:
        if value:
            lines.append(f"| **{label}** | {value} |")

    return "\n".join(lines)


# Scheduling fields that distinguish a real Task from a User Story/Feature
_TASK_SCHEDULING_FIELDS = (
    "Microsoft.VSTS.Scheduling.CompletedWork",
    "Microsoft.VSTS.Scheduling.OriginalEstimate",
    "Microsoft.VSTS.Scheduling.RemainingWork",
)


def resolve_github_type(work_item: dict) -> str:
    """
    Returns the GitHub type label for a work item.
    Both real Tasks and User Stories appear as System.WorkItemType=Task in ADO.
    Tasks have scheduling fields; User Stories / Features do not.
    All other types are looked up in WORK_ITEM_TYPE_LABELS.
    """
    fields = work_item.get("fields", {})
    wi_type = fields.get("System.WorkItemType", "")
    if wi_type == "Bug":
        return "type: bug"
    if wi_type == "Task":
        has_scheduling = any(
            fields.get(f) is not None for f in _TASK_SCHEDULING_FIELDS
        )
        return "type: task" if has_scheduling else "type: feature"
    # All other recognised types: look up in the central mapping
    label_suffix = WORK_ITEM_TYPE_LABELS.get(wi_type)
    if label_suffix:
        return f"type: {label_suffix}"
    # Truly unknown type — fail-safe
    return "type: unknown"


# Maps ADO work item types to GitHub native Issue Type names.
# Only "Bug", "Task", and "Feature" are configured as native types in this repo.
_GITHUB_ISSUE_TYPE_MAP: dict[str, str] = {
    "Bug":              "Bug",
    "Task":             "Task",      # real Task (has scheduling fields)
    # Task without scheduling → Feature (handled separately in the function)
    "User Story":       "Feature",
    "Feature":          "Feature",
    "Feature Request":  "Feature",
    "Epic":             "Feature",
    "Product Backlog Item": "Feature",
    "Issue":            "Bug",
    "Test Case":        "Task",
    "Test Plan":        "Task",
    "Test Suite":       "Task",
    "Impediment":       "Task",
}


def resolve_github_issue_type_name(work_item: dict) -> str:
    """
    Returns the GitHub native Issue Type name for a work item.
    Expected values in this repo: Bug, Task, Feature.
    """
    fields = work_item.get("fields", {})
    wi_type = fields.get("System.WorkItemType", "")
    if wi_type == "Bug":
        return "Bug"
    if wi_type == "Task":
        has_scheduling = any(
            fields.get(f) is not None for f in _TASK_SCHEDULING_FIELDS
        )
        return "Task" if has_scheduling else "Feature"
    return _GITHUB_ISSUE_TYPE_MAP.get(wi_type, "Feature")


def build_labels(work_item: dict) -> list[str]:
    """Returns the list of GitHub label names for this work item."""
    fields = work_item.get("fields", {})
    labels = []

    # GitHub type (Bug / Task / Feature)
    labels.append(resolve_github_type(work_item))

    # Priority
    priority = fields.get("Microsoft.VSTS.Common.Priority")
    if priority in PRIORITY_LABELS:
        labels.append(PRIORITY_LABELS[priority])

    # Severity
    severity = fields.get("Microsoft.VSTS.Common.Severity", "")
    severity_label = SEVERITY_LABELS.get(severity)
    if severity_label:
        labels.append(severity_label)

    # Triage
    triage = fields.get("Microsoft.VSTS.Common.Triage", "")
    triage_label = TRIAGE_LABELS.get(triage)
    if triage_label:
        labels.append(triage_label)

    # State
    state = fields.get("System.State", "")
    state_label = STATE_LABELS.get(state)
    if state_label and state_label != "closed":
        labels.append(state_label)

    # ADO tags → GitHub labels
    tags_str = fields.get("System.Tags", "") or ""
    for tag in tags_str.split(";"):
        tag = tag.strip()
        if tag:
            labels.append(f"{tag}")

    return labels


def should_close(work_item: dict) -> bool:
    """
    Determines whether the migrated GitHub issue should be closed.

    Rules (per work item type):
    - Bug  : close only when State == "Closed"
    - Task : close when State is "Closed" or "Removed"
             (covers both real Tasks and User-Story/Feature sub-types,
              which share System.WorkItemType == "Task" in ADO)
    - All other types: use the broad fallback set
      ("Closed", "Done", "Removed", "Resolved")
    """
    fields  = work_item.get("fields", {})
    wi_type = fields.get("System.WorkItemType", "")
    state   = fields.get("System.State", "")

    if wi_type == "Bug":
        return state == "Closed"
    if wi_type == "Task":
        return state in {"Closed", "Removed"}
    # Fallback for Epic, Feature, User Story, etc.
    return state in CLOSED_STATES


def build_comment_body(comment: dict) -> str:
    """Formats an ADO comment for GitHub."""
    author = comment.get("createdBy", {}).get("displayName", "Unknown")
    date   = comment.get("createdDate", "")[:10]
    text   = _strip_html(comment.get("text", ""))
    return f"**{author}** _(ADO comment, {date})_:\n\n{text}"