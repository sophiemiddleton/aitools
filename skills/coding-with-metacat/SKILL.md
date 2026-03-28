```skill
---
name: coding-with-metacat
description: Query and manipulate Mu2e file metadata using the metacat Python API. Use for programmatic file discovery, metadata manipulation, and integration into analysis code and reproducible workflows.
compatibility: Requires mu2einit, muse setup ops, Python 3.7+, network access to Fermilab metacat service
metadata:
    version: "1.0.0"
    last-updated: "2026-02-25"
---

# Coding with Metacat

## Overview

**metacat** is Fermilab's file catalog database, adopted by Mu2e for modern data handling.

Use this skill when you need to:
- Query files and datasets from Python code
- Automate file discovery and metadata access
- Manipulate or create file metadata programmatically
- Integrate metacat calls into analysis scripts and workflows
- Upload and declare new files via API
- Build tools or applications that interact with the Mu2e file catalog

**For command-line usage**, see [finding-data-metacat](../finding-data-metacat/SKILL.md) instead.

Related skills:
- [understanding-data-handling](../understanding-data-handling/SKILL.md): Data architecture and naming conventions
- [finding-data-metacat](../finding-data-metacat/SKILL.md): File discovery and prestaging workflows

### Agent Guardrails (Read First)

For AI-generated code, apply these rules consistently:

- Import the client as `from metacat.webapi import MetaCatClient`
- Prefer `client = MetaCatClient()` (reads `METACAT_SERVER_URL` from environment)
- Use full DIDs (`namespace:name`) when calling `get_file()` and dataset methods
- Treat `query()` as **lazy**; wrap with `list(...)` to force execution and surface errors
- Handle missing files via `if file_obj is None:`
- Use [finding-data-metacat](../finding-data-metacat/SKILL.md) for CLI behavior; do not duplicate CLI logic here

### Safety Policy: Read-Only by Default

Mu2e users may have write access to production metacat databases. AI-generated code must default to **read-only methods** unless the user explicitly asks for a write operation and confirms they understand the risk.

**Default agent behavior:**
- Use only read-only API methods (`list_*`, `get_*`, `query`)
- Do not call write methods (`declare_*`, `create_*`, `update_*`, `add_*`, `remove_*`, `delete_*`, `retire_*`) without explicit user confirmation
- Before generating write code, warn that operations may alter the database and request confirmation in the surrounding workflow
- Prefer dry-run or test namespace workflows when available

---

## Setup

**Environment:**
```bash
mu2einit
muse setup ops
```

This brings in `metacat` and related tools.

**What this setup provides:**
- `mu2einit` sets core Mu2e environment and auth context
- `muse setup ops` provides the metacat Python package and runtime stack
- Together they provide required metacat environment variables (notably `METACAT_SERVER_URL` and auth settings used by `MetaCatClient()`)

**Verify installation:**
```bash
python3 -c "import metacat; print(metacat.__version__)"
python3 -c "import os; print('METACAT_SERVER_URL=', os.getenv('METACAT_SERVER_URL'))"
```

**Authentication:**

See [understanding-data-handling](../understanding-data-handling/SKILL.md) for the
full Kerberos → OAuth → service-login flow.

Short form for interactive use:
```bash
getToken                           # Refresh OAuth token (~2h)
metacat auth login -m token $USER  # Authenticate metacat session
```

**Agent checklist (setup):**
- Verify `MetaCatClient` import succeeds before generating workflow code
- Prefer environment-driven endpoint instead of hardcoding server URL
- If auth errors occur, direct user to run `getToken` then `metacat auth login -m token $USER`

---

## Core Concepts

For conceptual background on files, datasets, namespaces, and file naming conventions, see [understanding-data-handling](../understanding-data-handling/SKILL.md).

### Python API Key Concepts

When using the Python API, all results are returned as Python dictionaries:

- **Dataset objects**: Dict with keys like `name`, `namespace`, `creator`, `file_count`, `metadata`, etc.
- **File objects**: Dict with keys like `name`, `fid`, `size`, `checksums`, `created_timestamp`, `metadata`, etc.
- **Query results**: Iterator or list of file dicts matching the query criteria

### Super-Datasets (Non-Standard Naming)

In addition to standard Mu2e default dataset naming, metacat also contains
**non-standard management datasets** (for example `mu2e:Memo-000`).

These are intentionally visually distinct from normal production naming and are
used as **super-datasets** for operations and workflow control:

- Collect files drawn from multiple default datasets (or subsets of datasets)
- Represent management/control groupings rather than a single processing tier
- Gate downstream processing by adding files only when follow-on resources are available

Guidance for AI-generated code:

- Do not assume all dataset names follow the standard naming convention
- Treat super-datasets as valid first-class datasets in read queries
- Avoid inferring semantics from name format alone; use metadata and workflow context
- Treat strings like `Memo-` and metadata keys like `dataset_role` as **examples only**, not a fixed or complete implementation list

Example (read-only discovery pattern):

```python
from metacat.webapi import MetaCatClient

client = MetaCatClient()

# Start with broad discovery in namespace (no write calls)
datasets = client.list_datasets(namespace_pattern="mu2e", with_counts=False)

# Identify possible super-datasets using workflow context or visual naming cues.
# The checks below are illustrative examples only, not a fixed convention.
candidates = [
    d for d in datasets
    if d["name"].startswith("Memo-") or d.get("metadata", {}).get("dataset_role") == "control"
]

for d in candidates:
    did = f"{d['namespace']}:{d['name']}"
    details = client.get_dataset(did=did, exact_file_count=False)
    print(did, details.get("file_count", 0))
```

---

## Python API

The Python `metacat` library provides programmatic access for integration into analysis code.

### Installation

```bash
pip install metacat
```

(Usually pre-installed with `muse setup ops`)

### Authentication

```python
from metacat.webapi import MetaCatClient

# Recommended: use METACAT_SERVER_URL from environment
client = MetaCatClient()

# Optional: explicit server URL + token
client = MetaCatClient(
    "https://metacat.fnal.gov:9443/mu2e_meta_prod/app",
    token="my-auth-token"
)
```

### API Method Auth Matrix

Use this matrix to decide whether authentication and user confirmation are required.

| Method family | Examples | Auth typically required | Can modify DB | Default for AI code |
|---|---|---|---|---|
| Read-only discovery | `list_datasets`, `get_dataset`, `get_dataset_files`, `get_file`, `query` | Usually no (public read), env auth still okay | No | ✅ Use by default |
| File declaration / ingestion | `declare_file`, `declare_files`, `add_files` | Yes | Yes | 🚫 Only with explicit user approval |
| Dataset/namespace creation | `create_dataset`, `create_namespace` | Yes | Yes | 🚫 Only with explicit user approval |
| Metadata or membership updates | `update_dataset`, `move_files`, `remove_files`, `add_child_dataset` | Yes | Yes | 🚫 Only with explicit user approval |
| Destructive operations | `delete_file`, `retire_file`, `remove_dataset` | Yes | Yes (destructive) | ⛔ Require explicit user acknowledgement of risk |

Notes:
- Exact auth enforcement depends on server policy and token scope.
- Even when auth is present, generated code should remain read-only unless the user requested writes.

### Safe Starter Template (Read-Only by Default)

Use this boilerplate in generated code to prevent accidental database mutations.

```python
from metacat.webapi import MetaCatClient

# Explicit safety gate. Keep False unless user has explicitly approved writes.
ALLOW_WRITES = False

WRITE_METHODS = {
    "declare_file",
    "declare_files",
    "add_files",
    "create_dataset",
    "create_namespace",
    "update_dataset",
    "move_files",
    "remove_files",
    "add_child_dataset",
    "delete_file",
    "retire_file",
    "remove_dataset",
}


class SafeMetaCat:
    def __init__(self, allow_writes: bool = False):
        self.allow_writes = allow_writes
        self.client = MetaCatClient()

    def call(self, method_name: str, *args, **kwargs):
        if method_name in WRITE_METHODS and not self.allow_writes:
            raise RuntimeError(
                f"Blocked write method: {method_name}. "
                "Set allow_writes=True only after explicit user approval."
            )

        method = getattr(self.client, method_name)
        return method(*args, **kwargs)


# Default usage: read-only
api = SafeMetaCat(allow_writes=ALLOW_WRITES)

# Safe read examples
dataset = api.call("get_dataset", did="mu2e:mcs.mu2e.dh_test.000.art")
rows = list(api.call("query", "files from mu2e:mcs.mu2e.dh_test.000.art limit 5"))

print(dataset["file_count"], len(rows))
```

If the user explicitly asks for write operations, require all of the following before enabling writes:
- User acknowledges potential for modifying production metadata
- Target namespace/dataset is confirmed
- `ALLOW_WRITES` is intentionally set to `True`
- Write method call is shown explicitly in code review output

### Basic Queries

> ⚠️ **Performance note:** `list_datasets(..., with_counts=True)` can be slow at large scope because per-dataset file counts are expensive to compute. Prefer `with_counts=False` first, then fetch counts only for the narrowed subset.

**Agent checklist (basic calls):**
- `list_datasets(...)` and `get_dataset(...)` return dict-like records
- Use `file_count` (not `n_files`) for dataset size
- Use `get_dataset_files(...)` for dataset membership
- For file details, call `get_file(did=..., with_metadata=True)` and check for `None`
- Avoid global `with_counts=True` scans; filter first by namespace/pattern/time window

**List datasets:**
```python
from metacat.webapi import MetaCatClient

client = MetaCatClient()

# All Mu2e datasets
datasets = client.list_datasets(namespace_pattern="mu2e", with_counts=True)
for ds in datasets:
    print(f"{ds['name']}: {ds['file_count']} files")
```

**Scalable count pattern (recommended):**
```python
from metacat.webapi import MetaCatClient

client = MetaCatClient()

# 1) Fast discovery without counts
datasets = client.list_datasets(namespace_pattern="mu2e", with_counts=False)

# 2) Narrow down first (example: name prefix)
selected = [
    d for d in datasets
    if d["name"].startswith("mcs.mu2e.dh_test")
]

# 3) Fetch count only for selected datasets
for d in selected:
    did = f"{d['namespace']}:{d['name']}"
    info = client.get_dataset(did=did, exact_file_count=False)
    print(did, info.get("file_count", 0))
```

**Get dataset info:**
```python
dataset = client.get_dataset(did="mu2e:sim.mu2e.beam.0429a.art")
print(f"Namespace: {dataset['namespace']}")
print(f"Files: {dataset['file_count']}")
print(f"Created: {dataset['created_timestamp']}")
print(f"Metadata: {dataset['metadata']}")
```

**List files in dataset:**
```python
files = client.get_dataset_files(did="mu2e:sim.mu2e.beam.0429a.art", with_metadata=False)
for f in files:
    print(f"  {f['name']}: {f['size']} bytes")
```

**Get file metadata:**
```python
f = client.get_file(did="mu2e:sim.mu2e.beam.0429a.123456_12345678.art", with_metadata=True)

if f is None:
    print("File not found")
else:
    print(f"Name: {f['name']}")
    print(f"Namespace: {f['namespace']}")
    print(f"Size: {f['size']}")
    print(f"Created: {f['created_timestamp']}")
    print(f"Checksums: {f['checksums']}")
```

### MQL Queries

**Agent checklist (query execution):**
- Start query strings with `files from` (MQL, not SQL)
- Always force evaluation: `rows = list(client.query(...))`
- Catch exceptions around `list(...)`, not just around `query(...)`

**Execute MQL query:**
```python
# Raw query - note: MQL does not use SELECT, use "files from"
files = client.query("""
    files from mu2e:sim.mu2e.beam.0429a.art
    where run = 123456
    order by subrun
""")

for f in files:
    print(f"  {f['namespace']}:{f['name']} size={f['size']}")
```

**Iterate large result sets:**
```python
# Query with limit/offset for pagination
limit = 100
offset = 0
all_files = []

while True:
    batch = client.query(f"""
        files from mu2e:sim.mu2e.beam.0429a.art
        limit {limit} offset {offset}
    """)

    batch_list = list(batch)     # query() is lazy generator
    if not batch_list:
        break

    all_files.extend(batch_list)
    offset += limit
    print(f"Fetched {len(all_files)} files...")

print(f"Total files: {len(all_files)}")
```

### File Uploads and Declarations

> ⚠️ **Write operations section**: The methods below can modify metacat state. Use only after the user has explicitly asked for write access behavior and acknowledged the risk.

**Create metadata for a file:**
```python
import json

metadata = {
    "file_name": "sim.MyUser.test.v1.001000_000001.art",
    "file_type": "art",
    "checksums": {
        "adler32": "12345678"  # Compute from file
    },
    "size": 123456789,
    "metadata": {
        "data_tier": "sim",
        "run": 1000,
        "subrun": 1,
        "n_events": 10000
    }
}

# Write to file
with open("metadata.json", "w") as f:
    json.dump(metadata, f, indent=2)
```

**Declare file to metacat:**
```python
with open("metadata.json") as f:
    metadata = json.load(f)

# Declare file in metacat and attach to dataset
result = client.declare_file(
    did="mu2e:sim.MyUser.test.v1.001000_000001.art",
    dataset_did="mu2e:sim.MyUser.test.v1.art",
    size=metadata["size"],
    checksums=metadata["checksums"],
    metadata=metadata["metadata"]
)
print(f"File declared: {result['fid']}")
```

**Update dataset metadata:**
```python
updates = {
    "status": "validated",
    "quality": "good"
}

client.update_dataset("mu2e:sim.MyUser.test.v1.art", metadata=updates)
```

**Agent checklist (writes):**
- Prefer explicit keyword arguments in write calls (`did=`, `dataset_did=`, `metadata=`)
- Log returned identifiers (e.g., `fid`) for auditability
- Validate required metadata keys before submit
- Confirm with user that write/modify operations are intended before generating executable code

### Error Handling

**Agent checklist (error semantics):**
- `get_file(did=...)` may return `None` for missing file
- `query(...)` may only raise once iterated
- Include exception type in logs (`type(e).__name__`) for triage
- If write methods are attempted, catch and report permission/auth errors without retrying destructive actions

**Catch common errors:**
```python
from metacat.webapi import MetaCatClient

client = MetaCatClient()

# get_file returns None if DID does not exist
f = client.get_file(did="mu2e:sim.nonexistent.art")
if f is None:
    print("File not found in metacat")

# query() raises syntax/data errors when iterated
try:
    list(client.query("select * from invalid.syntax"))
except Exception as e:
    print(f"Query failed: {type(e).__name__}: {e}")
```

---

## Common Patterns

### Pattern 1: Discover Files, Get URLs

**Task:** Find all files in a dataset and get their ROOT URLs for art job input.

```python
from metacat.webapi import MetaCatClient
import subprocess

client = MetaCatClient()

# Query files
files = client.query("""
    files from mu2e:sim.mu2e.beam.0429a.art
    where run = 123456
""")

# Generate URLs via mdh
urls = []
for f in files:
    did = f"{f['namespace']}:{f['name']}"
    result = subprocess.run(
        ["mdh", "print-url", "-l", "tape", "-s", "root", did],
        capture_output=True,
        text=True
    )
    urls.append(result.stdout.strip())

# Use in art job
with open("input_files.txt", "w") as f:
    f.write("\n".join(urls))
```

### Pattern 2: Find Recent Files

**Task:** Find all files in a dataset created in the last 7 days.

```python
from metacat.webapi import MetaCatClient
from datetime import datetime
import time

client = MetaCatClient()

# Compute 7 days ago
seven_days_ago = time.time() - (7 * 86400)

files = client.query(f"""
    files from mu2e:sim.mu2e.beam.0429a.art
    where created_timestamp > {int(seven_days_ago)}
    order by created_timestamp desc
""")

for f in files:
    ts = datetime.fromtimestamp(f["created_timestamp"])
    print(f"{f['name']}: {ts}")
```

### Pattern 3: Dataset Statistics

**Task:** Compute total size and file count for a dataset.


```python
from metacat.webapi import MetaCatClient

client = MetaCatClient()

dataset = client.get_dataset(did="mu2e:sim.mu2e.beam.0429a.art")
n_files = dataset["file_count"]

# Get total size
files = client.query("files from mu2e:sim.mu2e.beam.0429a.art")
total_size = sum(f["size"] for f in files)

print(f"Dataset: {dataset['name']}")
print(f"Files: {n_files}")
print(f"Total size: {total_size / 1e9:.2f} GB")
print(f"Average size: {total_size / n_files / 1e9:.2f} GB")
```

### Pattern 4: Validate Metadata Completeness

**Task:** Check that all files have required metadata fields.

```python
from metacat.webapi import MetaCatClient

client = MetaCatClient()

required_fields = ["run", "subrun", "n_events"]
dataset = "mu2e:sim.mu2e.beam.0429a.art"

files = client.query(f"files from {dataset}")

missing = []
for f in files:
    meta = f.get("metadata", {})
    for field in required_fields:
        if field not in meta or meta[field] is None:
            missing.append((f["name"], field))

if missing:
    print(f"Files missing required metadata ({len(missing)} total):")
    for fname, field in missing[:10]:
        print(f"  {fname}: missing {field}")
else:
    print("All files have required metadata")
```

---

## Integration with Art Jobs

**Use the Python API to generate input file lists for art jobs:**

Generate a fcl file with metacat-discovered files:

```python
from metacat.webapi import MetaCatClient

client = MetaCatClient()

# Query files
files = client.query("""
    files from mu2e:sim.mu2e.beam.0429a.art
    where run = 123456
    limit 10
""")

# Convert to file names
file_names = [f"{f['namespace']}:{f['name']}" for f in files]

# Generate fhicl configuration
fhicl_content = f"""input_files: [
{chr(10).join(f'  "{name}",' for name in file_names[:-1])}
  "{file_names[-1]}"
]
"""

with open("input_files.fcl", "w") as f:
    f.write(fhicl_content)
```

Then use in your art job fcl:
```fhicl
#include "input_files.fcl"

source: {
  module_type: RootInput
  fileNames: @local::input_files
}
```

---

## Troubleshooting

### Environment Not Initialized (Most Common)

**Problem:** `MetaCatClient()` fails, `METACAT_SERVER_URL` is missing, or imports fail because setup was not run in the current shell.

**Solution:**
```bash
mu2einit
muse setup ops
python3 -c "import os; print(os.getenv('METACAT_SERVER_URL'))"
```

If the final command prints `None`, the environment is still not initialized correctly for this shell.

### Authentication Issues

**Problem:** "Authentication failed" or "No credentials" when initializing `MetaCatClient`

**Solution:**
```python
import subprocess

# Renew Kerberos ticket from Python
subprocess.run(["kinit"])

# Reinitialize environment
subprocess.run(["bash", "-c", "mu2einit"])

# Then create client
from metacat.webapi import MetaCatClient
client = MetaCatClient()
```

### Connection Errors

**Problem:** "Connection refused" or "Cannot connect to server"

**Solution:**
```python
from metacat.webapi import MetaCatClient

try:
    client = MetaCatClient()
    # Test connection
    datasets = list(client.list_datasets(namespace_pattern="mu2e", with_counts=False))
    print(f"Datasets visible: {len(datasets)}")
    print("Connection successful")
except Exception as e:
    print(f"Connection failed: {e}")
```

### Query Syntax Errors

**Problem:** "Invalid MQL" or "Syntax error in query"

**Solution:**
- Use `files from` keyword, not `select from` (this is MQL, not SQL)
- Check balanced quotes and parentheses
- Remember: `query()` is lazy; force evaluation with `list(...)`
- Test simple query first: `list(client.query("files from mu2e:* limit 1"))`

Example of correct versus incorrect syntax:
```python
# WRONG - this is SQL syntax, not MQL
result = client.query("select name from mu2e:sim.mu2e.beam.0429a.art")

# CORRECT - MQL syntax
result = client.query("files from mu2e:sim.mu2e.beam.0429a.art")
```

### File Not Found Errors

**Problem:** Exception when trying to access a file with `client.get_file()`

`get_file()` may return `None` for missing DID instead of raising.

**Solution:**
```python
from metacat.webapi import MetaCatClient

client = MetaCatClient()

f = client.get_file(did="mu2e:sim.mu2e.beam.0429a.123456_12345678.art")
if f is None:
    print("File not found in metacat")

    # Try to find similar files
    results = client.query("files from mu2e:sim.mu2e.beam.0429a.art limit 5")
    print("Available files in dataset:")
    for r in results:
        print(f"  {r['namespace']}:{r['name']}")
```

### Large Result Sets

**Problem:** Query timeout or memory exhaustion when iterating millions of files

Related pitfall: broad dataset scans with `with_counts=True` can be slow for the same reason (count computation cost).

**Solution:** Use pagination with limit/offset:

```python
from metacat.webapi import MetaCatClient

client = MetaCatClient()

dataset_did = "mu2e:sim.mu2e.beam.0429a.art"
limit = 1000
offset = 0
all_files = []

while True:
    batch = client.query(f"""
        files from {dataset_did}
        limit {limit} offset {offset}
    """)
    
    batch_list = list(batch)  # Convert iterator to list
    if not batch_list:
        break
    
    all_files.extend(batch_list)
    offset += limit
    print(f"Fetched {len(all_files)} files...")

print(f"Total files: {len(all_files)}")
```

Alternatively, get counts without iterating all files:

```python
dataset = client.get_dataset(did=dataset_did)
print(f"Total files in dataset: {dataset['file_count']}")
```

---

## References

**Official documentation:**
- Fermilab metacat wiki: https://cdcvs.fnal.gov/redmine/projects/metacat/wiki
- Python API docs: (distributed with `metacat` package)

**Mu2e resources:**
- Data handling overview: [understanding-data-handling.md](../understanding-data-handling/SKILL.md)
- File discovery: [finding-data-metacat.md](../finding-data-metacat/SKILL.md)
- File naming conventions: [Data Handling Overview](../understanding-data-handling/SKILL.md#file-naming-and-datasets)

---

**Last updated:** 2026-02-25  
**Author:** Mu2e Computing Group  
**License:** CC-BY-SA (Fermilab standard)

---

## Investigation and Validation Notes

This skill was validated against metacat 4.1.4 using the dataset `mu2e:mcs.mu2e.dh_test.000.art` on 2026-02-25.

**Key findings from validation:**

1. **MQL Syntax Corrected** - This skill previously documented incorrect MQL syntax using `SELECT` keyword. The correct syntax uses `FILES FROM` keyword. All examples have been corrected.

2. **File Object Structure** - Validated that file objects returned by queries are dicts with fields: `name`, `size`, `checksums`, `created_timestamp`, `creator`, `fid`, `namespace`, `retired`, `updated_by`, `updated_timestamp`.

3. **Python Query Semantics** - `query()` returns a lazy generator and server-side errors (e.g., invalid MQL) are raised when iterating (e.g., `list(client.query(...))`).

4. **Missing File Behavior** - `get_file(did=...)` returns `None` for missing files rather than always raising an exception.

5. **Client Import Path** - In this environment, use `from metacat.webapi import MetaCatClient`.

For detailed investigation results, see [METACAT_INVESTIGATION_SUMMARY.md](../../METACAT_INVESTIGATION_SUMMARY.md).

```
