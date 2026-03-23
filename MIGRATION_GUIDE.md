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

## Fail-safe logging (migrate.py)

Two new artifacts are written automatically during every run:

| File | Purpose |
|---|---|
| `migration.log` | Human-readable timestamped log — one line per success (ADO #X → GH #Y), one line per failure with the full error message, plus run-start / run-end lines. Appended on every run, so the full history is preserved. |
| `migration_errors.json` | Machine-readable JSON ledger of unresolved failures. Contains `{ ado_id: { title, error, timestamp } }`. An item is removed from this file automatically the next time it migrates successfully, so the file always reflects exactly what still needs attention. |

On each run the console now shows how many items previously failed so you know upfront that retries are queued.

## Type-aware should_close() (mapper.py)

ADO type	Closes when state is…
Bug	Closed only
Task (→ task and feature/user-story in GitHub)	Closed or Removed
Everything else (Epic, User Story, etc.)	Closed, Done, Removed, Resolved (original broad set)

## Pre-mass-migration checklist
These are the things that can cost you the most time or are hardest to fix after the fact:

### Before you run

- Dry-run a representative sample. Run python migrate.py test <id> on at least one Bug, one Task/Feature, and one closed item of each type to validate body formatting, label creation, and should_close logic before touching 2 500 items.
- Enumerate the exact item count first. Add a quick WIQL query run (the same one get_all_work_item_ids() uses) without actually migrating, and confirm the number. The query WHERE [System.TeamProject] = @project has no date or type filter — if the BacklogTools project has sub-projects or archived items you don't expect, they show up here.
- GitHub label pre-creation. The migration calls create_issue with labels that may not exist yet. GitHub silently drops unknown labels on issue creation. Run python setup_github.py (or whatever creates labels) and verify every label in WORK_ITEM_TYPE_LABELS, PRIORITY_LABELS, SEVERITY_LABELS, TRIAGE_LABELS, and STATE_LABELS actually exists in the repo before the run.
- Validate the assignee list. Call resolve_github_username() against a sample of real displayName values from your ADO data. If any name variant doesn't match, the issue is created without an assignee — no error is thrown. Worth checking: accented characters, middle names, or nicknames in ADO.
- GitHub secondary rate limit. With 2 500 items × (1 create_issue + N comments + maybe 1 close) API calls, you will approach or hit GitHub's secondary rate limit (roughly 80–100 write requests per minute for the REST API). The current time.sleep(0.5) between items and time.sleep(0.3) between comments helps, but if comments are numerous, slow it down further. A 429 or 403 with "secondary rate limit" in the body will show up as a logged error, and the item will be retried on the next run.
- state.json is your safety net — back it up. The file is the only record of ADO ID → GitHub issue number mappings. Copy it somewhere safe before the run. If you need to re-run for any reason, missing entries here will cause duplicate issues.

### During the run

- Keep the terminal in view. Errors are printed in real time. If you see a burst of ❌ lines (e.g. a GitHub outage or token expiry), kill the process — the state and error ledger are saved after every individual item, so you lose at most one item's progress.
- Watch migration.log in a second terminal (Get-Content migration.log -Wait on PowerShell) for a timestamped stream.

### After the run

- Check migration_errors.json. If it's non-empty, fix the root cause (wrong token, missing label, rate limit) and re-run — the failed items will be retried automatically.
- Verify a random 5–10 issues on GitHub: confirm labels, closed state, comments, and the > Migrated from Azure DevOps header all look right.
- The ADO items themselves are not touched by this script, so you can compare source and destination at any point.