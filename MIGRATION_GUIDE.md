# ADO → GitHub Migration Guide

This document describes how Azure DevOps (ADO) work items are migrated to GitHub Issues using this toolset.

---

## Commands

| Command | Description |
|---|---|
| `python migrate.py test <ADO_ID>` | Dry-run: prints the GitHub issue that would be created for one work item — nothing is submitted |
| `python migrate.py discover <ADO_ID>` | Prints every ADO field reference name and value for a work item — useful for identifying custom fields |
| `python migrate.py` | Full migration: migrates all pending work items, resuming from `state.json` |

---

## Work Item Type Mapping

ADO's `System.WorkItemType` is used to determine the GitHub issue type label and is detected as follows:

| ADO Type | Detection Rule | GitHub Label |
|---|---|---|
| `Bug` | `System.WorkItemType = Bug` | `type: bug` |
| `Task` | `System.WorkItemType = Task` **and** any of the scheduling fields are non-null (`CompletedWork`, `OriginalEstimate`, `RemainingWork`) | `type: task` |
| `Feature` (User Story) | `System.WorkItemType = Task` **and** none of the scheduling fields are present | `type: feature` |

---

## Field Mapping: Bug Work Items

### Issue Body Sections

The GitHub issue body is built from the following ADO fields, rendered as Markdown sections in this order:

| Section Heading | ADO Field Reference |
|---|---|
| `## Description` | `System.Description` |
| `## Repro Steps` | `Microsoft.VSTS.TCM.ReproSteps` |
| `## Symptom` | `Microsoft.VSTS.CMMI.Symptom` |
| `## Expected Result` | `Custom.Infragistics_ExpectedResult` |
| `## Acceptance Criteria` | `Microsoft.VSTS.Common.AcceptanceCriteria` |

Sections are omitted entirely if the field has no value.

### Metadata Table

Below the content sections, a metadata table is appended with:

| Table Field | ADO Field Reference |
|---|---|
| ADO ID | `System.Id` |
| Type | `System.WorkItemType` |
| State | `System.State` |
| Reason | `System.Reason` |
| **Planning** | |
| Triage | `Microsoft.VSTS.Common.Triage` |
| Resolved Reason | `Microsoft.VSTS.Common.ResolvedReason` |
| Priority | `Microsoft.VSTS.Common.Priority` |
| Severity | `Microsoft.VSTS.Common.Severity` |
| Activity | `Microsoft.VSTS.Common.Activity` | Values: Development, Design, Deployment, Testing, Requirements and Implementation. |
| **Classification** | |
| Area Path | `System.AreaPath` |
| Iteration | `System.IterationPath` |
| Category | `Custom.Infragistics_Category` |
| Regression | `Custom.Infragistics_Regression` |
| Visibility | `Custom.Infragistics_Visibility` |
| **Origin** | |
| Created By | `System.CreatedBy` |
| Created Date | `System.CreatedDate` |
| Tags | `System.Tags` |

Rows are omitted automatically if the field has no value.

### Labels

Labels are derived automatically from the following ADO fields:

| Label Prefix | Source ADO Field | Example Values |
|---|---|---|
| `type:` | `System.WorkItemType` (+ scheduling logic) | `type: bug`, `type: task`, `type: feature` |
| `priority:` | `Microsoft.VSTS.Common.Priority` | `priority: critical` (1), `priority: high` (2), `priority: medium` (3), `priority: low` (4) |
| `severity:` | `Microsoft.VSTS.Common.Severity` | `severity: critical`, `severity: high`, `severity: medium`, `severity: low` |
| `triage:` | `Microsoft.VSTS.Common.Triage` | `triage: pending`, `triage: info-received`, `triage: triaged` |
| `state:` | `System.State` | `state: active`, `state: new`, `state: in-progress`, etc. |
| `ado-tag:` | `System.Tags` | `ado-tag: .NET`, `ado-tag: regression` |
| _(fixed)_ | — | `migrated-from-ado` |

### Issue Closure

A GitHub issue is automatically **closed** after creation if the ADO work item state is one of: `Resolved`, `Closed`, `Done`, `Removed`.

### Comments

All ADO discussion comments are migrated as GitHub issue comments, formatted as:

```
**Author Name** _(ADO comment, YYYY-MM-DD)_:

<comment text>
```

---

## Resume Support

The migration tracks progress in `state.json` (a map of `ado_id → github_issue_number`). If the process is interrupted, re-running `python migrate.py` will skip already-migrated items automatically.

---

## Discovering Custom Fields

If a work item contains custom fields not yet in the mapper, use the `discover` command:

```bash
python migrate.py discover <ADO_ID>
```

This fetches the item without any field filter, printing all field reference names alongside their values. Fields whose names contain keywords like `repro`, `symptom`, `expected`, or `steps` are highlighted with `◀ CUSTOM FIELD`.

To add a discovered field:
1. Note the exact reference name (e.g., `Custom.Infragistics_ExpectedResult`)
2. Add the field read to `build_issue_body()` in `mapper.py`
3. Add a corresponding `if <field>: lines += [...]` block in the same function

---

## Configuration

All configuration lives in `.env` (loaded via `python-dotenv`):

| Variable | Description |
|---|---|
| `ADO_ORG` | ADO organisation name (e.g. `infragistics`) |
| `ADO_PROJECT` | ADO project name (e.g. `BusinessTools`) |
| `ADO_PAT` | ADO Personal Access Token with **Read** scope on Work Items |
| `GH_TOKEN` | GitHub PAT with **repo** and **issues** scopes |

Label and state mappings are defined in `config.py` (`PRIORITY_LABELS`, `SEVERITY_LABELS`, `TRIAGE_LABELS`, `STATE_LABELS`, `CLOSED_STATES`).

---

## Known Issues and Limitations

### Attachments — Not Automatically Migrated

Attachments cannot be migrated automatically. GitHub's REST API has no endpoint for uploading files directly to an issue's attachment container, so the standard migration approach requires a three-step manual process.

**Why it can't be automated end-to-end**

| Phase | System | Action | API Used |
|---|---|---|---|
| 1. Discovery | Azure DevOps | Identify attachment URLs | Query work item with `?$expand=relations`, filter for `AttachedFile` |
| 2. Extraction | Azure DevOps | Download the binary | Authenticated `GET` to the attachment URL |
| 3. Migration | GitHub | Upload & link | `PUT` the file into the repo via the Contents API, then append the resulting URL to the issue body |

**What the migration script does instead**

When a work item has one or more attachments, the generated GitHub issue displays a warning banner:

> ⚠️ **Attachments not migrated** — this work item had N attachment(s) in Azure DevOps.  
> They could not be transferred automatically due to GitHub API limitations.  
> Please retrieve them manually from the original ADO work item.  
> See the [Attachment Migration Guide](https://github.com/Infragistics-BusinessTools/Reveal/wiki/ADO-to-GitHub-Migration-Guide) for step-by-step instructions.

**Manual steps**

1. Open the original ADO work item using the link in the issue header.
2. Download the attachments from the **Attachments** tab.
3. Follow the [Attachment Migration Guide](https://github.com/Infragistics-BusinessTools/Reveal/wiki/ADO-to-GitHub-Migration-Guide) (GitHub Wiki) to commit them into the repository and link them back to the issue.

