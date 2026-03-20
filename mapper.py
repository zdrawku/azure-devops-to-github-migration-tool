import re
import html
from config import (
    WORK_ITEM_TYPE_LABELS,
    PRIORITY_LABELS,
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
    wi_id        = work_item.get("id")
    wi_type      = fields.get("System.WorkItemType", "Unknown")
    description  = _strip_html(fields.get("System.Description", ""))
    acceptance   = _strip_html(fields.get("Microsoft.VSTS.Common.AcceptanceCriteria", ""))
    repro_steps  = _strip_html(fields.get("Microsoft.VSTS.Common.ReproSteps", ""))
    test_steps   = _strip_html(fields.get("Microsoft.VSTS.TCM.Steps", ""))
    area         = fields.get("System.AreaPath", "")
    iteration    = fields.get("System.IterationPath", "")
    created_by   = fields.get("System.CreatedBy", {})
    created_date = fields.get("System.CreatedDate", "")
    tags         = fields.get("System.Tags", "")
    priority     = fields.get("Microsoft.VSTS.Common.Priority", "")
    state        = fields.get("System.State", "")

    ado_url = (
        f"https://dev.azure.com/{ado_org}/{ado_project}/_workitems/edit/{wi_id}"
    )
    created_by_name = (
        created_by.get("displayName", "Unknown") if isinstance(created_by, dict)
        else str(created_by)
    )

    lines = [
        f"> **Migrated from Azure DevOps** · [{wi_type} #{wi_id}]({ado_url})",
        "",
    ]

    if description:
        lines += ["## 📋 Description", "", description, ""]

    if repro_steps:
        lines += ["## 🐛 Repro Steps", "", repro_steps, ""]

    if acceptance:
        lines += ["## ✅ Acceptance Criteria", "", acceptance, ""]

    if test_steps:
        lines += ["## 🧪 Test Steps", "", test_steps, ""]

    # Metadata table
    lines += [
        "---",
        "### 🗂️ ADO Metadata",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| **ADO ID** | #{wi_id} |",
        f"| **Type** | {wi_type} |",
        f"| **State** | {state} |",
        f"| **Priority** | {priority} |",
        f"| **Area Path** | {area} |",
        f"| **Iteration** | {iteration} |",
        f"| **Created By** | {created_by_name} |",
        f"| **Created Date** | {created_date[:10] if created_date else ''} |",
    ]

    if tags:
        lines.append(f"| **Tags** | {tags} |")

    return "\n".join(lines)


def build_labels(work_item: dict) -> list[str]:
    """Returns the list of GitHub label names for this work item."""
    fields = work_item.get("fields", {})
    labels = []

    # Work item type
    wi_type = fields.get("System.WorkItemType", "")
    if wi_type in WORK_ITEM_TYPE_LABELS:
        labels.append(WORK_ITEM_TYPE_LABELS[wi_type])

    # Priority
    priority = fields.get("Microsoft.VSTS.Common.Priority")
    if priority in PRIORITY_LABELS:
        labels.append(PRIORITY_LABELS[priority])

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
            labels.append(f"ado-tag: {tag}")

    return labels


def should_close(work_item: dict) -> bool:
    state = _get_field(work_item, "System.State", "")
    return state in CLOSED_STATES


def build_comment_body(comment: dict) -> str:
    """Formats an ADO comment for GitHub."""
    author = comment.get("createdBy", {}).get("displayName", "Unknown")
    date   = comment.get("createdDate", "")[:10]
    text   = _strip_html(comment.get("text", ""))
    return f"**{author}** _(ADO comment, {date})_:\n\n{text}"