# ADO → GitHub Migration Guide

This document describes how Azure DevOps (ADO) work items are migrated to GitHub Issues using this toolset.

---

## Project Structure

```
ado-to-github-migration/
├── clients/                    # API client modules
│   ├── ado_client.py           #   Azure DevOps REST API helpers
│   └── github_client.py        #   GitHub REST + GraphQL helpers
├── setup/                      # One-time setup & utility scripts
│   ├── setup_github.py         #   Create all required labels
│   ├── create_milestones.py    #   Create GitHub milestones from ADO iterations
│   ├── create_area_fields.py   #   Add 'Area' custom field to GitHub ProjectsV2
│   └── fetch_areas_and_iterations.py  # Print ADO area/iteration trees (debug)
├── config.py                   # All env-var config and label/state mappings
├── mapper.py                   # ADO work item → GitHub issue field mapper
├── milestone_map.py            # ADO iteration path → GitHub milestone number
├── migrate.py                  # Main migration entry point
├── reporter.py                 # Migration progress reporter (see Reporting section)
├── state.json                  # Migration progress tracker (auto-generated)
├── migration_errors.json       # Error ledger (auto-generated)
└── requirements.txt
```

---

## Commands

### migrate.py

| Command | Description |
|---|---|
| `python migrate.py` | **Full migration** — migrates all pending work items, resuming from `state.json` |
| `python migrate.py count` | **Count preview** — queries ADO and prints a breakdown of all work items by type and state, plus how many are already migrated vs. still pending. Nothing is created. |
| `python migrate.py report` | **Progress report** — reads local state files and prints a full migration status report. No API calls. See [Reporting](#migration-progress-reporting) for details. |
| `python migrate.py report --detailed` | **Detailed report** — same as above with full item-level lists for every issue category |
| `python migrate.py report --fetch-totals` | **Report with totals** — adds ADO total count and percentage completion (requires ADO connection) |
| `python migrate.py test <ADO_ID>` | **Dry-run** — prints the GitHub issue that would be created for one work item; nothing is submitted |
| `python migrate.py single <ADO_ID>` | **Single item migration** — creates a GitHub issue for one specific ADO work item, updates `state.json`, and returns the GitHub issue number |
| `python migrate.py multiple <N>` | **Batch migration** — migrates the next N not-yet-migrated items in ascending ADO ID order |
| `python migrate.py discover <ADO_ID>` | **Field discovery** — prints every ADO field reference name and value for a work item; useful for identifying custom fields |

### setup/setup_github.py

| Command | Description |
|---|---|
| `python setup/setup_github.py` | **Setup** — creates all required GitHub labels and milestones. Only labels that do not already exist in the repo are created; existing ones are reported and skipped. |
| `python setup/setup_github.py verify` | **Verify** — compares the labels the migration will apply against what is currently in the GitHub repo. Prints a clear Present / Missing / Extra report. Exits with code `1` if any required label is absent. |

### setup/create_milestones.py

| Command | Description |
|---|---|
| `python setup/create_milestones.py` | Creates or updates GitHub milestones from the hardcoded ADO iteration list. Safe to re-run — existing milestones are updated, not duplicated. |

### setup/create_area_fields.py

| Command | Description |
|---|---|
| `python setup/create_area_fields.py` | Adds an `Area` Single Select custom field to all GitHub ProjectsV2 in the org. |
| `python setup/create_area_fields.py 1 5` | Limits the operation to projects with those numbers. |

---

## Inspecting Areas & Iterations

Two utility functions in `clients/ado_client.py` let you fetch the full area-path and iteration trees directly from the ADO Classification Nodes API.

| Function | REST Endpoint |
|---|---|
| `get_all_areas(depth=10)` | `GET .../wit/classificationnodes/Areas?$depth={depth}&api-version=7.1` |
| `get_all_iterations(depth=10)` | `GET .../wit/classificationnodes/Iterations?$depth={depth}&api-version=7.1` |

Both return the raw ADO response dict with nested `children` lists. The `depth` parameter controls how many levels of the tree are returned (default `10`).

### Usage

```python
from clients.ado_client import get_all_areas, get_all_iterations
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

Milestone mapper function was created to map the ported issues to the appropriate Milestone.

---

## Work Item Type Mapping

ADO's `System.WorkItemType` is used to determine the GitHub issue type label and native Issue Type.
For items where `System.WorkItemType = Task` the classifier uses a field-presence heuristic
(evaluated top-to-bottom — first match wins):

| Priority | Signal | GitHub Type |
|---|---|---|
| 1 | `System.WorkItemType = Bug` | **Bug** |
| 2 | `System.WorkItemType = Task` **and** `Microsoft.VSTS.Scheduling.StoryPoints` key is present in the ADO response (value may be null) | **Feature** — User Story masquerading as a Task |
| 3 | `System.WorkItemType = Task` **and** any of `OriginalEstimate`, `RemainingWork`, or `CompletedWork` keys are present in the ADO response | **Task** — real task with hour-tracking fields |
| 4 | `System.WorkItemType = Task` — no Story Points, no Effort fields | **Task** — fail-safe: ambiguous items default to Task |
| 5 | Any other recognised ADO type (`User Story`, `Feature`, `Epic`, `Feature Request`, `Product Backlog Item`) | **Feature** |
| 6 | Any other recognised ADO type (`Test Case`, `Test Plan`, `Test Suite`, `Impediment`) | **Task** |
| 7 | `Issue` ADO type | **Bug** |
| 8 | Completely unrecognised ADO type | **Task** — fail-safe |

> **Field presence vs. value**: checks use `key in fields`, not `fields[key] is not None`.
> A field returned by ADO with a `null` value still counts as "present" — this correctly
> handles items where the Story Points or Effort fields exist on the work item template but
> have never been filled in.

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

All configuration lives in a `.env` file (loaded via `python-dotenv`) at the repository root. Create this file before running any migration commands.

### .env File Template

```dotenv
# Azure DevOps
ADO_ORG=your-ado-organization
ADO_PROJECT=your-ado-project
ADO_PAT=your-ado-personal-access-token

# GitHub
GH_TOKEN=your-github-personal-access-token

# ADO display name → GitHub username mapping (JSON format)
ADO_GH_USER_MAP={"Luis Pandolfi":"luispandolfi","Brian Lagunas":"brianlagunas","Zdravko Kolev":"zdrawku"}
```

### Configuration Variables

| Variable | Description | Example |
|---|---|---|
| `ADO_ORG` | Azure DevOps organization name | `infragistics` |
| `ADO_PROJECT` | Azure DevOps project name | `BusinessTools` |
| `ADO_PAT` | ADO Personal Access Token with **Read** scope on Work Items | `8NrxboNt...` |
| `GH_TOKEN` | GitHub Personal Access Token with **repo**, **issues**, and **project** scopes | `github_pat_11A...` |
| `ADO_GH_USER_MAP` | JSON mapping of ADO display names to GitHub usernames. Used to assign items to the correct GitHub user. | `{"Zdravko Kolev":"zdrawku","Brian Lagunas":"brianlagunas"}` |

### Building ADO_GH_USER_MAP

The `ADO_GH_USER_MAP` is a JSON object that maps the exact ADO display name (from `System.AssignedTo.displayName`) to the corresponding GitHub username. 

**Steps to build the map:**
1. Query your ADO project and collect all unique assignee display names
2. Look up each person's GitHub username in your organization
3. Create a JSON object with the mapping: `{"ADO Display Name": "github-username", ...}`
4. Paste the entire JSON object (with escaped quotes) as the value of `ADO_GH_USER_MAP`

**Example:**
```dotenv
ADO_GH_USER_MAP={"Luis Pandolfi":"luispandolfi","Brian Lagunas":"brianlagunas","Zdravko Kolev":"zdrawku","Hristo Anastasov":"hanastasov"}
```

If an ADO user has no entry in the map, the migrated issue will be created without an assignee (no error is thrown).

### Additional Configuration

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

## Rate Limit Considerations
GitHub’s secondary rate limit is roughly 80–100 write requests per minute. With 2 500 items the default sleeps (`0.5 s` between items, `0.3 s` between comments) should stay under the limit, but slow down the sleeps if you see `429` / `403` errors.

Per-item API call costs (for 2663 items):

1 POST /issues + ~2 POST /issues/{n}/comments + close_issue (if closed) = ~4 REST calls
Per project × 2: addProjectV2ItemById + set iteration + set Priority + set Area + set issue type = ~10 GraphQL mutations
~14 API calls per item × 2663 = ~37,000 calls

GitHub's REST and GraphQL limits are both 5,000 requests/hour, so this run needs ~7.5 hours at full speed — well over your overnight window unless you throttle. Current sleep of 0.5s between items is way too aggressive and will trigger secondary rate limits. At ~2s between items the run takes ~1.5h in sleep alone, comfortably within limits.

### Current gaps that will kill an overnight run:

_handle_rate_limit doesn't handle HTTP 429 (secondary rate limit), only 403
_graphql has zero rate-limit handling — GraphQL mutations are the majority of calls
close_issue has no retry loop at all
ADO client has zero retry logic — a single 429 from ADO crashes the whole run
Inter-item sleep is only 0.5s (too fast — GitHub secondary limits kick in)

### Changes made

#### [clients/github_client.py](clients/github_client.py)

| Fix | Where | Why |
|---|---|---|
| `_handle_rate_limit` now catches **HTTP 429** with `Retry-After` header | All REST callers | GitHub secondary rate limits return 429, not just 403 |
| `_handle_rate_limit` handles **403 with `Retry-After`** (secondary limit) | All REST callers | GitHub's secondary limit can return 403 + `Retry-After` without "rate limit" in the body |
| **Proactive quota check**: sleeps until reset when `X-RateLimit-Remaining < 50` | All REST callers | Prevents ever exhausting the quota mid-run |
| `_graphql` now has a **retry loop** (429 → wait, 403 → wait, 5xx → exponential backoff) | All GraphQL mutations (project, issue type, parent link) | GraphQL calls are the majority of API calls and had zero retry logic |
| `close_issue` now has a `while True` **retry loop** like `create_issue`/`add_comment` | Closing resolved items | Had no rate-limit recovery at all |

#### [clients/ado_client.py](clients/ado_client.py)

| Fix | Where |
|---|---|
| New `_ado_request()` helper: retries on **429 + Retry-After** and **5xx with exponential backoff** | `get_all_work_item_ids`, `get_work_items_batch`, `get_work_item_comments` |

#### [migrate.py](migrate.py)

| Change | Before → After | Reason |
|---|---|---|
| Inter-item sleep | 0.5s → **2s** | 2663 × ~12 calls = ~32k API calls total. At 0.5s that's ~17k calls/hr, 3× over GitHub's 5,000/hr limit |
| Per-comment sleep | 0.3s → **1s** | Items with many comments were bursting too fast |
Time estimate at new pacing
~2,663 items × ~3s per item (2s sleep + ~1s processing) ≈ 2.2 hours — comfortably fits in a 4–5 hour overnight window even if some items trigger waits.
If rate limit waits do trigger, the script pauses and resumes automatically — state.json already checkpoints every item, so the run is fully resumable if anything goes wrong.

### Time estimate at new pacing
~2,663 items × ~3s per item (2s sleep + ~1s processing) ≈ 2.2 hours

If rate limit waits do trigger, the script pauses and resumes automatically — state.json already checkpoints every item, so the run is fully resumable if anything goes wrong

# Gaps found — 23rd of March

### config.py

| Fix | Impact |
|---|---|
| Added `"Feature Request": "feature-request"` to `WORK_ITEM_TYPE_LABELS` | 58 items were unrecognised |
| Added 6 missing states to `STATE_LABELS`: `In Code Review`, `In Test`, `Completed`, `Declined`, `Awaiting Test`, `Design` | 45 items had no state label |
| Added `"Completed"` and `"Declined"` to `CLOSED_STATES` | 22 Feature Request / Test Suite items (`Completed`×16, `Declined`×9) would have stayed open |

### mapper.py

| Fix | Impact |
|---|---|
| `resolve_github_type` now looks up `WORK_ITEM_TYPE_LABELS` for all non-Bug/non-Task types instead of falling back to `"type: unknown"` | 592 items across User Story, Epic, Feature, Feature Request, Issue, Test Case, Test Plan, Test Suite |
| Introduced `_GITHUB_ISSUE_TYPE_MAP` and updated `resolve_github_issue_type_name` to return correct GitHub native types (`Feature`/`Task`/`Bug`) for all ADO types | Same 592 items were all being stamped with native type `Bug` |

### setup_github.py

| Fix | Impact |
|---|---|
| Added `type: user-story` and `type: feature-request` to `LABELS_TO_CREATE` | `verify` command would have reported them as missing |
| Added 6 new state labels to `LABELS_TO_CREATE` | Labels would silently fail to apply on GitHub if not pre-created |

`tests/test_type_state_coverage.py` — new file with 70 tests covering all 30 observed (type, state) pairs, every mapping function, and label/setup consistency.

# Incremental runs — two changes make repeat runs efficient:

**ado_client.py** — fetch_all_work_items() now accepts an optional skip_ids set. The WIQL query still fetches all IDs (so totals are accurate), but the expensive batch-detail API calls are only made for IDs not in the set.

**migrate.py** — migrate() now passes already_migrated IDs as skip_ids. On a repeat run a week later with, say, 50 new items, only those 50 items are downloaded from ADO instead of all 2666.

**!! Running python migrate.py again at any point is fully safe !!**: state.json prevents duplicates, only genuinely new ADO work items get a GitHub issue created.

# Helper methods

Each function is now runnable directly from the terminal. Usage:

**No arguments needed**
python clients/ado_client.py get_all_work_item_ids
python clients/ado_client.py fetch_all_work_items
python clients/ado_client.py count_work_items_by_type
python clients/ado_client.py get_iterations
python clients/ado_client.py get_all_areas
python clients/ado_client.py get_all_iterations

**Require --id**
python clients/ado_client.py get_work_item_comments --id 12345
python clients/ado_client.py discover_work_item_fields --id 12345

**Require --ids (one or more)**
python clients/ado_client.py get_work_items_batch --ids 1 2 3 4 5

All results are printed as formatted JSON. count_work_items_by_type gets a human-readable table instead since it returns a nested dict that's more readable that way.

## Migrate the first 100 items

```
python migrate.py multiple 100   # migrates the oldest 100 not-yet-migrated items
python migrate.py multiple 100   # next run picks up items 101-200
python migrate.py multiple 100   # continues with 201-300, and so on
```

Notes:
What happens under the hood:

- All ADO IDs are fetched via WIQL (already sorted ascending by ID)
- IDs already in state.json are filtered out
- The first N of the remaining IDs form the batch — full details are fetched only for those N
- Each item is migrated and checkpointed to state.json immediately, so you can interrupt mid-batch and the next call picks up exactly - where it left off
- At the end it prints how many items are still remaining and reminds you to run the command again
- The batch size is whatever number you pass, so python migrate.py multiple 500 would do 500 at a time, etc. python migrate.py (no - args) still runs the full migration as before.

## Reporting Helper Methods

```bash
# Summary report (default — no API calls)
python migrate.py report

# Full detail — item-level lists for every issue section
python migrate.py report --detailed

# Include ADO total count and percentage bar (requires ADO_PAT)
python migrate.py report --fetch-totals

# Both flags combined
python migrate.py report --detailed --fetch-totals
```

# Implementind Development mapper/linker ensuring the linked PRs and branches from Azure DevOps are migrated into the GitHub issues

Changes made:

**mapper.py**

Added _resolve_vstfs_github_url() — parses the vstfs URL into (guid, prNumber), checks ADO_GITHUB_CONNECTION_MAP first, then falls back to the GitHub REST search API
Added _search_gh_pr_in_org() — uses GET /search/issues?q=is:pr+org:…+{N} (REST, works with your token) and filters to exact number matches. If one repo has PR #N → resolved. If multiple repos have PR #N → warns and asks you to add the GUID to the config map
Updated _parse_vstfs_github() to call the resolver and populate github_url
Fixed extract_dev_links() to deduplicate links (avoids double-counting when a PR appears as both artifact + explicit hyperlink)
config.py

Added ADO_GITHUB_CONNECTION_MAP — loaded from .env, maps connection GUID → "owner/repo". Takes priority over search (faster + handles ambiguous PR numbers across repos)
migrate.py

Fixed the PR linker filter: was source == "hyperlink" (never matched artifact links) → now github_url is set and URL contains "pull"
ado_client.py

Added discover_github_connections() — scans work items and prints all GUIDs with a ready-to-paste .env snippet (run python ado_client.py discover_github_connections)

| GUID         | Type                     | Usage                | Status                                 |
|--------------|--------------------------|----------------------|----------------------------------------|
| dbf634f2…    | PRs / Commits / Branches | 45 PRs, 37 commits   | ✅ Infragistics-BusinessTools/Reveal   |
| 2d16b998…    | PRs / Commits            | 6 PRs, 3 commits     | ✅ Infragistics-BusinessTools/Shared   |
| 0b0d6b44…    | PRs / Commits            | 2 PRs only           | ❓ Services, Slingshot, or Reveal.Sdk.AI|
| f5f3ea1e…    | GitHub Issues (not PRs)  | 276 issue links      | ✅ RevealBi/Reveal.Sdk (body link only — cross-org, no Development sidebar) |

---

# Migration Progress Reporting

The `reporter.py` module provides a structured, offline progress report based entirely on the local state files — no API calls are needed by default.

### What the report covers

| Section | Description |
|---|---|
| **Overall Progress** | Migrated count, total (optional), pending, and percentage completion |
| **Batch Run History** | Each invocation's start/end timestamp, batch size, pending-at-start, and success/failure breakdown |
| **Failed Items** | Items in `migration_errors.json` with their error messages, timestamps, and ADO titles |
| **PR / Branch Link Issues** | All `git push` / Development-section links that could not be established, with the affected GitHub issue numbers |
| **Parent / Hierarchy Link Issues** | Every parent→child relationship that failed, grouped by failure type |
| **Action Checklist** | Concrete next steps for each category of detected issue |

### Helper Commands

```bash
# Summary report (default — no API calls)
python migrate.py report

# Full detail — item-level lists for every issue section
python migrate.py report --detailed

# Include ADO total count and percentage bar (requires ADO_PAT)
python migrate.py report --fetch-totals

# Both flags combined
python migrate.py report --detailed --fetch-totals
```

### Data sources

The reporter reads three local files written automatically during every migration run:

| File | Contents |
|---|---|
| `state.json` | `{ "ado_id": github_issue_number }` — every successfully migrated item |
| `migration_errors.json` | `{ "ado_id": { "title", "error", "timestamp" } }` — items that raised an exception |
| `migration.log` | Line-by-line event log used to extract batch history, PR link failures, and parent link failures |

### Example output

```
================================================================
  ADO → GitHub Migration Progress Report
  Generated: 2026-03-24 08:00:00 UTC
================================================================

────────────────────────────────────────────────────────────────
  OVERALL PROGRESS
────────────────────────────────────────────────────────────────
  Migrated  :    342
  Total     :    950
  Pending   :    608
  Progress  : [███████████░░░░░░░░░░░░░░░░░░░] 36.0%
  Failed    :      5  (in migration_errors.json)

────────────────────────────────────────────────────────────────
  BATCH RUN HISTORY  (3 run(s))
────────────────────────────────────────────────────────────────
  [ 1] Migration run
        Start   : 2026-03-21 09:00:00
        End     : 2026-03-21 09:45:12
        Pending at start : 950 (already done: 0)
        Result  : ✅ 200  ❌ 1

  [ 2] Batch run (batch=100)
        Start   : 2026-03-22 14:00:00
        End     : 2026-03-22 14:22:08
        Pending at start : 750 (already done: 200)
        Result  : ✅ 100  ❌ 0

  [ 3] Batch run (batch=100)
        Start   : 2026-03-23 10:30:00
        End     : 2026-03-23 10:55:33
        Pending at start : 650 (already done: 300)
        Result  : ✅ 42  ❌ 4

────────────────────────────────────────────────────────────────
  FAILED ITEMS  (5)
────────────────────────────────────────────────────────────────
  5 item(s) need attention. Run with --detailed to see the full list.
  Quick view: open migration_errors.json

────────────────────────────────────────────────────────────────
  PR / BRANCH LINK ISSUES  (2)
────────────────────────────────────────────────────────────────
  These Development-section links could not be established:

  2 PR link(s) failed. Run with --detailed to see URLs.

  Affected GitHub issues: #117, #284

────────────────────────────────────────────────────────────────
  PARENT / HIERARCHY LINK ISSUES  (1)
────────────────────────────────────────────────────────────────

  [NEVER-MIGRATED]  Parent never migrated (children are unlinked)  (1 item(s))
    Parent ADO IDs: #38901

────────────────────────────────────────────────────────────────
  ACTION CHECKLIST
────────────────────────────────────────────────────────────────
  ☐  Re-run failed items:
       Review migration_errors.json, fix root causes, then re-run.
       Individual items can be re-run with:
         python migrate.py single <ADO_ID>
  ☐  Fix PR / Development section links:
       Check ADO_GITHUB_CONNECTION_MAP in config.py and ensure
       all GitHub connection GUIDs are mapped to their repos.
       Then re-run the affected items using migrate.py single.
  ☐  Fix parent hierarchy links:
       Some parent items were never migrated. Migrate them first
       with 'python migrate.py single <PARENT_ADO_ID>', then
       re-run the child items to establish the parent link.

================================================================
  State file  : state.json  (342 migrated)
  Error file  : migration_errors.json  (5 failed)
  Full log    : migration.log
  Tip: Use --detailed for full item lists, --fetch-totals for ADO count.
================================================================
```

### Interpreting the report

**Overall Progress** — The migrated count always comes from `state.json`.  The percentage bar only appears when `--fetch-totals` is passed (adds one ADO API call).

**Batch Run History** — Each block corresponds to one invocation of `migrate.py` (either `python migrate.py` or `python migrate.py multiple N`).  If the process was interrupted before it finished, the block shows `⚠  interrupted` with no end timestamp and zeroed success/failed counts.

**Failed Items (summary mode)** — Shows the count only.  Use `--detailed` to see the ADO ID, title, timestamp, and full error message for every failed item.

**Failed Items (detailed mode)** — Displays a table with every item in `migration_errors.json`.  After fixing the underlying cause, re-run with `python migrate.py single <ADO_ID>`.  Successful re-runs clear the entry from `migration_errors.json` automatically.

**PR / Branch Link Issues** — Summary mode lists the affected GitHub issue numbers so you can navigate straight to them.  Detailed mode adds the exact PR URL and the timestamp from the log.  Root causes are usually an unmapped GitHub connection GUID — add the GUID to `ADO_GITHUB_CONNECTION_MAP` in `config.py`, then re-run the item.

**Parent / Hierarchy Link Issues** — Grouped by failure category:

| Category | Meaning | Fix |
|---|---|---|
| `NEVER-MIGRATED` | Parent ADO item has no matching GitHub issue | Migrate the parent first with `migrate.py single`, then re-run the child |
| `FAILED` | The GraphQL mutation to set the parent link returned an error | Check `GH_TOKEN` has project-write scope; then re-run |
| `AUTO-FAILED` | Auto-migration of the parent before the child raised an exception | Check `migration_errors.json` for the parent's error; fix and retry |
| `NOT-FOUND` | Parent ADO item does not exist in ADO at all | No fix needed — the ADO data has an orphaned reference |
| `DEFERRED-FAILED` | The deferred parent link (end-of-run resolution) failed | Check token scopes; then re-run just the child item |

### Programmatic use

`reporter.py` can also be imported directly:

```python
from reporter import collect_report_data, print_report

report = collect_report_data(fetch_totals=False)
print(f"Migrated: {report.migrated_count}")
print(f"Failed:   {report.failed_count}")
print(f"PR issues: {len(report.pr_link_issues)}")

# Full formatted output
print_report(report, detailed=True)
```
