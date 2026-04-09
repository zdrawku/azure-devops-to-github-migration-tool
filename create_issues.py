"""
create_issues.py  —  Create GitHub Issues from a free-text Markdown description file.

Reads a structured Markdown file (default: info/work-items-to-be-created.md),
fetches and caches issue templates from .github/ISSUE_TEMPLATE in the configured
repository, creates GitHub issues by slotting each item's description into the
best-matching template, adds issues to the configured ProjectsV2, and wires
parent→child relationships between Features and their Tasks.

Usage
-----
    # Preview what would be created (dry-run, nothing submitted)
    python create_issues.py

    # Actually create the issues
    python create_issues.py --execute

    # Use a different input file
    python create_issues.py --execute --file path/to/items.md

    # Point at a different project number
    python create_issues.py --execute --project 3

    # Force re-fetch issue templates from GitHub (bypass local cache)
    python create_issues.py --refresh-templates

Resume support
--------------
Every successfully created issue is recorded in create_issues_state.json.
Re-running the command skips items that are already in that file, so the
script is safe to cancel and restart at any time.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

# ── Windows UTF-8 console fix ─────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from clients.github_client import add_issue_to_project, create_issue, set_issue_parent
from config import GH_BASE_URL, GH_TOKEN, WORK_ITEM_TYPE_LABELS

# ── Constants ──────────────────────────────────────────────────────────────────
DEFAULT_INPUT_FILE     = "info/work-items-to-be-created.md"
TEMPLATE_CACHE_FILE    = "template_cache.json"
STATE_FILE             = "create_issues_state.json"
DEFAULT_PROJECT_NUMBER = 5


# ── Data models ────────────────────────────────────────────────────────────────
@dataclass
class WorkItem:
    key: str                  # e.g. "Feature 1", "Task 1.1"
    item_type: str            # "Feature" or "Task"
    title: str
    description: str
    parent_key: str | None = None   # "Feature 1" for child tasks


@dataclass
class CreatedIssue:
    key: str
    number: int
    node_id: str


# ── GitHub API helpers ─────────────────────────────────────────────────────────
def _gh_headers() -> dict:
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ── Template fetching & caching ────────────────────────────────────────────────
def fetch_issue_templates(force_refresh: bool = False) -> dict[str, dict]:
    """
    Returns {filename: {"name": str, "labels": list[str], "body": str}}.

    On the first call (or when force_refresh=True) fetches templates from
    .github/ISSUE_TEMPLATE via the GitHub API and caches the result to
    TEMPLATE_CACHE_FILE.  Subsequent calls read from the cache.
    """
    cache_path = Path(TEMPLATE_CACHE_FILE)
    if cache_path.exists() and not force_refresh:
        with open(cache_path, encoding="utf-8") as f:
            cached: dict[str, dict] = json.load(f)
        print(f"Loaded {len(cached)} cached template(s) from {TEMPLATE_CACHE_FILE}")
        return cached

    print("Fetching issue templates from GitHub...")
    r = requests.get(
        f"{GH_BASE_URL}/contents/.github/ISSUE_TEMPLATE",
        headers=_gh_headers(),
    )
    r.raise_for_status()

    templates: dict[str, dict] = {}
    for entry in r.json():
        filename = entry.get("name", "")
        # Skip config.yml and non-template files
        if filename == "config.yml" or not filename.endswith((".md", ".yml", ".yaml")):
            continue
        content_r = requests.get(entry["download_url"], headers=_gh_headers())
        content_r.raise_for_status()
        parsed = _parse_template(filename, content_r.text)
        if parsed:
            templates[filename] = parsed
            print(f"  Fetched: {filename!r}  ({parsed['name']!r}, labels={parsed['labels']})")

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2, ensure_ascii=False)
    print(f"Cached {len(templates)} template(s) to {TEMPLATE_CACHE_FILE}")
    return templates


# ── Template parsing ───────────────────────────────────────────────────────────
def _parse_yaml(text: str) -> dict:
    """
    Parses a YAML string.  Uses PyYAML when available; falls back to a minimal
    regex-based parser that handles flat key:value pairs and simple list values.
    """
    try:
        import yaml  # type: ignore[import]
        result = yaml.safe_load(text)
        return result if isinstance(result, dict) else {}
    except Exception:
        pass

    # Minimal fallback: handle key: value and key:\n  - item lists
    result: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^(\w[\w-]*):\s*(.*)$", lines[i])
        if m:
            key, val = m.group(1), m.group(2).strip()
            if not val:
                # Possible list value on following lines
                items: list[str] = []
                i += 1
                while i < len(lines) and re.match(r"^\s+-\s+", lines[i]):
                    items.append(re.sub(r"^\s+-\s+", "", lines[i]).strip())
                    i += 1
                result[key] = items
                continue
            result[key] = val
        i += 1
    return result


def _extract_labels(raw) -> list[str]:
    """Normalises a labels value (string, list, or None) to a list of strings."""
    if isinstance(raw, list):
        return [str(l).strip().strip("'\"") for l in raw if str(l).strip()]
    if isinstance(raw, str):
        return [l.strip().strip("'\"") for l in raw.strip().strip("[]").split(",") if l.strip()]
    return []


def _parse_template(filename: str, raw: str) -> dict | None:
    """Dispatches to the appropriate parser based on file extension."""
    if filename.endswith(".md"):
        return _parse_md_template(filename, raw)
    return _parse_yml_form_template(filename, raw)


def _parse_md_template(filename: str, raw: str) -> dict | None:
    """Parses a classic Markdown issue template with optional YAML frontmatter."""
    name = filename
    labels: list[str] = []
    body = raw

    fm_match = re.match(r"^---\s*\n(.*?)\n?---\s*\n?", raw, re.DOTALL)
    if fm_match:
        fm_data = _parse_yaml(fm_match.group(1))
        body    = raw[fm_match.end():]
        name    = str(fm_data.get("name", filename)).strip()
        labels  = _extract_labels(fm_data.get("labels", []))

    return {"name": name, "labels": labels, "body": body.strip()}


def _parse_yml_form_template(filename: str, raw: str) -> dict | None:
    """
    Parses a GitHub Forms issue template (.yml).
    Reconstructs a Markdown body from the form field definitions so it can be
    used as a regular body template.
    """
    data = _parse_yaml(raw)
    if not data:
        return _parse_md_template(filename, raw)

    name   = str(data.get("name", filename)).strip()
    labels = _extract_labels(data.get("labels", []))

    # Reconstruct a markdown body from the form body fields
    parts: list[str] = []
    for field in data.get("body", []):
        if not isinstance(field, dict):
            continue
        ftype = field.get("type", "")
        attrs = field.get("attributes", {}) or {}
        if ftype == "markdown":
            val = (attrs.get("value") or "").strip()
            if val:
                parts.append(val)
        elif ftype in ("textarea", "input"):
            label = (attrs.get("label") or "").strip()
            desc  = (attrs.get("description") or "").strip()
            if label:
                section = f"## {label}"
                if desc:
                    section += f"\n\n{desc}"
                parts.append(section)

    return {"name": name, "labels": labels, "body": "\n\n".join(parts).strip()}


# ── Template selection ─────────────────────────────────────────────────────────
def select_template(
    item_type: str, templates: dict[str, dict]
) -> tuple[str, dict] | tuple[None, None]:
    """
    Returns (filename, template_dict) for the best-matching template.

    Matching priority:
    1. item_type substring match in the template filename
    2. item_type substring match in the template name
    3. First available template (fallback)
    """
    type_lower = item_type.lower()
    for fname, tmpl in templates.items():
        if type_lower in fname.lower() or type_lower in tmpl["name"].lower():
            return fname, tmpl
    if templates:
        first = next(iter(templates))
        return first, templates[first]
    return None, None


# ── Template body population ───────────────────────────────────────────────────
# Heading names considered as the primary description section (checked in order)
_DESCRIPTION_ALIASES = (
    "description", "summary", "overview", "details", "context", "about",
)


def populate_template(template_body: str, item: WorkItem) -> str:
    """
    Inserts item.description into the best-matching section of the template body.

    - HTML comment placeholders (<!-- … -->) are stripped before insertion.
    - Prefers a section whose heading matches one of the description aliases.
    - Falls back to the first ## heading, or prepends if no headings exist.
    """
    # Strip HTML comment placeholders and normalise blank lines
    clean = re.sub(r"<!--.*?-->", "", template_body, flags=re.DOTALL)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()

    headings = list(re.finditer(r"^(##\s+.+)$", clean, re.MULTILINE))
    if not headings:
        # No sections — prepend the description
        return f"{item.description}\n\n{clean}".strip() if clean else item.description

    # Pick the best section heading
    target_idx = 0
    for i, heading in enumerate(headings):
        label = heading.group(1).lstrip("#").strip().lower()
        if any(alias in label for alias in _DESCRIPTION_ALIASES):
            target_idx = i
            break

    target = headings[target_idx]
    # Where the section content ends (start of next heading, or end of body)
    section_end = (
        headings[target_idx + 1].start()
        if target_idx + 1 < len(headings)
        else len(clean)
    )

    before = clean[: target.end()].rstrip()
    after  = clean[section_end:].lstrip("\n")

    if after:
        return f"{before}\n\n{item.description}\n\n{after}"
    return f"{before}\n\n{item.description}"


# ── Markdown work-item parser ──────────────────────────────────────────────────
_FEATURE_RE   = re.compile(r"^###\s+\*\*Feature\s+(\d+):\s+(.+?)\*\*\s*$")
_TASK_RE      = re.compile(r"^\*\*Task\s+([\d.]+):\s+(.+?)\*\*\s*$")
_DESC_RE      = re.compile(r"^\*\s+\*\*Description:\*\*\s+(.+)$")
_RELATIONS_RE = re.compile(r"^\*\s+\*\*Relations:\*\*\s+(.+)$")

# Free-form format regexes  (# Heading / Title: / Type: / Description:)
_FF_SECTION_RE = re.compile(r"^#\s+(.+)$")       # Top-level `# Heading` (section boundary)
_FF_TITLE_RE   = re.compile(r"^Title:\s*(.+)$", re.IGNORECASE)
_FF_TYPE_RE    = re.compile(r"^Type:\s*(.+)$",  re.IGNORECASE)
_FF_DESC_RE    = re.compile(r"^Description:\s*(.*)$", re.IGNORECASE)


def _is_structured_format(md_text: str) -> bool:
    """Returns True when the text uses the old ### **Feature N:** / **Task N.M:** format."""
    return bool(
        _FEATURE_RE.search(md_text) or _TASK_RE.search(md_text)
    )


def _parse_freeform_items(md_text: str) -> list[WorkItem]:
    """
    Parses the free-form Markdown format:

        # Section heading          ← item boundary (text is ignored; Title: below is used)
        Title: The issue title
        Type: Task | Feature | Bug  ← optional, defaults to "Task"
        Description:
        Multi-line description text …

    Description content runs from the `Description:` line to the next `# heading`
    (or end of file).  All other lines before `Description:` are treated as metadata
    (Title / Type).
    """
    items: list[WorkItem] = []
    counter = 0

    # Split into sections on lines that start with a single `#` (top-level heading)
    raw_sections = re.split(r"(?m)^(?=#\s)", md_text.strip())

    for section in raw_sections:
        section = section.strip()
        if not section:
            continue

        lines = section.splitlines()
        title: str = ""
        item_type: str = "Task"
        description_lines: list[str] = []
        in_description = False

        for line in lines:
            # Skip the section heading line itself
            if _FF_SECTION_RE.match(line):
                continue

            if not in_description:
                m = _FF_TITLE_RE.match(line)
                if m:
                    title = m.group(1).strip()
                    continue
                m = _FF_TYPE_RE.match(line)
                if m:
                    item_type = m.group(1).strip().title()
                    continue
                m = _FF_DESC_RE.match(line)
                if m:
                    in_description = True
                    # Remainder of the Description: line (may be empty if value is on next line)
                    inline = m.group(1).strip()
                    if inline:
                        description_lines.append(inline)
                    continue
                # Any other line before Description: is silently ignored
            else:
                description_lines.append(line)

        if not title:
            continue  # Section with no Title: is skipped

        counter += 1
        description = "\n".join(description_lines).strip()
        items.append(WorkItem(
            key=f"Item {counter}",
            item_type=item_type,
            title=title,
            description=description,
            parent_key=None,
        ))

    return items


def parse_work_items(md_text: str) -> list[WorkItem]:
    """
    Auto-detects the input format and dispatches to the appropriate parser.

    **Structured format** (original):
        ### **Feature N: Title**
        **Task N.M: Title**
        * **Description:** …
        * **Relations:** …   (derives parent_key for tasks)

    **Free-form format** (new):
        # Any section heading
        Title: The issue title
        Type: Task | Feature | Bug     (optional, defaults to "Task")
        Description:
        Multi-line body text…

    Returns a list of WorkItem objects.
    """
    if _is_structured_format(md_text):
        return _parse_structured_items(md_text)
    return _parse_freeform_items(md_text)


def _parse_structured_items(md_text: str) -> list[WorkItem]:
    """Original structured parser (### **Feature N:** / **Task N.M:**)."""
    items:   list[WorkItem] = []
    pending: dict | None    = None

    def _flush(p: dict | None) -> None:
        if p is None:
            return
        relations  = p.get("relations", "")
        parent_key: str | None = None
        m = re.search(r"Child of\s+(Feature\s+\d+)", relations, re.IGNORECASE)
        if m:
            parent_key = m.group(1)
        items.append(WorkItem(
            key=p["key"],
            item_type=p["type"],
            title=p["title"],
            description=p.get("description", ""),
            parent_key=parent_key,
        ))

    for raw_line in md_text.splitlines():
        line = raw_line.rstrip()

        m = _FEATURE_RE.match(line)
        if m:
            _flush(pending)
            pending = {
                "key":   f"Feature {m.group(1)}",
                "type":  "Feature",
                "title": m.group(2).strip(),
            }
            continue

        m = _TASK_RE.match(line)
        if m:
            _flush(pending)
            pending = {
                "key":   f"Task {m.group(1)}",
                "type":  "Task",
                "title": m.group(2).strip(),
            }
            continue

        if pending is None:
            continue

        m = _DESC_RE.match(line)
        if m:
            pending["description"] = m.group(1).strip()
            continue

        m = _RELATIONS_RE.match(line)
        if m:
            pending["relations"] = m.group(1).strip()

    _flush(pending)
    return items


# ── State management ────────────────────────────────────────────────────────────
def _load_state() -> dict[str, dict]:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict[str, dict]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── Main orchestration ─────────────────────────────────────────────────────────
def run(input_file: str, execute: bool, project_number: int) -> None:
    # 1. Load templates ─────────────────────────────────────────────────────────
    templates = fetch_issue_templates()
    if not templates:
        print("ERROR: No issue templates found. Aborting.")
        sys.exit(1)
    print(f"\nLoaded templates: {list(templates.keys())}\n")

    # 2. Parse input file ────────────────────────────────────────────────────────
    md_path = Path(input_file)
    if not md_path.exists():
        print(f"ERROR: Input file not found: {input_file}")
        sys.exit(1)

    items = parse_work_items(md_path.read_text(encoding="utf-8"))
    if not items:
        print("ERROR: No work items found in the input file.")
        sys.exit(1)

    print(f"Parsed {len(items)} work item(s) from {input_file}:")
    for wi in items:
        hint = f" → child of [{wi.parent_key}]" if wi.parent_key else ""
        print(f"  [{wi.item_type:7s}] {wi.key}: {wi.title}{hint}")

    # 3. Load existing state (resume support) ────────────────────────────────────
    state  = _load_state()
    known: dict[str, CreatedIssue] = {
        k: CreatedIssue(key=k, number=v["number"], node_id=v["node_id"])
        for k, v in state.items()
    }

    # 4. Create issues (Features first so parents exist before children) ─────────
    ordered = sorted(
        items,
        key=lambda wi: (0 if wi.item_type == "Feature" else 1, wi.key),
    )
    created_count = 0
    skipped_count = 0

    for wi in ordered:
        if wi.key in known:
            print(f"\n[SKIP] {wi.key} — already created (issue #{known[wi.key].number})")
            skipped_count += 1
            continue

        fname, tmpl = select_template(wi.item_type, templates)
        if tmpl:
            body         = populate_template(tmpl["body"], wi)
            extra_labels = tmpl.get("labels", [])
        else:
            body         = wi.description
            extra_labels = []
            fname        = "(none)"

        type_label = WORK_ITEM_TYPE_LABELS.get(wi.item_type, wi.item_type.lower())
        labels     = sorted({l for l in ({type_label} | set(extra_labels)) if l})

        mode = "CREATE" if execute else "DRY-RUN"
        print(f"\n[{mode}] {wi.key}: {wi.title}")
        print(f"  Template : {fname}")
        print(f"  Labels   : {labels}")
        preview = body[:300] + ("..." if len(body) > 300 else "")
        print(f"  Body     :\n{'-' * 60}\n{preview}\n{'-' * 60}")

        if not execute:
            continue

        issue   = create_issue(
            title=wi.title,
            body=body,
            labels=labels,
            assignees=[],
            milestone=None,
            issue_type_name=wi.item_type,
        )
        number  = issue["number"]
        node_id = issue["node_id"]
        print(f"  Created  : #{number}  (node_id={node_id})")

        _proj_node_id, item_id = add_issue_to_project(project_number, node_id)
        if item_id:
            print(f"  Project  : added to #{project_number}")
        else:
            print(f"  [WARN]     could not add to project #{project_number}")

        known[wi.key] = CreatedIssue(key=wi.key, number=number, node_id=node_id)
        state[wi.key] = {"number": number, "node_id": node_id, "title": wi.title}
        _save_state(state)
        created_count += 1

    # 5. Wire parent→child issue links ───────────────────────────────────────────
    if execute:
        print("\n── Wiring parent→child issue links ──────────────────────────────────────────")
        linked_count = 0
        for wi in items:
            if not wi.parent_key:
                continue
            if wi.key not in known or wi.parent_key not in known:
                print(f"  [SKIP] Cannot link {wi.key} — parent or child not in state.")
                continue
            child  = known[wi.key]
            parent = known[wi.parent_key]
            try:
                set_issue_parent(child.node_id, parent.node_id)
                print(
                    f"  Linked  #{child.number} ({wi.key}) "
                    f"→ parent #{parent.number} ({wi.parent_key})"
                )
                linked_count += 1
            except Exception as exc:
                print(f"  [WARN] {wi.key} → {wi.parent_key}: {exc}")
        print(f"  Linked {linked_count} child issue(s).")

    # 6. Summary ─────────────────────────────────────────────────────────────────
    final_state = _load_state()
    total       = len(items)
    print(f"\n── Summary ──────────────────────────────────────────────────────────────────")
    print(f"  Items in file  : {total}")
    if execute:
        print(f"  Created        : {created_count}")
        print(f"  Skipped        : {skipped_count}")
        print(f"  State file     : {STATE_FILE}  ({len(final_state)} total tracked)")
    else:
        pending_count = sum(1 for wi in items if wi.key not in final_state)
        print(f"  Would create   : {pending_count}")
        print(f"  Already done   : {total - pending_count}")
        print(f"\n  Run with --execute to create these issues.")


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create GitHub Issues from a Markdown work-item description file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--file", "-f",
        default=DEFAULT_INPUT_FILE,
        metavar="FILE",
        help=f"Input Markdown file (default: {DEFAULT_INPUT_FILE})",
    )
    parser.add_argument(
        "--execute", "-x",
        action="store_true",
        help="Actually create issues. Without this flag the script runs as a dry-run.",
    )
    parser.add_argument(
        "--project", "-p",
        type=int,
        default=DEFAULT_PROJECT_NUMBER,
        metavar="N",
        help=f"GitHub ProjectsV2 number to add issues to (default: {DEFAULT_PROJECT_NUMBER})",
    )
    parser.add_argument(
        "--refresh-templates",
        action="store_true",
        help="Force re-fetch issue templates from GitHub (ignores the local cache).",
    )
    args = parser.parse_args()

    if args.refresh_templates:
        fetch_issue_templates(force_refresh=True)
        sys.exit(0)

    run(input_file=args.file, execute=args.execute, project_number=args.project)
