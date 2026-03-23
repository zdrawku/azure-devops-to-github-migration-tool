"""
Creates GitHub milestones from the ADO iteration list.

Usage:
    python setup/create_milestones.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
from clients.github_client import create_milestone, update_milestone, list_milestones

MILESTONES = [
    {"name": "Release - Feb 2023",   "start_date": "2023-01-02", "finish_date": "2023-02-28"},
    {"name": "Release - Dec 2022",   "start_date": "2022-11-16", "finish_date": "2022-12-30"},
    {"name": "Release - Nov 2022",   "start_date": "2022-10-03", "finish_date": "2022-11-16"},
    {"name": "Release - Apr 2023",   "start_date": "2023-03-01", "finish_date": "2023-04-27"},
    {"name": "Release - Jun 2023",   "start_date": "2023-04-28", "finish_date": "2023-06-26"},
    {"name": "Release - Aug 2023",   "start_date": "2023-06-27", "finish_date": "2023-08-23"},
    {"name": "Release - Oct 2023",   "start_date": "2023-08-24", "finish_date": "2023-10-20"},
    {"name": "Release - Dec 2023",   "start_date": "2023-10-23", "finish_date": "2023-12-19"},
    {"name": "Release - Feb 2024",   "start_date": "2023-12-20", "finish_date": "2024-02-15"},
    {"name": "Release - Apr 2024",   "start_date": "2024-02-16", "finish_date": "2024-04-15"},
    {"name": "Release - Jun 2024",   "start_date": "2024-04-16", "finish_date": "2024-06-12"},
    {"name": "Aug 2024 - Release",   "start_date": "2024-08-01", "finish_date": "2024-08-31"},
    {"name": "Oct 2024 - Release",   "start_date": "2024-10-01", "finish_date": "2024-10-31"},
    {"name": "Dec 2024 - Release",   "start_date": "2024-12-01", "finish_date": "2024-12-31"},
    {"name": "July 2024",            "start_date": "2024-07-01", "finish_date": "2024-07-31"},
    {"name": "Sept 2024",            "start_date": "2024-09-01", "finish_date": "2024-09-30"},
    {"name": "Nov 2024",             "start_date": "2024-11-01", "finish_date": "2024-11-30"},
    {"name": "Jan 2025",             "start_date": "2025-01-01", "finish_date": "2025-01-31"},
    {"name": "Feb 2025 - Release",   "start_date": "2025-02-01", "finish_date": "2025-02-28"},
    {"name": "March 2025",           "start_date": "2025-03-01", "finish_date": "2025-03-31"},
    {"name": "April 2025 - Release", "start_date": "2025-04-01", "finish_date": "2025-04-30"},
    {"name": "May 2025",             "start_date": "2025-05-01", "finish_date": "2025-05-31"},
    {"name": "June 2025 - Release",  "start_date": "2025-06-01", "finish_date": "2025-06-30"},
    {"name": "July 2025",            "start_date": "2025-07-01", "finish_date": "2025-07-31"},
    {"name": "Aug 2025 - Release",   "start_date": "2025-08-01", "finish_date": "2025-08-31"},
    {"name": "Sept 2025",            "start_date": "2025-09-01", "finish_date": "2025-09-30"},
    {"name": "Oct 2025 - Release",   "start_date": "2025-10-01", "finish_date": "2025-10-31"},
    {"name": "Nov 2025",             "start_date": "2025-11-01", "finish_date": "2025-11-30"},
    {"name": "Dec 2025 - Release",   "start_date": "2025-12-01", "finish_date": "2025-12-31"},
    {"name": "Jan 2026",             "start_date": "2026-01-01", "finish_date": "2026-01-31"},
    {"name": "Feb 2026 - Release",   "start_date": "2026-02-01", "finish_date": "2026-02-28"},
    {"name": "Mar 2026",             "start_date": "2026-03-01", "finish_date": "2026-03-31"},
    {"name": "Apr 2026 - Release",   "start_date": "2026-04-01", "finish_date": "2026-04-30"},
    {"name": "May 2026",             "start_date": "2026-05-01", "finish_date": "2026-05-31"},
    {"name": "Jun 2026 - Release",   "start_date": "2026-06-01", "finish_date": "2026-06-30"},
]


# Build a lookup: milestone name → start_date from our list
_START_DATES = {ms["name"]: ms["start_date"] for ms in MILESTONES}


def main():
    print("🗓️  Fetching existing GitHub milestones...")
    existing_milestones = list_milestones()
    existing_by_title = {m["title"]: m for m in existing_milestones}
    print(f"   {len(existing_by_title)} milestone(s) already in the repo.\n")

    created = 0
    updated = 0

    for ms in MILESTONES:
        title = ms["name"]
        description = f"Start Date: {ms['start_date']}"
        due_on = f"{ms['finish_date']}T00:00:00Z"

        if title in existing_by_title:
            gh_ms = existing_by_title[title]
            update_milestone(gh_ms["number"], description=description)
            print(f"   [updated] {title} → #{gh_ms['number']}")
            updated += 1
        else:
            ms_num = create_milestone(title=title, description=description, due_on=due_on)
            print(f"   [created] {title} → #{ms_num}")
            created += 1

    print(f"\n✅ Done — {created} created, {updated} updated.")


if __name__ == "__main__":
    main()
