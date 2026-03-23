import base64
import requests
from config import ADO_BASE_URL, ADO_PAT, ADO_API_VER, BATCH_SIZE


def _headers():
    token = base64.b64encode(f":{ADO_PAT}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def get_all_work_item_ids() -> list[int]:
    """
    Uses WIQL to retrieve ALL work item IDs from the ADO project,
    across every type, area path, and iteration.
    """
    url = f"{ADO_BASE_URL}/wit/wiql?api-version={ADO_API_VER}"
    query = {
        "query": (
            "SELECT [System.Id] FROM WorkItems "
            "WHERE [System.TeamProject] = @project "
            "ORDER BY [System.ChangedDate] DESC"
        )
    }
    response = requests.post(url, json=query, headers=_headers())
    response.raise_for_status()
    items = response.json().get("workItems", [])
    return [item["id"] for item in items]


def get_work_items_batch(ids: list[int]) -> list[dict]:
    """
    Fetches full work item details for a batch of IDs (max 200 per request).
    Includes all fields + relations (links between work items).
    """
    if not ids:
        return []

    url = (
        f"{ADO_BASE_URL}/wit/workitemsbatch?api-version={ADO_API_VER}"
    )
    payload = {
        "ids": ids,
        "errorPolicy": "omit",
        "$expand": "relations",
    }
    response = requests.post(url, json=payload, headers=_headers())
    if not response.ok:
        print(f"   [DEBUG] Batch API error {response.status_code}: {response.text[:500]}")
    response.raise_for_status()
    return response.json().get("value", [])


def get_work_item_comments(work_item_id: int) -> list[dict]:
    """Fetches all discussion comments for a given work item."""
    url = (
        f"{ADO_BASE_URL}/wit/workItems/{work_item_id}/comments"
        f"?api-version={ADO_API_VER}-preview.3"
    )
    response = requests.get(url, headers=_headers())
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json().get("comments", [])


def get_iterations() -> list[dict]:
    """Fetches all iterations (sprints) from the ADO project."""
    url = (
        f"{ADO_BASE_URL}/work/teamsettings/iterations"
        f"?api-version={ADO_API_VER}"
    )
    response = requests.get(url, headers=_headers())
    response.raise_for_status()
    return response.json().get("value", [])


def discover_work_item_fields(work_item_id: int) -> list[dict]:
    """
    Fetches a single work item with ALL fields expanded and returns a sorted
    list of {referenceName, value} dicts — useful for finding custom
    field reference names.
    """
    url = (
        f"{ADO_BASE_URL}/wit/workitems/{work_item_id}"
        f"?$expand=all&api-version={ADO_API_VER}"
    )
    response = requests.get(url, headers=_headers())
    response.raise_for_status()
    fields = response.json().get("fields", {})
    return sorted(
        [{"referenceName": k, "value": v} for k, v in fields.items()],
        key=lambda x: x["referenceName"],
    )


def fetch_all_work_items() -> list[dict]:
    """Main entry point: fetches all work items in paginated batches."""
    print("🔍 Fetching all work item IDs from Azure DevOps...")
    all_ids = get_all_work_item_ids()
    print(f"   Found {len(all_ids)} work items total.")

    all_items = []
    for i in range(0, len(all_ids), BATCH_SIZE):
        batch_ids = all_ids[i: i + BATCH_SIZE]
        print(f"   Fetching details for items {i + 1}–{i + len(batch_ids)}...")
        batch = get_work_items_batch(batch_ids)
        all_items.extend(batch)

    print(f"✅ Fetched {len(all_items)} work items from ADO.\n")
    return all_items