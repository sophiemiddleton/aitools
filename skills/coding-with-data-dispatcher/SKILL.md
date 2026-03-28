---
name: coding-with-data-dispatcher
description: Write and troubleshoot Python code using Data Dispatcher to discover projects, filter by owner/state/time/metadata, and summarize project file-handle states (available/reserved/done/failed) for monitoring and operations.
compatibility: Requires mu2einit, muse setup ops, Python 3.7+, network access to Data Dispatcher service, and optional auth token for non-public project operations
metadata:
  version: "1.0.0"
  last-updated: "2026-03-27"
---

# Coding with Data Dispatcher

## Overview

Use this skill when writing Python code to inspect Data Dispatcher project state.

Naming note:

- The Data Dispatcher CLI command is commonly `ddisp`

Primary use cases:

- Find projects by owner, state, creation time, and metadata
- Search projects with query expressions (including regex and time windows)
- Fetch project file-handle lists
- Report counts and file lists by handle state (`initial`, `reserved`, `done`, `failed`)
- Build operational monitoring scripts for project health and progress

Data handling relationship:

- `metacat` catalogs files and metadata
- Data Dispatcher organizes file processing work as a `project`
- Workers reserve files from the project and report completion/failure back to Data Dispatcher

For Mu2e data architecture background, pair with `understanding-data-handling`.

---

## Safety Policy (Read-Only by Default)

For investigation workflows, use read-only APIs unless the user explicitly asks to mutate project state.

Read-only methods (default):

- `list_projects(...)`
- `search_projects(...)`
- `get_project(...)`
- `get_handle(...)`
- `reserved_handles(...)`
- `version()`

State-changing methods (use only with explicit user intent):

- `create_project(...)`, `copy_project(...)`
- `cancel_project(...)`, `activate_project(...)`, `delete_project(...)`
- `restart_handles(...)`
- `next_file(...)`, `file_done(...)`, `file_failed(...)`

---

## Setup

Initialize Mu2e environment first (so Data Dispatcher tools/modules are on path):

```bash
mu2einit
muse setup ops
```

**Authentication:**

See [understanding-data-handling](../understanding-data-handling/SKILL.md) for the
full Kerberos → OAuth → service-login flow.

Short form for interactive use:
```bash
getToken                       # Refresh OAuth token (~2h)
ddisp login -m token $USER    # Authenticate ddisp session
```

Service URLs are set automatically by `mu2einit` via environment variables:

```bash
# These are set for you after mu2einit:
# DATA_DISPATCHER_URL
# DATA_DISPATCHER_AUTH_URL
```

Create client:

```python
from data_dispatcher.api import DataDispatcherClient

# Preferred: server URL from DATA_DISPATCHER_URL env var
client = DataDispatcherClient()

# Optional explicit endpoint
# client = DataDispatcherClient("https://server.host.domain:8080/dd/data")
```

Quick connectivity check:

```python
print("DD server version:", client.version())
```

CLI alias note:

```bash
ddisp --help
```

`ddisp` is the common short command name for Data Dispatcher CLI operations.

---

## Project Model

Project attributes (top-level fields) include:

- `project_id`
- `owner`
- `state` (`active`, `abandoned`, `cancelled`, `done`, `failed`)
- `attributes` (arbitrary project metadata dictionary)
- `created_timestamp`
- `ended_timestamp`
- `active`
- `query`
- `worker_timeout`
- `idle_timeout`

When `with_files=True`, project dictionaries include `file_handles`.

Each file handle typically includes fields such as:

- `namespace`
- `name`
- `state` (commonly `initial`, `reserved`, `done`, `failed`)
- `worker_id` (for reserved handles)
- optional replica/location details when `with_replicas=True`

---

## Standard Investigation Workflow

1. Start with fast project discovery (`with_files=False`)
2. Filter by owner/state/metadata/time
3. Fetch full project details only for selected project IDs (`with_files=True`)
4. Summarize handle counts by state
5. Optionally list file DIDs per state for deeper troubleshooting

---

## Core API Patterns

### 1) List projects with structured filters

```python
projects = client.list_projects(
    owner="jdoe",                 # optional
    state="all",                  # active|abandoned|cancelled|done|failed|all
    not_state=None,                # optional exclusion
    attributes={"campaign": "crv"},
    with_files=False,
    with_replicas=False,
)
```

Notes:

- Default call returns `state="active"` and excludes abandoned.
- `list_projects()` does **not** support `state="all"` — omit the `state` argument (or pass `None`) to get all states.
- `search_projects()` does support `state="all"` (it omits the filter server-side).
- Keep `with_files=False` for scalability during discovery.

### 2) Search projects using query expressions

```python
query = (
    'owner = "jdoe" and '
    'state in ("active", "failed") and '
    'created_timestamp >= "2026-03-01 00:00:00" and '
    'created_timestamp <  "2026-04-01 00:00:00" and '
    'pipeline ~ "crv.*reco"'
)

projects = client.search_projects(
    search_query=query,
    state="all",
    with_files=False,
    with_replicas=False,
)
```

Supported query operators include:

- comparisons: `<`, `<=`, `=`, `!=`, `>=`, `>`
- regex match: `field ~ "regex"`
- membership: `field in (...)`
- range: `field in low:high`
- presence: `field present`, `field not present`
- boolean composition: `and`, `or`, `! (...)`

> ⚠️ **Important limitation**: The `search_projects` query expression only
> supports **user-defined metadata attribute names** (keys inside `attributes` dict),
> NOT built-in project fields like `owner`, `state`, or `created_timestamp`.
> Filter on built-in fields via API parameters (`owner=`, `state=`) or
> apply date-range filtering client-side after `list_projects`.

Timestamp literal format (for user-defined metadata fields):

- `"YYYY-MM-DD[ HH:MM:SS[+/-HH:MM]]"`

### 3) Get one project with handles

```python
project = client.get_project(project_id=12345, with_files=True, with_replicas=False)
if project is None:
    raise RuntimeError("Project not found")
```

---

## Status Reporting Patterns

### Count handles by state

```python
from collections import Counter


def handle_state_counts(project: dict) -> Counter:
    handles = project.get("file_handles", [])
    return Counter(h.get("state", "unknown") for h in handles)
```

### Build DID lists by state

```python
from collections import defaultdict


def handles_grouped_by_state(project: dict) -> dict:
    groups = defaultdict(list)
    for h in project.get("file_handles", []):
        state = h.get("state", "unknown")
        did = f"{h.get('namespace')}:{h.get('name')}"
        groups[state].append(did)
    return dict(groups)
```

### Project summary record

```python
from datetime import datetime, timezone


def fmt_ts(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def summarize_project(project: dict) -> dict:
    counts = handle_state_counts(project)
    total = sum(counts.values())
    done = counts.get("done", 0)
    failed = counts.get("failed", 0)
    reserved = counts.get("reserved", 0)
    available = counts.get("initial", 0)

    return {
        "project_id": project.get("project_id"),
        "owner": project.get("owner"),
        "state": project.get("state"),
        "created": fmt_ts(project.get("created_timestamp")),
        "ended": fmt_ts(project.get("ended_timestamp")),
        "total_handles": total,
        "done": done,
        "failed": failed,
        "reserved": reserved,
        "available": available,
        "completion_fraction": (done / total) if total else 0.0,
        "attributes": project.get("attributes", {}),
    }
```

---

## End-to-End Investigation Script (Read-Only)

```python
#!/usr/bin/env python3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from data_dispatcher.api import DataDispatcherClient


def fmt_ts(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def summarize_handles(project):
    counts = Counter(h.get("state", "unknown") for h in project.get("file_handles", []))
    by_state = defaultdict(list)
    for h in project.get("file_handles", []):
        did = f"{h.get('namespace')}:{h.get('name')}"
        by_state[h.get("state", "unknown")].append(did)
    return counts, dict(by_state)


def find_projects(client, owner=None, state="all", search_query=None):
    if search_query:
        return client.search_projects(
            search_query=search_query,
            owner=owner,
            state=state,
            with_files=False,
            with_replicas=False,
        )
    return client.list_projects(
        owner=owner,
        state=state,
        not_state=None,
        with_files=False,
        with_replicas=False,
    )


def investigate_projects(owner=None, state="all", search_query=None):
    client = DataDispatcherClient()

    projects = find_projects(client, owner=owner, state=state, search_query=search_query)
    print(f"Discovered {len(projects)} projects")

    for p in projects:
        pid = p["project_id"]
        full = client.get_project(pid, with_files=True, with_replicas=False)
        if full is None:
            print(f"project_id={pid}: not found")
            continue

        counts, by_state = summarize_handles(full)
        total = sum(counts.values())

        print("-" * 80)
        print(f"project_id: {pid}")
        print(f"owner:      {full.get('owner')}")
        print(f"state:      {full.get('state')}")
        print(f"created:    {fmt_ts(full.get('created_timestamp'))}")
        print(f"ended:      {fmt_ts(full.get('ended_timestamp'))}")
        print(f"attributes: {full.get('attributes', {})}")
        print(f"query:      {full.get('query')}")
        print(f"total files: {total}")
        for s in ("initial", "reserved", "done", "failed", "unknown"):
            if counts.get(s, 0):
                print(f"  {s:8s}: {counts[s]}")

        # Optional: print actual file DIDs by status
        # for state_name, dids in by_state.items():
        #     print(f"  {state_name}: {len(dids)}")
        #     for did in dids:
        #         print(f"    {did}")


if __name__ == "__main__":
    # Example query: project metadata key `pipeline` and a creation-time window
    query = (
        'state in ("active", "failed", "done") and '
        'created_timestamp >= "2026-03-01 00:00:00" and '
        'created_timestamp <  "2026-04-01 00:00:00" and '
        'pipeline ~ "crv.*"'
    )
    investigate_projects(owner=None, state="all", search_query=query)
```

---

## Search Recipes

Use these directly in `search_projects(search_query=...)`.

Find projects by creator and recent creation time:

```text
owner = "jdoe" and created_timestamp >= "2026-03-20 00:00:00"
```

Find failed or abandoned projects:

```text
state in ("failed", "abandoned")
```

Find by project metadata key/value:

```text
campaign = "crv" and pass = "kpp"
```

Find by regex in query text:

```text
query ~ "files .* from .*raw\\.mu2e\\.cosmics_crv.*"
```

Find projects that include a metadata field:

```text
pipeline present and mode in ("debug", "prod")
```

---

## Performance and Reliability Guidance

- Prefer `with_files=False` for broad discovery, then `get_project(..., with_files=True)` per selected ID.
- Use `state="all"` for dashboards, but narrow by owner/time whenever possible.
- Treat `search_projects(...)` as server-side filtering; use it to reduce client-side loops.
- Handle `None` returns from `get_project(...)`.
- Convert timestamps to UTC for stable reports.
- For very large projects, avoid printing full DID lists unless explicitly requested.

---

## Output Template

Use this exact structure for investigation outputs:

```text
Project investigation summary
- filters: owner=<...>, state=<...>, query=<...>
- projects discovered: <N>

project_id=<id> owner=<owner> state=<state>
- created: <ISO-8601>
- ended: <ISO-8601 or None>
- metadata: <attributes dict>
- handles: total=<N> initial=<N> reserved=<N> done=<N> failed=<N>
- completion: <done/total as percent>

(optional) failed file DIDs:
- <namespace:name>
- <namespace:name>
```

---

## References

- https://fermitools.github.io/data_dispatcher/
- https://fermitools.github.io/data_dispatcher/webapi.html
- https://fermitools.github.io/data_dispatcher/project_query.html
- https://fermitools.github.io/data_dispatcher/worker.html
