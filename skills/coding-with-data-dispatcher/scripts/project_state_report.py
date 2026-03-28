#!/usr/bin/env python3
"""Read-only Data Dispatcher project investigation report.

Examples:
  python3 project_state_report.py --state all --limit 10
  python3 project_state_report.py --owner rlc --search 'state in ("active", "failed")'
  python3 project_state_report.py --project-id 12345 --list-failed
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import sys
from typing import Any


def fmt_ts(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return str(ts)


def summarize_handles(project: dict[str, Any]) -> tuple[Counter, dict[str, list[str]]]:
    counts: Counter = Counter()
    by_state: dict[str, list[str]] = defaultdict(list)

    for h in project.get("file_handles", []) or []:
        state = h.get("state", "unknown")
        did = f"{h.get('namespace')}:{h.get('name')}"
        counts[state] += 1
        by_state[state].append(did)

    return counts, dict(by_state)


def _parse_date(s: str) -> float:
    """Parse an ISO-like date string to a UTC timestamp."""
    import time as _time
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return _time.mktime(_time.strptime(s, fmt))
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s!r}  (use YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)")


def _date_filter(projects: list, args: argparse.Namespace) -> list:
    """Client-side filter by created_timestamp."""
    after = _parse_date(args.created_after) if args.created_after else None
    before = _parse_date(args.created_before) if args.created_before else None
    if after is None and before is None:
        return projects
    out = []
    for p in projects:
        ts = p.get("created_timestamp")
        if ts is None:
            continue
        ts = float(ts)
        if after is not None and ts < after:
            continue
        if before is not None and ts >= before:
            continue
        out.append(p)
    return out


def discover_projects(client: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.project_id is not None:
        p = client.get_project(
            project_id=args.project_id,
            with_files=False,
            with_replicas=False,
        )
        return [] if p is None else [p]

    if args.search:
        # search_projects query expressions only support user-defined metadata
        # attributes; built-in attrs (owner, state, created_timestamp) must be
        # passed as API parameters or filtered client-side.
        projects = client.search_projects(
            search_query=args.search,
            owner=args.owner,
            state=args.state,
            with_files=False,
            with_replicas=False,
        )
        return _date_filter(projects, args)

    attrs = None
    if args.attributes_json:
        attrs = json.loads(args.attributes_json)

    # list_projects does not accept state="all"; omit state/not_state to get
    # all projects, or pass a concrete state name to filter.
    state_arg = args.state if args.state != "all" else None

    projects = client.list_projects(
        owner=args.owner,
        state=state_arg,
        not_state=None,
        attributes=attrs,
        with_files=False,
        with_replicas=False,
    )
    return _date_filter(projects, args)


def print_project_report(client: Any, project_stub: dict[str, Any], args: argparse.Namespace) -> None:
    pid = project_stub.get("project_id")
    full = client.get_project(pid, with_files=True, with_replicas=False)
    if full is None:
        print(f"project_id={pid}: not found")
        return

    counts, by_state = summarize_handles(full)
    total = sum(counts.values())
    done = counts.get("done", 0)
    percent = (100.0 * done / total) if total else 0.0

    print("-" * 80)
    print(f"project_id: {pid}")
    print(f"owner:      {full.get('owner')}")
    print(f"state:      {full.get('state')}")
    print(f"created:    {fmt_ts(full.get('created_timestamp'))}")
    print(f"ended:      {fmt_ts(full.get('ended_timestamp'))}")
    print(f"attributes: {full.get('attributes', {})}")
    print(f"query:      {full.get('query')}")
    print(f"total files: {total}")
    for state_name in ("initial", "reserved", "done", "failed", "unknown"):
        if counts.get(state_name, 0):
            print(f"  {state_name:8s}: {counts[state_name]}")
    print(f"completion: {percent:.1f}%")

    if args.list_failed:
        print("failed DIDs:")
        for did in by_state.get("failed", []):
            print(f"  {did}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Data Dispatcher project investigation report (read-only)."
    )
    p.add_argument("--project-id", type=int, help="Inspect one specific project id")
    p.add_argument("--owner", help="Project owner filter")
    p.add_argument(
        "--state",
        default="all",
        help="Project state filter for list/search: active|abandoned|cancelled|done|failed|all",
    )
    p.add_argument(
        "--search",
        help="Data Dispatcher project search query expression",
    )
    p.add_argument(
        "--attributes-json",
        help="JSON object for list_projects attributes filter, e.g. '{\"campaign\":\"crv\"}'",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max number of discovered projects to report",
    )
    p.add_argument(
        "--created-after",
        help="Include only projects created on or after this date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
    )
    p.add_argument(
        "--created-before",
        help="Include only projects created before this date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)",
    )
    p.add_argument(
        "--list-failed",
        action="store_true",
        help="Print failed file DIDs per project",
    )
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        from data_dispatcher.api import DataDispatcherClient
    except Exception as e:
        print("Error: could not import data_dispatcher.api", file=sys.stderr)
        print("Run: mu2einit && muse setup ops (or pip install --user datadispatcher)", file=sys.stderr)
        print(f"Import error: {e}", file=sys.stderr)
        return 2

    try:
        client = DataDispatcherClient()
        projects = discover_projects(client, args)
    except Exception as e:
        print("Error: failed to query Data Dispatcher", file=sys.stderr)
        print("Check DATA_DISPATCHER_URL / auth setup, then retry.", file=sys.stderr)
        print(f"Details: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    if not projects:
        print("No projects found.")
        return 0

    selected = projects[: args.limit]
    print(f"Discovered {len(projects)} projects; reporting first {len(selected)}")

    for p in selected:
        print_project_report(client, p, args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
