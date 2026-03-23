# Azure DevOps (ADO) → GitHub Migration Tool

A Python toolset for migrating Azure DevOps work items to GitHub Issues with full fidelity, including comments, assignments, milestones, and custom fields.

## Overview

This tool automates the migration of thousands of work items from Azure DevOps to GitHub while:

✅ Preserving all work item metadata (title, description, state, priority, severity, etc.)  
✅ Migrating discussion comments with author and timestamp information  
✅ Mapping ADO assignees to GitHub users via configurable name mapping  
✅ Setting GitHub ProjectV2 fields (iteration, priority, area, issue type)  
✅ Handling parent-child relationships (epics → issues)  
✅ Supporting resume-on-failure with automatic checkpointing  
✅ Implementing comprehensive rate-limit handling for safe overnight runs  

## Features

- **Fully resumable**: Progress is saved to `state.json` after every item; restart anytime without duplicates
- **Rate-limit safe**: Built-in retry logic, exponential backoff, and adaptive throttling to handle both GitHub and ADO rate limits
- **Comprehensive logging**: All activity recorded to `migration.log` with human-readable format; errors tracked separately in `migration_errors.json`
- **Dry-run & test modes**: Preview what will be created before running the full migration
- **Custom field mapping**: Supports ADO description, repro steps, symptom, expected result, acceptance criteria, and more
- **Label automation**: Generates labels from work item type, priority, severity, triage status, state, and ADO tags
- **Configurable**: All mappings (users, iterations, priorities, areas) live in `config.py` and `.env`

## Prerequisites

- Python 3.11+ 
- ADO organization and project with read access
- GitHub repository with admin or maintain permissions
- Personal Access Tokens for both ADO and GitHub

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Infragistics-BusinessTools/Reveal.git
cd ado-to-github-migration
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the repository root with your credentials and mappings:

```dotenv
# Azure DevOps
ADO_ORG=your-ado-organization
ADO_PROJECT=your-ado-project
ADO_PAT=your-ado-personal-access-token

# GitHub
GH_TOKEN=your-github-personal-access-token

# ADO display name → GitHub username mapping (JSON)
ADO_GH_USER_MAP={"Luis Pandolfi":"luispandolfi","Brian Lagunas":"brianlagunas"}
```

See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md#configuration) for detailed configuration instructions, including how to build the `ADO_GH_USER_MAP`.

## Quick Start

### 1. Preview Work Items

```bash
python migrate.py count
```

Shows how many work items will be migrated, broken down by type and state.

### 2. Set Up GitHub (one-time)

```bash
python setup/setup_github.py
```

Creates all required labels and milestones in the GitHub repository.

### 3. Dry-Run a Single Item

```bash
python migrate.py test 1234
```

Prints the GitHub issue that would be created for ADO work item #1234—nothing is submitted.

### 4. Run Full Migration

```bash
python migrate.py
```

Migrates all pending work items. Safe to restart anytime; already-migrated items are skipped automatically.

## Commands

### Main Migration Script

```bash
python migrate.py                    # Full migration (resumable from state.json)
python migrate.py count             # Preview: count & breakdown of work items
python migrate.py test <ADO_ID>     # Dry-run: print the issue that would be created
python migrate.py single <ADO_ID>   # Migrate one work item and return its GitHub issue number
python migrate.py discover <ADO_ID> # Print all fields for a work item (for discovering custom fields)
```

### Setup & Utilities

```bash
python setup/setup_github.py              # Create GitHub labels and milestones
python setup/setup_github.py verify       # Verify all required labels exist
python setup/create_milestones.py         # Create/update GitHub milestones from ADO iterations
python setup/create_area_fields.py        # Add 'Area' custom field to GitHub ProjectV2
python setup/create_area_fields.py 1 5    # Limit to specific project numbers
```

## Performance & Rate Limiting

The tool is optimized for safe overnight runs of 2,000+ items:

- **Estimated runtime**: ~2–3 hours for 2,663 items (including inter-item pauses)
- **Rate limit handling**: Automatic retry on GitHub 429 (secondary rate limit) and ADO 429
- **Exponential backoff**: 5xx server errors retry with 5s, 10s, 20s, 40s delays
- **Proactive throttling**: Inter-item delays (2s) and per-comment delays (1s) keep the script well under GitHub's 5,000 req/hr limit
- **Resumable**: If interrupted, restart with `python migrate.py`—no data loss

For detailed timing and rate-limit strategy, see [Rate Limit Considerations](MIGRATION_GUIDE.md#rate-limit-considerations) in the migration guide.

## Monitoring

### During the Run

```bash
# In terminal 1: run the migration
python migrate.py

# In terminal 2: monitor the log in real time
Get-Content migration.log -Wait     # PowerShell
tail -f migration.log               # macOS / Linux
```

### After the Run

- Check `migration_errors.json` for any failed items
- Review `migration.log` for the full run summary
- Spot-check 5–10 random issues on GitHub to verify labels, state, and comments

## File Structure

```
ado-to-github-migration/
├── clients/
│   ├── ado_client.py            # Azure DevOps REST API helpers
│   └── github_client.py         # GitHub REST + GraphQL helpers
├── setup/
│   ├── setup_github.py          # Create labels & milestones
│   ├── create_milestones.py     # ADO iteration → GitHub milestone mapper
│   ├── create_area_fields.py    # Add ProjectV2 Area field
│   └── fetch_areas_and_iterations.py  # Debug utility
├── config.py                    # Label, state, and iteration mappings
├── mapper.py                    # ADO work item → GitHub issue field mapping
├── milestone_map.py             # Iteration path → milestone number resolver
├── migrate.py                   # Main migration entry point
├── state.json                   # Migration progress (auto-generated)
├── migration_errors.json        # Error ledger (auto-generated)
├── migration.log                # Full activity log (auto-generated)
├── MIGRATION_GUIDE.md           # Detailed documentation
├── README.md                    # This file
└── requirements.txt
```

## Configuration

All configuration lives in `.env` and `config.py`:

| File | Purpose |
|---|---|
| `.env` | ADO/GitHub credentials and user name mappings |
| `config.py` | Label mappings, iteration mappings, priority mappings, custom fields |

See [Configuration](MIGRATION_GUIDE.md#configuration) in the migration guide for complete details.

## Known Limitations

### Attachments

Attachments cannot be migrated automatically due to GitHub API limitations. When a work item has attachments, the migration script adds a warning banner to the issue with instructions for manual migration. See [Attachments — Not Automatically Migrated](MIGRATION_GUIDE.md#attachments--not-automatically-migrated) for the full manual process.

### Custom Fields

If your ADO work items contain custom fields beyond those in `mapper.py`, use the `discover` command to find the field reference names:

```bash
python migrate.py discover 1234
```

Then add mappings to `mapper.py` and `config.py` as needed.

## Troubleshooting

### Migration Fails with API Errors

**Symptoms**: Errors like `401 Unauthorized`, `403 Forbidden`, or `404 Not Found`

**Solution**:
1. Verify your `.env` credentials are correct
2. Check token scopes: ADO needs **Read** on Work Items; GitHub needs **repo**, **issues**, and **project**
3. Confirm the GitHub repo is accessible: `python setup/setup_github.py verify`

### Rate Limit Errors (429 / 403)

**Symptoms**: Repeated `⏳ Rate limit hit. Waiting Xs...` messages

**Solution**:
- This is expected and normal—the script will pause and retry automatically
- If it happens frequently, increase the inter-item sleep in `migrate.py` (currently 2s)

### "ADO #X was already migrated as GitHub Issue #Y"

**Meaning**: The work item is in `state.json`, so the migration script skipped it to avoid duplicates.

**Solution**: Either ignore (it's already done) or remove the entry from `state.json` to re-migrate it.

### Missing Labels or Milestones

**Solution**: Run the setup script:
```bash
python setup/setup_github.py
python setup/create_milestones.py
```

### Assignees Not Matching

**Meaning**: Some ADO users were not assigned in GitHub issues.

**Solution**: Check your `ADO_GH_USER_MAP` in `.env`. Users not in the map are created unassigned. Run `python migrate.py discover <ID>` to see the exact `System.AssignedTo.displayName` values.

## Support & Documentation

- **Full migration walkthrough**: See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
- **Field mapping details**: See [Field Mapping](MIGRATION_GUIDE.md#field-mapping-bug-work-items) in the guide
- **Pre-migration checklist**: See [Pre-migration Checklist](MIGRATION_GUIDE.md#pre-migration-checklist)

## Contributing

To report bugs or request features, open an issue on the repository. To contribute code:

1. Fork the repository
2. Create a feature branch
3. Make your changes with clear commit messages
4. Submit a pull request

## License

This project is part of the Infragistics-BusinessTools/Reveal repository.

## Changelog

### v1.0.1 (March 2026)
- ✅ Added comprehensive rate-limit handling for overnight runs
- ✅ Improved retry logic for both GitHub (REST + GraphQL) and ADO APIs
- ✅ Extended documentation with rate-limit strategy and configuration guidance
- ✅ Tuned inter-item and per-comment sleep times for safe parallel execution

### v1.0.0 (Initial Release)
- Core migration functionality for ADO work items → GitHub issues
- Comment migration with author/timestamp
- ProjectV2 field mapping (iteration, priority, area, issue type)
- Resumable migration with state.json checkpointing
- Comprehensive error logging
