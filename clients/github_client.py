import time
import requests
from config import GH_TOKEN, GH_BASE_URL, GH_REPO_OWNER, GH_REPO_NAME

GRAPHQL_URL = "https://api.github.com/graphql"


def _headers():
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _graphql(query: str, variables: dict | None = None) -> dict:
        payload = {"query": query}
        if variables:
                payload["variables"] = variables
        r = requests.post(
                GRAPHQL_URL,
                json=payload,
                headers={
                        "Authorization": f"Bearer {GH_TOKEN}",
                        "Content-Type": "application/json",
                },
        )
        r.raise_for_status()
        body = r.json()
        if "errors" in body and "data" not in body:
                raise RuntimeError(f"GraphQL errors: {body['errors']}")
        return body


def _get_issue_type_id_by_name(type_name: str) -> str | None:
        query = """
        query($owner: String!, $repo: String!) {
            repository(owner: $owner, name: $repo) {
                issueTypes(first: 50) {
                    nodes {
                        id
                        name
                    }
                }
            }
        }
        """
        data = _graphql(query, {"owner": GH_REPO_OWNER, "repo": GH_REPO_NAME})
        nodes = data.get("data", {}).get("repository", {}).get("issueTypes", {}).get("nodes", [])
        for n in nodes:
                if n.get("name", "").lower() == type_name.lower():
                        return n.get("id")
        return None


def _set_issue_type(issue_node_id: str, type_name: str):
        issue_type_id = _get_issue_type_id_by_name(type_name)
        if not issue_type_id:
                print(f"   [WARN] GitHub issue type '{type_name}' not found. Skipping native issue type set.")
                return

        mutation = """
        mutation($issueId: ID!, $issueTypeId: ID!) {
            updateIssue(input: {id: $issueId, issueTypeId: $issueTypeId}) {
                issue {
                    number
                    issueType {
                        name
                    }
                }
            }
        }
        """
        _graphql(mutation, {"issueId": issue_node_id, "issueTypeId": issue_type_id})


def _handle_rate_limit(response: requests.Response):
    """Pauses execution if GitHub rate limit is hit."""
    if response.status_code == 403 and "rate limit" in response.text.lower():
        reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
        wait = max(reset_time - int(time.time()), 10)
        print(f"⏳ Rate limit hit. Waiting {wait}s...")
        time.sleep(wait)
        return True
    return False


def create_label(name: str, color: str, description: str = "") -> dict:
    url = f"{GH_BASE_URL}/labels"
    payload = {"name": name, "color": color, "description": description}
    r = requests.post(url, json=payload, headers=_headers())
    if r.status_code == 422:  # Already exists
        return {"name": name, "already_existed": True}
    r.raise_for_status()
    return r.json()


def create_milestone(title: str, description: str = "", due_on: str = None) -> int:
    """Creates a milestone and returns its number."""
    url = f"{GH_BASE_URL}/milestones"
    payload = {"title": title, "description": description}
    if due_on:
        payload["due_on"] = due_on
    r = requests.post(url, json=payload, headers=_headers())
    if r.status_code == 422:
        # Already exists – look it up
        existing = list_milestones()
        for m in existing:
            if m["title"] == title:
                return m["number"]
    r.raise_for_status()
    return r.json()["number"]


def update_milestone(milestone_number: int, **fields) -> dict:
    """Updates a milestone. Accepts any PATCH-able fields (description, due_on, etc.)."""
    url = f"{GH_BASE_URL}/milestones/{milestone_number}"
    r = requests.patch(url, json=fields, headers=_headers())
    r.raise_for_status()
    return r.json()


def list_milestones() -> list[dict]:
    url = f"{GH_BASE_URL}/milestones?state=all&per_page=100"
    print(f"   [DEBUG] GET {url}")
    r = requests.get(url, headers=_headers())
    print(f"   [DEBUG] Response: {r.status_code} {r.reason}")
    if r.status_code != 200:
        print(f"   [DEBUG] Body: {r.text[:500]}")
    r.raise_for_status()
    return r.json()


def create_issue(
    title: str,
    body: str,
    labels: list[str],
    assignees: list[str],
    milestone: int | None = None,
    issue_type_name: str | None = None,
) -> dict:
    url = f"{GH_BASE_URL}/issues"
    payload = {
        "title": title,
        "body": body,
        "labels": labels,
        "assignees": assignees,
    }
    if milestone is not None:
        payload["milestone"] = milestone

    print(f"   [DEBUG] POST {url}")
    print(f"   [DEBUG] Title: {title[:80]}")
    print(f"   [DEBUG] Labels: {labels}")
    print(f"   [DEBUG] Body length: {len(body)} chars")

    while True:
        r = requests.post(url, json=payload, headers=_headers())
        print(f"   [DEBUG] Response: {r.status_code} {r.reason}")
        if r.status_code != 201:
            print(f"   [DEBUG] Body: {r.text[:500]}")
        if _handle_rate_limit(r):
            continue
        r.raise_for_status()
        issue = r.json()
        if issue_type_name and issue.get("node_id"):
            try:
                _set_issue_type(issue["node_id"], issue_type_name)
                print(f"   [DEBUG] Native issue type set: {issue_type_name}")
            except Exception as ex:
                print(f"   [WARN] Failed to set native issue type '{issue_type_name}': {ex}")
        return issue


def close_issue(issue_number: int):
    url = f"{GH_BASE_URL}/issues/{issue_number}"
    r = requests.patch(url, json={"state": "closed"}, headers=_headers())
    r.raise_for_status()


def list_labels() -> list[str]:
    """Returns the names of all labels that currently exist in the repo."""
    names = []
    page  = 1
    while True:
        r = requests.get(
            f"{GH_BASE_URL}/labels",
            params={"per_page": 100, "page": page},
            headers=_headers(),
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        names.extend(label["name"] for label in batch)
        if len(batch) < 100:
            break
        page += 1
    return names


def add_comment(issue_number: int, body: str):
    url = f"{GH_BASE_URL}/issues/{issue_number}/comments"
    while True:
        r = requests.post(url, json={"body": body}, headers=_headers())
        if _handle_rate_limit(r):
            continue
        r.raise_for_status()
        return r.json()


# ── ProjectV2 support ─────────────────────────────────────────────────────────

_project_node_cache: dict[int, str] = {}           # project_number → node_id
_iteration_field_cache: dict[str, tuple] = {}       # project_node_id → (field_id, {title_lower: iter_id})
_single_select_field_cache: dict[str, dict] = {}    # "proj_id:field_name" → (field_id, {option_lower: opt_id})


def _get_project_node_id(project_number: int) -> str | None:
    """Returns the GraphQL node ID for an org-level ProjectV2 (cached)."""
    if project_number in _project_node_cache:
        return _project_node_cache[project_number]
    query = """
    query($org: String!, $num: Int!) {
      organization(login: $org) {
        projectV2(number: $num) {
          id
        }
      }
    }
    """
    data = _graphql(query, {"org": GH_REPO_OWNER, "num": project_number})
    node_id = (
        data.get("data", {})
            .get("organization", {})
            .get("projectV2", {})
            .get("id")
    )
    if node_id:
        _project_node_cache[project_number] = node_id
    return node_id


def _get_project_iteration_field(project_node_id: str) -> tuple[str | None, dict[str, str]]:
    """
    Returns (field_id, {iteration_title_lower: iteration_id}) for the
    project's first iteration field (cached).
    """
    if project_node_id in _iteration_field_cache:
        return _iteration_field_cache[project_node_id]
    query = """
    query($id: ID!) {
      node(id: $id) {
        ... on ProjectV2 {
          fields(first: 50) {
            nodes {
              ... on ProjectV2IterationField {
                id
                name
                configuration {
                  iterations {
                    id
                    title
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    data = _graphql(query, {"id": project_node_id})
    nodes = data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])
    field_id = None
    iterations_map: dict[str, str] = {}
    for f in nodes:
        if "configuration" in f:  # ProjectV2IterationField uniquely has this key
            field_id = f["id"]
            for it in f.get("configuration", {}).get("iterations", []):
                iterations_map[it["title"].lower()] = it["id"]
            break
    result: tuple[str | None, dict[str, str]] = (field_id, iterations_map)
    _iteration_field_cache[project_node_id] = result
    return result


def add_issue_to_project(project_number: int, issue_node_id: str) -> tuple[str, str] | tuple[None, None]:
    """
    Adds an issue (by its GraphQL node_id) to an org-level ProjectV2.
    Returns (project_node_id, item_id), or (None, None) on failure.
    """
    project_node_id = _get_project_node_id(project_number)
    if not project_node_id:
        print(f"   [WARN] Project #{project_number} not found or inaccessible.")
        return None, None

    mutation = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item {
          id
        }
      }
    }
    """
    data = _graphql(mutation, {"projectId": project_node_id, "contentId": issue_node_id})
    item_id = (
        data.get("data", {})
            .get("addProjectV2ItemById", {})
            .get("item", {})
            .get("id")
    )
    return project_node_id, item_id


def set_project_item_iteration(project_node_id: str, item_id: str, iteration_title: str):
    """
    Sets the iteration field on a ProjectV2 item.
    Matches iteration_title case-insensitively against the project's iteration names.
    """
    field_id, iterations_map = _get_project_iteration_field(project_node_id)
    if not field_id:
        print(f"   [WARN] No iteration field found on project {project_node_id}.")
        return
    iteration_id = iterations_map.get(iteration_title.lower())
    if not iteration_id:
        available = list(iterations_map.keys())
        print(f"   [WARN] Iteration '{iteration_title}' not found. Available: {available}")
        return

    mutation = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $iterationId: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $projectId,
        itemId: $itemId,
        fieldId: $fieldId,
        value: { iterationId: $iterationId }
      }) {
        projectV2Item { id }
      }
    }
    """
    _graphql(mutation, {
        "projectId": project_node_id,
        "itemId":    item_id,
        "fieldId":   field_id,
        "iterationId": iteration_id,
    })


def _get_project_single_select_field(
    project_node_id: str, field_name: str
) -> tuple[str | None, dict[str, str]]:
    """
    Returns (field_id, {option_name_lower: option_id}) for a named
    ProjectV2SingleSelectField (cached per project + field name).
    """
    cache_key = f"{project_node_id}:{field_name.lower()}"
    if cache_key in _single_select_field_cache:
        return _single_select_field_cache[cache_key]

    query = """
    query($id: ID!) {
      node(id: $id) {
        ... on ProjectV2 {
          fields(first: 50) {
            nodes {
              ... on ProjectV2SingleSelectField {
                id
                name
                options {
                  id
                  name
                }
              }
            }
          }
        }
      }
    }
    """
    data = _graphql(query, {"id": project_node_id})
    nodes = data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])
    field_id = None
    options_map: dict[str, str] = {}
    for f in nodes:
        if f.get("name", "").lower() == field_name.lower() and "options" in f:
            field_id = f["id"]
            for opt in f.get("options", []):
                options_map[opt["name"].lower()] = opt["id"]
            break
    result: tuple[str | None, dict[str, str]] = (field_id, options_map)
    _single_select_field_cache[cache_key] = result
    return result


def set_project_item_single_select(
    project_node_id: str, item_id: str, field_name: str, option_name: str
):
    """
    Sets a single-select field on a ProjectV2 item by option name
    (case-insensitive match).
    """
    field_id, options_map = _get_project_single_select_field(project_node_id, field_name)
    if not field_id:
        print(f"   [WARN] Single-select field '{field_name}' not found on project {project_node_id}.")
        return
    option_id = options_map.get(option_name.lower())
    if not option_id:
        available = list(options_map.keys())
        print(f"   [WARN] Option '{option_name}' not found in '{field_name}'. Available: {available}")
        return

    mutation = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $projectId,
        itemId: $itemId,
        fieldId: $fieldId,
        value: { singleSelectOptionId: $optionId }
      }) {
        projectV2Item { id }
      }
    }
    """
    _graphql(mutation, {
        "projectId": project_node_id,
        "itemId":    item_id,
        "fieldId":   field_id,
        "optionId":  option_id,
    })


def set_issue_parent(child_issue_node_id: str, parent_issue_node_id: str):
    """
    Sets a GitHub issue's parent using the addSubIssue mutation.
    The *parent* issue gets the sub-issue added; child is identified by node_id.
    """
    mutation = """
    mutation($parentId: ID!, $childId: ID!) {
      addSubIssue(input: {issueId: $parentId, subIssueId: $childId}) {
        issue {
          number
        }
        subIssue {
          number
        }
      }
    }
    """
    _graphql(mutation, {"parentId": parent_issue_node_id, "childId": child_issue_node_id})