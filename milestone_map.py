"""
Fetches all GitHub milestones and builds a mapping from the milestone
title (last segment of the ADO iteration path) to the GitHub milestone number.

Usage:
    python milestone_map.py          # print the mapping
    python milestone_map.py --json   # output as JSON (for piping / import)

Programmatic usage from other scripts:
    from milestone_map import build_milestone_map
    ms_map = build_milestone_map()   # {"Apr 2026 - Release": 34, ...}
"""
import sys
import json
from github_client import list_milestones


def build_milestone_map() -> dict[str, int]:
    """
    Returns a dict mapping milestone title → GitHub milestone number.

    Example:
        {"Apr 2026 - Release": 34, "Release - Feb 2023": 1, ...}
    """
    milestones = list_milestones()
    return {m["title"]: m["number"] for m in milestones}


def resolve_milestone(iteration_path: str, ms_map: dict[str, int]) -> int | None:
    """
    Given an ADO iteration path like 'BusinessTools\\Reveal\\Apr 2026 - Release',
    extracts the last segment ('Apr 2026 - Release') and looks it up in ms_map.

    Returns the GitHub milestone number or None if no match.
    """
    if not iteration_path:
        return None
    last_segment = iteration_path.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return ms_map.get(last_segment)


def main():
    ms_map = build_milestone_map()

    if "--json" in sys.argv:
        print(json.dumps(ms_map, indent=2))
        return

    print(f"{'Milestone Title':<35} {'GH #':>5}")
    print("-" * 42)
    for title in sorted(ms_map, key=lambda t: ms_map[t]):
        print(f"{title:<35} {ms_map[title]:>5}")
    print(f"\nTotal: {len(ms_map)} milestone(s)")


if __name__ == "__main__":
    main()
