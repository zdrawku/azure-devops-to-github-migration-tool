import time
import requests
from config import GH_TOKEN, GH_BASE_URL, GH_REPO_OWNER, GH_REPO_NAME


def _headers():
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


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


def list_milestones() -> list[dict]:
    url = f"{GH_BASE_URL}/milestones?state=all&per_page=100"
    r = requests.get(url, headers=_headers())
    r.raise_for_status()
    return r.json()


def create_issue(
    title: str,
    body: str,
    labels: list[str],
    milestone: int | None,
    assignees: list[str],
) -> dict:
    url = f"{GH_BASE_URL}/issues"
    payload = {
        "title": title,
        "body": body,
        "labels": labels,
        "assignees": assignees,
    }
    if milestone:
        payload["milestone"] = milestone

    while True:
        r = requests.post(url, json=payload, headers=_headers())
        if _handle_rate_limit(r):
            continue
        r.raise_for_status()
        return r.json()


def close_issue(issue_number: int):
    url = f"{GH_BASE_URL}/issues/{issue_number}"
    r = requests.patch(url, json={"state": "closed"}, headers=_headers())
    r.raise_for_status()


def add_comment(issue_number: int, body: str):
    url = f"{GH_BASE_URL}/issues/{issue_number}/comments"
    while True:
        r = requests.post(url, json={"body": body}, headers=_headers())
        if _handle_rate_limit(r):
            continue
        r.raise_for_status()
        return r.json()