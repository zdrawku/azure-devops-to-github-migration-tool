"""
Create an "Area" custom field (Single Select) on every GitHub ProjectV2
in the Infragistics-BusinessTools organisation.

Usage:
    python create_area_fields.py          # all projects
    python create_area_fields.py 3 7 12   # only project numbers 3, 7, 12
"""

import sys
import time
import requests
from config import GH_TOKEN, GH_REPO_OWNER

GRAPHQL_URL = "https://api.github.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Content-Type": "application/json",
}

AREA_OPTIONS = [
    "BusinessTools",
    "BusinessTools\\Reveal",
    "BusinessTools\\Reveal\\Data Sources",
    "BusinessTools\\Reveal\\Data Sources\\MS SQL Server",
    "BusinessTools\\Reveal\\Data Sources\\REST Service",
    "BusinessTools\\Reveal\\Data Sources\\OneDrive",
    "BusinessTools\\Reveal\\Data Sources\\Amazon Athena",
    "BusinessTools\\Reveal\\Data Sources\\Amazon Redshift",
    "BusinessTools\\Reveal\\Data Sources\\Box",
    "BusinessTools\\Reveal\\Data Sources\\Dropbox",
    "BusinessTools\\Reveal\\Data Sources\\Google Analytics",
    "BusinessTools\\Reveal\\Data Sources\\Google BigQuery",
    "BusinessTools\\Reveal\\Data Sources\\Google Drive",
    "BusinessTools\\Reveal\\Data Sources\\Google Sheets",
    "BusinessTools\\Reveal\\Data Sources\\Hubspot",
    "BusinessTools\\Reveal\\Data Sources\\In-Memory Data",
    "BusinessTools\\Reveal\\Data Sources\\Marketo",
    "BusinessTools\\Reveal\\Data Sources\\MS Analysis Services",
    "BusinessTools\\Reveal\\Data Sources\\MS Azure Synapse Analytics",
    "BusinessTools\\Reveal\\Data Sources\\MS Azure SQL Server",
    "BusinessTools\\Reveal\\Data Sources\\MS Dynamics CRM",
    "BusinessTools\\Reveal\\Data Sources\\MS Reporting Services (SSRS)",
    "BusinessTools\\Reveal\\Data Sources\\MySQL",
    "BusinessTools\\Reveal\\Data Sources\\Oracle",
    "BusinessTools\\Reveal\\Data Sources\\OData",
    "BusinessTools\\Reveal\\Data Sources\\PostgreSQL",
    "BusinessTools\\Reveal\\Data Sources\\QuickBooks",
    "BusinessTools\\Reveal\\Data Sources\\Salesforce",
    "BusinessTools\\Reveal\\Data Sources\\SharePoint",
    "BusinessTools\\Reveal\\Data Sources\\Sybase",
    "BusinessTools\\Reveal\\Data Sources\\Databricks",
    "BusinessTools\\Reveal\\Data Sources\\Elasticsearch",
    "BusinessTools\\Reveal\\Data Sources\\MongoDB",
    "BusinessTools\\Reveal\\Controls",
    "BusinessTools\\Reveal\\Controls\\RevealView",
    "BusinessTools\\Reveal\\Controls\\DashboardThumbnailView",
    "BusinessTools\\Reveal\\Visualizations",
    "BusinessTools\\Reveal\\Visualizations\\Area",
    "BusinessTools\\Reveal\\Visualizations\\Bar",
    "BusinessTools\\Reveal\\Visualizations\\Bubble",
    "BusinessTools\\Reveal\\Visualizations\\Candlestick",
    "BusinessTools\\Reveal\\Visualizations\\Choropleth",
    "BusinessTools\\Reveal\\Visualizations\\Circular Gauge",
    "BusinessTools\\Reveal\\Visualizations\\Column",
    "BusinessTools\\Reveal\\Visualizations\\Combo",
    "BusinessTools\\Reveal\\Visualizations\\Custom",
    "BusinessTools\\Reveal\\Visualizations\\Doughnut",
    "BusinessTools\\Reveal\\Visualizations\\Funnel",
    "BusinessTools\\Reveal\\Visualizations\\Grid",
    "BusinessTools\\Reveal\\Visualizations\\Image",
    "BusinessTools\\Reveal\\Visualizations\\KPI Target",
    "BusinessTools\\Reveal\\Visualizations\\KPI Time",
    "BusinessTools\\Reveal\\Visualizations\\Linear Gauge",
    "BusinessTools\\Reveal\\Visualizations\\Line",
    "BusinessTools\\Reveal\\Visualizations\\OHLC",
    "BusinessTools\\Reveal\\Visualizations\\Pie",
    "BusinessTools\\Reveal\\Visualizations\\Pivot",
    "BusinessTools\\Reveal\\Visualizations\\Radial",
    "BusinessTools\\Reveal\\Visualizations\\Scatter Map",
    "BusinessTools\\Reveal\\Visualizations\\Scatter",
    "BusinessTools\\Reveal\\Visualizations\\Sparkline",
    "BusinessTools\\Reveal\\Visualizations\\Spline",
    "BusinessTools\\Reveal\\Visualizations\\Spline Area",
    "BusinessTools\\Reveal\\Visualizations\\Stacked Area",
    "BusinessTools\\Reveal\\Visualizations\\Stacked Bar",
    "BusinessTools\\Reveal\\Visualizations\\Stacked Column",
    "BusinessTools\\Reveal\\Visualizations\\Step Area",
    "BusinessTools\\Reveal\\Visualizations\\Step Line",
    "BusinessTools\\Reveal\\Visualizations\\Text Box",
    "BusinessTools\\Reveal\\Visualizations\\Text View",
    "BusinessTools\\Reveal\\Visualizations\\Text",
    "BusinessTools\\Reveal\\Visualizations\\Time Series",
    "BusinessTools\\Reveal\\Visualizations\\Tree Map",
    "BusinessTools\\Reveal\\Samples",
    "BusinessTools\\Reveal\\Documentation",
    "BusinessTools\\Reveal\\Export",
    "BusinessTools\\Slingshot",
    "BusinessTools\\Slingshot\\Connectors",
    "BusinessTools\\Slingshot\\Connectors\\QuickBooks",
    "BusinessTools\\SharePlus",
    "BusinessTools\\Website Team",
    "BusinessTools\\Slingshot Server Team",
    "BusinessTools\\Data Source Team",
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
