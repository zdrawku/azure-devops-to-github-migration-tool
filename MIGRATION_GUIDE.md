# ADO → GitHub Migration Guide

This document describes how Azure DevOps (ADO) work items are migrated to GitHub Issues using this toolset.

---

## Commands

### migrate.py

| Command | Description |
|---|---|
| `python migrate.py` | **Full migration** — migrates all pending work items, resuming from `state.json` |
| `python migrate.py count` | **Count preview** — queries ADO and prints a breakdown of all work items by type and state, plus how many are already migrated vs. still pending. Nothing is created. |
| `python migrate.py test <ADO_ID>` | **Dry-run** — prints the GitHub issue that would be created for one work item; nothing is submitted |
| `python migrate.py discover <ADO_ID>` | **Field discovery** — prints every ADO field reference name and value for a work item; useful for identifying custom fields |

### setup_github.py

| Command | Description |
|---|---|
| `python setup_github.py` | **Setup** — creates all required GitHub labels and milestones. Only labels that do not already exist in the repo are created; existing ones are reported and skipped. |
| `python setup_github.py verify` | **Verify** — compares the labels the migration will apply against what is currently in the GitHub repo. Prints a clear Present / Missing / Extra report. Exits with code `1` if any required label is absent. |

---

## Inspecting Areas & Iterations

Two utility functions in `ado_client.py` let you fetch the full area-path and iteration trees directly from the ADO Classification Nodes API.

| Function | REST Endpoint |
|---|---|
| `get_all_areas(depth=10)` | `GET .../wit/classificationnodes/Areas?$depth={depth}&api-version=7.1` |
| `get_all_iterations(depth=10)` | `GET .../wit/classificationnodes/Iterations?$depth={depth}&api-version=7.1` |

Both return the raw ADO response dict with nested `children` lists. The `depth` parameter controls how many levels of the tree are returned (default `10`).

### Usage

```python
from ado_client import get_all_areas, get_all_iterations
import json

# Fetch the full trees
areas      = get_all_areas()
iterations = get_all_iterations()

# Pretty-print
print(json.dumps(areas, indent=2))
print(json.dumps(iterations, indent=2))

# Walk top-level children
for node in areas.get("children", []):
    print(node["name"])

# Limit depth
areas_shallow = get_all_areas(depth=2)
```

### Response Structure

Each node in the tree contains at minimum:

| Field | Description |
|---|---|
| `id` | Numeric node ID |
| `identifier` | GUID |
| `name` | Node display name (e.g. `"Sprint 42"`) |
| `structureType` | `"area"` or `"iteration"` |
| `hasChildren` | `true` if the node has sub-nodes |
| `children` | Array of child nodes (present when `hasChildren` is `true` and `$depth` is large enough) |
| `attributes` | For iterations: contains `startDate` and `finishDate` |


End result:

Area paths
[
  "BusinessTools",
  "BusinessTools\Reveal",
  "BusinessTools\Reveal\Data Sources",
  "BusinessTools\Reveal\Data Sources\MS SQL Server",
  "BusinessTools\Reveal\Data Sources\REST Service",
  "BusinessTools\Reveal\Data Sources\OneDrive",
  "BusinessTools\Reveal\Data Sources\Amazon Athena",
  "BusinessTools\Reveal\Data Sources\Amazon Redshift",
  "BusinessTools\Reveal\Data Sources\Box",
  "BusinessTools\Reveal\Data Sources\Dropbox",
  "BusinessTools\Reveal\Data Sources\Google Analytics",
  "BusinessTools\Reveal\Data Sources\Google BigQuery",
  "BusinessTools\Reveal\Data Sources\Google Drive",
  "BusinessTools\Reveal\Data Sources\Google Sheets",
  "BusinessTools\Reveal\Data Sources\Hubspot",
  "BusinessTools\Reveal\Data Sources\In-Memory Data",
  "BusinessTools\Reveal\Data Sources\Marketo",
  "BusinessTools\Reveal\Data Sources\MS Analysis Services",
  "BusinessTools\Reveal\Data Sources\MS Azure Synapse Analytics",
  "BusinessTools\Reveal\Data Sources\MS Azure SQL Server",
  "BusinessTools\Reveal\Data Sources\MS Dynamics CRM",
  "BusinessTools\Reveal\Data Sources\MS Reporting Services (SSRS)",
  "BusinessTools\Reveal\Data Sources\MySQL",
  "BusinessTools\Reveal\Data Sources\Oracle",
  "BusinessTools\Reveal\Data Sources\OData",
  "BusinessTools\Reveal\Data Sources\PostgreSQL",
  "BusinessTools\Reveal\Data Sources\QuickBooks",
  "BusinessTools\Reveal\Data Sources\Salesforce",
  "BusinessTools\Reveal\Data Sources\SharePoint",
  "BusinessTools\Reveal\Data Sources\Sybase",
  "BusinessTools\Reveal\Data Sources\Databricks",
  "BusinessTools\Reveal\Data Sources\Elasticsearch",
  "BusinessTools\Reveal\Data Sources\MongoDB",
  "BusinessTools\Reveal\Controls",
  "BusinessTools\Reveal\Controls\RevealView",
  "BusinessTools\Reveal\Controls\DashboardThumbnailView",
  "BusinessTools\Reveal\Visualizations",
  "BusinessTools\Reveal\Visualizations\Area",
  "BusinessTools\Reveal\Visualizations\Bar",
  "BusinessTools\Reveal\Visualizations\Bubble",
  "BusinessTools\Reveal\Visualizations\Candlestick",
  "BusinessTools\Reveal\Visualizations\Choropleth",
  "BusinessTools\Reveal\Visualizations\Circular Gauge",
  "BusinessTools\Reveal\Visualizations\Column",
  "BusinessTools\Reveal\Visualizations\Combo",
  "BusinessTools\Reveal\Visualizations\Custom",
  "BusinessTools\Reveal\Visualizations\Doughnut",
  "BusinessTools\Reveal\Visualizations\Funnel",
  "BusinessTools\Reveal\Visualizations\Grid",
  "BusinessTools\Reveal\Visualizations\Image",
  "BusinessTools\Reveal\Visualizations\KPI Target",
  "BusinessTools\Reveal\Visualizations\KPI Time",
  "BusinessTools\Reveal\Visualizations\Linear Gauge",
  "BusinessTools\Reveal\Visualizations\Line",
  "BusinessTools\Reveal\Visualizations\OHLC",
  "BusinessTools\Reveal\Visualizations\Pie",
  "BusinessTools\Reveal\Visualizations\Pivot",
  "BusinessTools\Reveal\Visualizations\Radial",
  "BusinessTools\Reveal\Visualizations\Scatter Map",
  "BusinessTools\Reveal\Visualizations\Scatter",
  "BusinessTools\Reveal\Visualizations\Sparkline",
  "BusinessTools\Reveal\Visualizations\Spline",
  "BusinessTools\Reveal\Visualizations\Spline Area",
  "BusinessTools\Reveal\Visualizations\Stacked Area",
  "BusinessTools\Reveal\Visualizations\Stacked Bar",
  "BusinessTools\Reveal\Visualizations\Stacked Column",
  "BusinessTools\Reveal\Visualizations\Step Area",
  "BusinessTools\Reveal\Visualizations\Step Line",
  "BusinessTools\Reveal\Visualizations\Text Box",
  "BusinessTools\Reveal\Visualizations\Text View",
  "BusinessTools\Reveal\Visualizations\Text",
  "BusinessTools\Reveal\Visualizations\Time Series",
  "BusinessTools\Reveal\Visualizations\Tree Map",
  "BusinessTools\Reveal\Samples",
  "BusinessTools\Reveal\Documentation",
  "BusinessTools\Reveal\Export",
  "BusinessTools\Slingshot",
  "BusinessTools\Slingshot\Connectors",
  "BusinessTools\Slingshot\Connectors\QuickBooks",
  "BusinessTools\SharePlus",
  "BusinessTools\Website Team",
  "BusinessTools\Slingshot Server Team",
  "BusinessTools\Data Source Team"
]

Milestones:
[
  {
    "name": "Release - Feb 2023",
    "start_date": "2023-01-02",
    "finish_date": "2023-02-28"
  },
  {
    "name": "Release - Dec 2022",
    "start_date": "2022-11-16",
    "finish_date": "2022-12-30"
  },
  {
    "name": "Release - Nov 2022",
    "start_date": "2022-10-03",
    "finish_date": "2022-11-16"
  },
  {
    "name": "Release - Apr 2023",
    "start_date": "2023-03-01",
    "finish_date": "2023-04-27"
  },
  {
    "name": "Release - Jun 2023",
    "start_date": "2023-04-28",
    "finish_date": "2023-06-26"
  },
  {
    "name": "Release - Aug 2023",
    "start_date": "2023-06-27",
    "finish_date": "2023-08-23"
  },
  {
    "name": "Release - Oct 2023",
    "start_date": "2023-08-24",
    "finish_date": "2023-10-20"
  },
  {
    "name": "Release - Dec 2023",
    "start_date": "2023-10-23",
    "finish_date": "2023-12-19"
  },
  {
    "name": "Release - Feb 2024",
    "start_date": "2023-12-20",
    "finish_date": "2024-02-15"
  },
  {
    "name": "Release - Apr 2024",
    "start_date": "2024-02-16",
    "finish_date": "2024-04-15"
  },
  {
    "name": "Release - Jun 2024",
    "start_date": "2024-04-16",
    "finish_date": "2024-06-12"
  },
  {
    "name": "Aug 2024 - Release",
    "start_date": "2024-08-01",
    "finish_date": "2024-08-31"
  },
  {
    "name": "Oct 2024 - Release",
    "start_date": "2024-10-01",
    "finish_date": "2024-10-31"
  },
  {
    "name": "Dec 2024 - Release",
    "start_date": "2024-12-01",
    "finish_date": "2024-12-31"
  },
  {
    "name": "July 2024",
    "start_date": "2024-07-01",
    "finish_date": "2024-07-31"
  },
  {
    "name": "Sept 2024",
    "start_date": "2024-09-01",
    "finish_date": "2024-09-30"
  },
  {
    "name": "Nov 2024",
    "start_date": "2024-11-01",
    "finish_date": "2024-11-30"
  },
  {
    "name": "Jan 2025",
    "start_date": "2025-01-01",
    "finish_date": "2025-01-31"
  },
  {
    "name": "Feb 2025 - Release",
    "start_date": "2025-02-01",
    "finish_date": "2025-02-28"
  },
  {
    "name": "March 2025",
    "start_date": "2025-03-01",
    "finish_date": "2025-03-31"
  },
  {
    "name": "April 2025 - Release",
    "start_date": "2025-04-01",
    "finish_date": "2025-04-30"
  },
  {
    "name": "May 2025",
    "start_date": "2025-05-01",
    "finish_date": "2025-05-31"
  },
  {
    "name": "June 2025 - Release",
    "start_date": "2025-06-01",
    "finish_date": "2025-06-30"
  },
  {
    "name": "July 2025",
    "start_date": "2025-07-01",
    "finish_date": "2025-07-31"
  },
  {
    "name": "Aug 2025 - Release",
    "start_date": "2025-08-01",
    "finish_date": "2025-08-31"
  },
  {
    "name": "Sept 2025",
    "start_date": "2025-09-01",
    "finish_date": "2025-09-30"
  },
  {
    "name": "Oct 2025 - Release",
    "start_date": "2025-10-01",
    "finish_date": "2025-10-31"
  },
  {
    "name": "Nov 2025",
    "start_date": "2025-11-01",
    "finish_date": "2025-11-30"
  },
  {
    "name": "Dec 2025 - Release",
    "start_date": "2025-12-01",
    "finish_date": "2025-12-31"
  },
  {
    "name": "Jan 2026",
    "start_date": "2026-01-01",
    "finish_date": "2026-01-31"
  },
  {
    "name": "Feb 2026 - Release",
    "start_date": "2026-02-01",
    "finish_date": "2026-02-28"
  },
  {
    "name": "Mar 2026",
    "start_date": "2026-03-01",
    "finish_date": "2026-03-31"
  },
  {
    "name": "Apr 2026 - Release",
    "start_date": "2026-04-01",
    "finish_date": "2026-04-30"
  },
  {
    "name": "May 2026",
    "start_date": "2026-05-01",
    "finish_date": "2026-05-31"
  },
  {
    "name": "Jun 2026 - Release",
    "start_date": "2026-06-01",
    "finish_date": "2026-06-30"
  }
]

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

A GitHub issue is automatically **closed** after creation based on the work item type:

| ADO Type | Closed when state is… |
|---|---|
| `Bug` | `Closed` only |
| `Task` (maps to `type: task` or `type: feature` in GitHub) | `Closed` or `Removed` |
| All other types (Epic, User Story, etc.) | `Closed`, `Done`, `Removed`, or `Resolved` |

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

---

## Fail-safe Logging

Every full migration run (`python migrate.py`) produces two artefacts:

| File | Purpose |
|---|---|
| `migration.log` | Human-readable timestamped log. One line per success (`ADO #X → GH #Y`), one line per failure with the full error message, plus run-start / run-end summary lines. Appended on every run so the full history is preserved. |
| `migration_errors.json` | Machine-readable JSON ledger of **unresolved** failures: `{ "ado_id": { "title", "error", "timestamp" } }`. An entry is automatically removed the next time that item migrates successfully, so the file always reflects exactly what still needs attention. |

On each run the console prints how many items previously failed, so you know upfront that retries are queued.

---

## Pre-migration Checklist

Run these steps in order before starting the full migration.

### 1. Count and inspect the work item scope

```bash
python migrate.py count
```

Prints the exact number of work items that will be migrated, broken down by type and state, cross-referenced with `state.json` to show how many are still pending. Verify the total matches your expectations — the WIQL query fetches **all** work items in the project with no type or date filter.

### 2. Create and verify GitHub labels

```bash
# Create all missing labels (safe to run repeatedly — skips labels that already exist)
python setup_github.py

# Confirm every label the migration will apply is present in the repo
python setup_github.py verify
```

`setup_github.py` compares `LABELS_TO_CREATE` against the live GitHub repo and only calls the API for labels that are genuinely absent. `verify` cross-references the labels that `mapper.py` emits against the repo and exits with code `1` if anything is missing, making it easy to add to a pre-flight script.

### 3. Dry-run at least one item of each type

```bash
python migrate.py test <BUG_ID>
python migrate.py test <TASK_ID>
python migrate.py test <FEATURE_ID>
python migrate.py test <CLOSED_ID>
```

Verify the rendered body, label list, assignee, and `WILL BE CLOSED` flag for each type before touching 2 500 items.

### 4. Validate assignee name matching

Check a few real `System.AssignedTo.displayName` values from your ADO data against `resolve_github_username()`. Names with accented characters, middle names, or nicknames may not match any entry in `ADO_GH_USER_MAP`. When a name does not match the issue is created without an assignee — no error is thrown.

### 5. Back up state.json before running

`state.json` is the only record of `ado_id → github_issue_number` mappings. Copy it somewhere safe. If it is lost or corrupted you have no way to detect duplicates on a re-run.

### 6. During the run

- Keep the terminal in view — errors are printed in real time. If you see a burst of ❌ lines (GitHub outage, token expiry), kill the process. State and the error ledger are saved after **every individual item**, so you lose at most one item’s progress.
- Monitor `migration.log` in a second terminal: `Get-Content migration.log -Wait`
- GitHub’s secondary rate limit is roughly 80–100 write requests per minute. With 2 500 items the default sleeps (`0.5 s` between items, `0.3 s` between comments) should stay under the limit, but slow down the sleeps if you see `429` / `403` errors.

### 7. After the run

- Check `migration_errors.json`. If it is non-empty, fix the root cause and re-run — failed items are retried automatically.
- Spot-check 5–10 random issues on GitHub: confirm labels, closed state, comments, and the `> Migrated from Azure DevOps` header.
- ADO work items are never modified by this script, so you can compare source and destination freely.