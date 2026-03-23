"""
Create an "Area" custom field (Single Select) on every GitHub ProjectV2
in the Infragistics-BusinessTools organisation.

Usage:
    python setup/create_area_fields.py          # all projects
    $ python setup/create_area_fields.py 1 5

Fetching projects for org 'Infragistics-BusinessTools' …
Found 5 project(s).

Filtered to 2 project(s): {1, 5}

▸ Project #5 – Reveal Project
    ✅ Created 'Area' field  (id: PVTSSF_lADODULKS84BSjhrzhAEonA)

▸ Project #1 – All Work Items Tracker
    ✅ Created 'Area' field  (id: PVTSSF_lADODULKS84BST8HzhAEonE)

Done.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import time
import requests
from config import GH_TOKEN, GH_REPO_OWNER

GRAPHQL_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Content-Type": "application/json",
}

AREA_OPTIONS = [
    "Reveal",
    "Reveal\\Samples",
    "Reveal\\Documentation",
    "Reveal\\Export",
    "Slingshot",
    "Slingshot\\Connectors",
    "Slingshot\\Connectors\\QuickBooks",
    "SharePlus",
    "Website Team",
    "Slingshot Server Team",
    "Data Source Team",
    "Reveal\\Data Sources",
    "Reveal\\Data Sources\\MS SQL Server",
    "Reveal\\Data Sources\\REST Service",
    "Reveal\\Data Sources\\OneDrive",
    "Reveal\\Data Sources\\Amazon Athena",
    "Reveal\\Data Sources\\Amazon Redshift",
    "Reveal\\Data Sources\\Box",
    "Reveal\\Data Sources\\Dropbox",
    "Reveal\\Data Sources\\Google Analytics",
    "Reveal\\Data Sources\\Google BigQuery",
    "Reveal\\Data Sources\\Google Drive",
    "Reveal\\Data Sources\\Google Sheets",
    "Reveal\\Data Sources\\Hubspot",
    "Reveal\\Data Sources\\In-Memory Data",
    "Reveal\\Data Sources\\Marketo",
    "Reveal\\Data Sources\\MS Analysis Services",
    "Reveal\\Data Sources\\MS Azure Synapse Analytics",
    "Reveal\\Data Sources\\MS Azure SQL Server",
    "Reveal\\Data Sources\\MS Dynamics CRM",
    "Reveal\\Data Sources\\MS Reporting Services (SSRS)",
    "Reveal\\Data Sources\\MySQL",
    "Reveal\\Data Sources\\Oracle",
    "Reveal\\Data Sources\\OData",
    "Reveal\\Data Sources\\PostgreSQL",
    "Reveal\\Data Sources\\QuickBooks",
    "Reveal\\Data Sources\\Salesforce",
    "Reveal\\Data Sources\\SharePoint",
    "Reveal\\Data Sources\\Sybase",
    "Reveal\\Data Sources\\Databricks",
    "Reveal\\Data Sources\\Elasticsearch",
    "Reveal\\Data Sources\\MongoDB",
    "Reveal\\Controls",
    "Reveal\\Controls\\RevealView",
    "Reveal\\Controls\\DashboardThumbnailView",
    "Reveal\\Visualizations",
    "Reveal\\Visualizations\\Area",
    "Reveal\\Visualizations\\Bar",
    "Reveal\\Visualizations\\Bubble",
    "Reveal\\Visualizations\\Candlestick",
    "Reveal\\Visualizations\\Choropleth",
    "Reveal\\Visualizations\\Circular Gauge",
    "Reveal\\Visualizations\\Column",
    "Reveal\\Visualizations\\Combo",
    "Reveal\\Visualizations\\Custom",
    "Reveal\\Visualizations\\Doughnut",
    "Reveal\\Visualizations\\Funnel",
    "Reveal\\Visualizations\\Grid",
    "Reveal\\Visualizations\\Image",
    "Reveal\\Visualizations\\KPI Target",
    "Reveal\\Visualizations\\KPI Time",
    "Reveal\\Visualizations\\Linear Gauge",
    "Reveal\\Visualizations\\Line",
    "Reveal\\Visualizations\\OHLC",
    "Reveal\\Visualizations\\Pie",
    "Reveal\\Visualizations\\Pivot",
    "Reveal\\Visualizations\\Radial",
    "Reveal\\Visualizations\\Scatter Map",
    "Reveal\\Visualizations\\Scatter",
    "Reveal\\Visualizations\\Sparkline",
    "Reveal\\Visualizations\\Spline",
    "Reveal\\Visualizations\\Spline Area",
    "Reveal\\Visualizations\\Stacked Area",
    "Reveal\\Visualizations\\Stacked Bar",
    "Reveal\\Visualizations\\Stacked Column",
    "Reveal\\Visualizations\\Step Area",
    "Reveal\\Visualizations\\Step Line",
    "Reveal\\Visualizations\\Text Box",
    "Reveal\\Visualizations\\Text View",
    "Reveal\\Visualizations\\Text",
    "Reveal\\Visualizations\\Time Series",
    "Reveal\\Visualizations\\Tree Map",
]


def _graphql(query: str, variables: dict | None = None) -> dict:
    """Execute a GraphQL request with basic rate-limit handling."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=30)

    # Handle rate limiting
    if resp.status_code == 403 or resp.status_code == 429:
        reset = int(resp.headers.get("X-RateLimit-Reset", 0))
        wait = max(reset - int(time.time()), 5)
        print(f"  ⏳ Rate-limited. Waiting {wait}s …")
        time.sleep(wait)
        resp = requests.post(GRAPHQL_URL, json=payload, headers=HEADERS, timeout=30)

    resp.raise_for_status()
    body = resp.json()
    if "errors" in body and "data" not in body:
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body


def list_projects(org: str) -> list[dict]:
    """Return all ProjectV2 entries for the organisation."""
    projects = []
    cursor = None

    while True:
        after = f', after: "{cursor}"' if cursor else ""
        query = f"""
        {{
          organization(login: "{org}") {{
            projectsV2(first: 100{after}) {{
              pageInfo {{ hasNextPage endCursor }}
              nodes {{
                id
                title
                number
              }}
            }}
          }}
        }}
        """
        data = _graphql(query)

        # Report permission warnings but continue with accessible projects
        if "errors" in data:
            forbidden = [e for e in data["errors"] if e.get("type") == "FORBIDDEN"]
            if forbidden:
                print(f"  ⚠  {len(forbidden)} project(s) not accessible with current token (need 'project' scope).")

        page = data["data"]["organization"]["projectsV2"]
        # Filter out null nodes (FORBIDDEN projects come back as None)
        projects.extend(n for n in page["nodes"] if n is not None)
        if page["pageInfo"]["hasNextPage"]:
            cursor = page["pageInfo"]["endCursor"]
        else:
            break

    return projects


def project_has_area_field(project_id: str) -> bool:
    """Check whether the project already has a field named 'Area'."""
    cursor = None
    while True:
        after = f', after: "{cursor}"' if cursor else ""
        query = f"""
        {{
          node(id: "{project_id}") {{
            ... on ProjectV2 {{
              fields(first: 100{after}) {{
                pageInfo {{ hasNextPage endCursor }}
                nodes {{
                  ... on ProjectV2SingleSelectField {{ name }}
                  ... on ProjectV2Field {{ name }}
                  ... on ProjectV2IterationField {{ name }}
                }}
              }}
            }}
          }}
        }}
        """
        data = _graphql(query)
        fields = data["data"]["node"]["fields"]
        for f in fields["nodes"]:
            if f.get("name") == "Area":
                return True
        if fields["pageInfo"]["hasNextPage"]:
            cursor = fields["pageInfo"]["endCursor"]
        else:
            return False


def create_area_field(project_id: str) -> str:
    """Create the 'Area' Single Select field on a project. Returns the field ID."""
    options = [{"name": opt, "color": "GRAY", "description": ""} for opt in AREA_OPTIONS]

    mutation = """
    mutation($input: CreateProjectV2FieldInput!) {
      createProjectV2Field(input: $input) {
        projectV2Field {
          ... on ProjectV2SingleSelectField {
            id
            name
          }
        }
      }
    }
    """
    variables = {
        "input": {
            "projectId": project_id,
            "dataType": "SINGLE_SELECT",
            "name": "Area",
            "singleSelectOptions": options,
        }
    }
    data = _graphql(mutation, variables)
    field = data["data"]["createProjectV2Field"]["projectV2Field"]
    return field["id"]


def main():
    filter_numbers = set()
    if len(sys.argv) > 1:
        filter_numbers = {int(n) for n in sys.argv[1:]}

    print(f"Fetching projects for org '{GH_REPO_OWNER}' …")
    projects = list_projects(GH_REPO_OWNER)
    print(f"Found {len(projects)} project(s).\n")

    if filter_numbers:
        projects = [p for p in projects if p["number"] in filter_numbers]
        print(f"Filtered to {len(projects)} project(s): {filter_numbers}\n")

    for proj in projects:
        title = proj["title"]
        number = proj["number"]
        pid = proj["id"]
        print(f"▸ Project #{number} – {title}")

        try:
            if project_has_area_field(pid):
                print("    ✔ 'Area' field already exists – skipping.\n")
                continue

            field_id = create_area_field(pid)
            print(f"    ✅ Created 'Area' field  (id: {field_id})\n")
        except RuntimeError as exc:
            print(f"    ❌ Failed: {exc}\n")

    print("Done.")


if __name__ == "__main__":
    main()
