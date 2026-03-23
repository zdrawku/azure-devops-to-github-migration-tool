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