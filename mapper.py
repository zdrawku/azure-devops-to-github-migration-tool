import re
import html
from config import (
    WORK_ITEM_TYPE_LABELS,
    PRIORITY_LABELS,
    SEVERITY_LABELS,
    TRIAGE_LABELS,
    STATE_LABELS,
    CLOSED_STATES,
)


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

    # Detect attachments from work item relations
    relations = work_item.get("relations") or []
    attachment_count = sum(
        1 for r in relations if r.get("rel") == "AttachedFile"
    )

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
    # Fallback: type is ambiguous — fail-safe to "type: unknown"
    return "type: unknown"


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
    # Fallback: type is ambiguous — fail-safe to Bug.
    return "Bug"


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