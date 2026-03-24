import base64
import os
import sys
import time
import requests

# Allow running this file directly: `python clients/ado_client.py <command>`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ADO_BASE_URL, ADO_PAT, ADO_API_VER, BATCH_SIZE


def _headers():
    token = base64.b64encode(f":{ADO_PAT}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }


def _ado_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    Thin wrapper around requests that retries on ADO rate-limit (429) and
    transient server errors (5xx) with exponential backoff.
    """
    for attempt in range(5):
        response = requests.request(method, url, **kwargs)
        if response.status_code == 429:
            wait = int(response.headers.get("Retry-After", 60))
            print(f"⏳ ADO rate limit (429). Waiting {wait}s...")
            time.sleep(wait)
            continue
        if response.status_code >= 500 and attempt < 4:
            wait = 5 * (2 ** attempt)  # 5, 10, 20, 40 s
            print(f"⏳ ADO server error {response.status_code}. Retrying in {wait}s...")
            time.sleep(wait)
            continue
        return response
    return response  # caller handles raise_for_status


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
            "ORDER BY [System.Id] ASC"
        )
    }
    response = _ado_request("POST", url, json=query, headers=_headers())
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
    response = _ado_request("POST", url, json=payload, headers=_headers())
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
    response = _ado_request("GET", url, headers=_headers())
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


def get_all_areas(depth: int = 10) -> list[str]:
    """
    Fetches all area paths as a flat list of backslash-separated strings.

    Example output::

        ["BusinessTools", "BusinessTools\\Reveal", "BusinessTools\\Reveal\\Data Sources", ...]
    """
    url = (
        f"{ADO_BASE_URL}/wit/classificationnodes/Areas"
        f"?$depth={depth}&api-version={ADO_API_VER}"
    )
    response = requests.get(url, headers=_headers())
    response.raise_for_status()

    paths: list[str] = []

    def _walk(node: dict, prefix: str = "") -> None:
        name = node.get("name", "")
        path = f"{prefix}\\{name}" if prefix else name
        paths.append(path)
        for child in node.get("children", []):
            _walk(child, path)

    _walk(response.json())
    return paths


def get_all_iterations(depth: int = 10) -> list[dict]:
    """
    Fetches all iterations as a flat list of dicts with name, start_date,
    and finish_date.

    Example output::

        [{"name": "Release - Nov 2022", "start_date": "10/3/2022", "finish_date": "11/16/2022"}, ...]
    """
    url = (
        f"{ADO_BASE_URL}/wit/classificationnodes/Iterations"
        f"?$depth={depth}&api-version={ADO_API_VER}"
    )
    response = requests.get(url, headers=_headers())
    response.raise_for_status()

    iterations: list[dict] = []

    def _walk(node: dict) -> None:
        attrs = node.get("attributes", {})
        start = attrs.get("startDate", "")
        finish = attrs.get("finishDate", "")
        # Only include leaf iterations that have dates
        if start or finish:
            iterations.append({
                "name": node.get("name", ""),
                "start_date": start[:10] if start else "",
                "finish_date": finish[:10] if finish else "",
            })
        for child in node.get("children", []):
            _walk(child)

    _walk(response.json())
    return iterations


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


def get_parent_ado_id(work_item: dict) -> int | None:
    """
    Returns the ADO ID of the parent work item, or None if there is no parent.
    The parent link in ADO relations uses rel type 'System.LinkTypes.Hierarchy-Reverse'.
    The URL in the relation looks like:
        https://dev.azure.com/{org}/{project}/_apis/wit/workItems/{id}
    """
    for rel in (work_item.get("relations") or []):
        if rel.get("rel") == "System.LinkTypes.Hierarchy-Reverse":
            url = rel.get("url", "")
            # Last path segment is the work item ID
            try:
                return int(url.rstrip("/").split("/")[-1])
            except (ValueError, IndexError):
                pass
    return None


def fetch_all_work_items(skip_ids: set[int] | None = None) -> list[dict]:
    """
    Main entry point: fetches all work items in paginated batches.

    ``skip_ids`` — optional set of ADO IDs (ints) whose full details should
    NOT be fetched because they are already migrated.  The IDs are still
    discovered via WIQL so the pending count is accurate, but no batch API
    call is made for them.  This makes repeat / incremental runs fast.
    """
    print("🔍 Fetching all work item IDs from Azure DevOps...")
    all_ids = get_all_work_item_ids()
    print(f"   Found {len(all_ids)} work items total.")

    pending_ids = [i for i in all_ids if i not in (skip_ids or set())]
    skipped = len(all_ids) - len(pending_ids)
    if skipped:
        print(f"   Skipping {skipped} already-migrated item(s) — fetching details for {len(pending_ids)} new item(s).")

    all_items = []
    for i in range(0, len(pending_ids), BATCH_SIZE):
        batch_ids = pending_ids[i: i + BATCH_SIZE]
        print(f"   Fetching details for items {i + 1}–{i + len(batch_ids)}...")
        batch = get_work_items_batch(batch_ids)
        all_items.extend(batch)

    print(f"✅ Fetched {len(all_items)} work items from ADO.\n")
    return all_items


def count_work_items_by_type() -> tuple[int, dict[str, dict[str, int]]]:
    """
    Queries ADO for all work item IDs, then fetches only the Type and State
    fields to produce a breakdown without doing a full migration fetch.

    Returns (total_count, {WorkItemType: {State: count}}).
    """
    from collections import defaultdict

    print("🔍 Fetching work item IDs from Azure DevOps...")
    all_ids = get_all_work_item_ids()
    total   = len(all_ids)
    print(f"   Found {total} work items. Fetching type/state breakdown...\n")

    counts: dict = defaultdict(lambda: defaultdict(int))

    for i in range(0, total, BATCH_SIZE):
        batch_ids = all_ids[i: i + BATCH_SIZE]
        url = f"{ADO_BASE_URL}/wit/workitemsbatch?api-version={ADO_API_VER}"
        payload = {
            "ids": batch_ids,
            "fields": ["System.WorkItemType", "System.State"],
            "errorPolicy": "omit",
        }
        response = requests.post(url, json=payload, headers=_headers())
        response.raise_for_status()
        for item in response.json().get("value", []):
            fields  = item.get("fields", {})
            wi_type = fields.get("System.WorkItemType", "Unknown")
            state   = fields.get("System.State",        "Unknown")
            counts[wi_type][state] += 1

    return total, {k: dict(v) for k, v in counts.items()}


def discover_github_connections(sample_size: int = 500) -> dict[str, list[int]]:
    """
    Scans a sample of work items for ArtifactLink relations that contain
    vstfs:///GitHub/ URLs and extracts the embedded connection GUIDs.

    Returns a dict mapping each GUID (lowercase) to a list of ADO work item IDs
    that reference it — useful for populating ADO_GITHUB_CONNECTION_MAP in .env.

    Usage::

        python clients/ado_client.py discover_github_connections
    """
    import urllib.parse as _up
    from collections import defaultdict

    print(f"Scanning up to {sample_size} work items for GitHub connection GUIDs...")
    all_ids = get_all_work_item_ids()
    sample  = all_ids[:sample_size]

    guid_to_items: dict[str, list[int]] = defaultdict(list)

    for i in range(0, len(sample), BATCH_SIZE):
        batch_ids = sample[i: i + BATCH_SIZE]
        items = get_work_items_batch(batch_ids)
        for item in items:
            wi_id = item.get("id")
            for rel in (item.get("relations") or []):
                if rel.get("rel") != "ArtifactLink":
                    continue
                url = rel.get("url", "")
                if "vstfs:///GitHub/" not in url:
                    continue
                # vstfs:///GitHub/PullRequest/{guid}%2F{num}
                rest   = url[len("vstfs:///GitHub/"):]
                parts  = rest.split("/", 1)
                if len(parts) < 2:
                    continue
                encoded = parts[1]
                decoded = _up.unquote(encoded)
                guid    = decoded.split("/")[0].lower()
                guid_to_items[guid].append(wi_id)

    return dict(guid_to_items)


# ---------------------------------------------------------------------------
# Standalone CLI — run any public function directly for testing
#
#   python clients/ado_client.py get_all_work_item_ids
#   python clients/ado_client.py fetch_all_work_items
#   python clients/ado_client.py count_work_items_by_type
#   python clients/ado_client.py get_iterations
#   python clients/ado_client.py get_all_areas
#   python clients/ado_client.py get_all_iterations
#   python clients/ado_client.py get_work_item_comments      --id 12345
#   python clients/ado_client.py get_work_items_batch        --ids 1 2 3
#   python clients/ado_client.py discover_work_item_fields   --id 12345
#   python clients/ado_client.py discover_github_connections
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Run a single ado_client function and print its result as JSON."
    )
    parser.add_argument(
        "command",
        choices=[
            "get_all_work_item_ids",
            "fetch_all_work_items",
            "count_work_items_by_type",
            "get_iterations",
            "get_all_areas",
            "get_all_iterations",
            "get_work_item_comments",
            "get_work_items_batch",
            "discover_work_item_fields",
            "discover_github_connections",
        ],
        help="Which function to execute.",
    )
    parser.add_argument("--id",  type=int, help="Single work item ID (for commands that need one).")
    parser.add_argument("--ids", type=int, nargs="+", help="One or more work item IDs (for get_work_items_batch).")
    args = parser.parse_args()

    result = None

    if args.command == "get_all_work_item_ids":
        result = get_all_work_item_ids()
        print(f"Total IDs returned: {len(result)}")

    elif args.command == "fetch_all_work_items":
        result = fetch_all_work_items()
        print(f"Total items fetched: {len(result)}")

    elif args.command == "count_work_items_by_type":
        total, breakdown = count_work_items_by_type()
        print(f"\nTotal work items: {total}\n")
        for wi_type, states in sorted(breakdown.items()):
            print(f"  {wi_type}:")
            for state, count in sorted(states.items()):
                print(f"    {state}: {count}")
        sys.exit(0)

    elif args.command == "get_iterations":
        result = get_iterations()
        print(f"Total iterations: {len(result)}")

    elif args.command == "get_all_areas":
        result = get_all_areas()
        print(f"Total area paths: {len(result)}")

    elif args.command == "get_all_iterations":
        result = get_all_iterations()
        print(f"Total iterations (with dates): {len(result)}")

    elif args.command == "get_work_item_comments":
        if not args.id:
            parser.error("--id is required for get_work_item_comments")
        result = get_work_item_comments(args.id)
        print(f"Comments for work item {args.id}: {len(result)}")

    elif args.command == "get_work_items_batch":
        if not args.ids:
            parser.error("--ids is required for get_work_items_batch")
        result = get_work_items_batch(args.ids)
        print(f"Items fetched: {len(result)}")

    elif args.command == "discover_work_item_fields":
        if not args.id:
            parser.error("--id is required for discover_work_item_fields")
        result = discover_work_item_fields(args.id)
        print(f"Fields for work item {args.id}: {len(result)}")

    elif args.command == "discover_github_connections":
        guid_map = discover_github_connections()
        if not guid_map:
            print("No GitHub ArtifactLink connections found in the scanned sample.")
        else:
            print(f"\nFound {len(guid_map)} unique GitHub connection GUID(s):")
            for guid, wi_ids in sorted(guid_map.items()):
                print(f"  {guid}  (seen in {len(wi_ids)} work item(s): {wi_ids[:5]})")
            print()
            print("Add to your .env as (fill in the owner/repo values):")
            print("ADO_GITHUB_CONNECTION_MAP={" + ", ".join(f'"{g}": "owner/repo"' for g in sorted(guid_map)) + "}")
        sys.exit(0)

    if result is not None:
        print(json.dumps(result, indent=2, default=str))