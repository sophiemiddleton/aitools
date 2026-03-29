# code-index-mcp (external upstream integration)

This MCP wraps the upstream Code Index MCP server from:

- https://github.com/johnhuang316/code-index-mcp

Unlike other MCPs in this workspace, this one is installed from a pinned upstream
release tag into the deploy tree.

## Scope

- Install upstream release from GitHub tag
- Keep local launcher and smoke test scripts stable in this repo
- Support two deployment server entries:
  - `py-index-central` for shared cached repos/index
  - `py-index-local` for user-local code indexing on demand

## Local trial install

```bash
cd aitools/mcp/code-index
./scripts/install.sh "$PWD/deploy/code-index" latest
```

This creates:

- `<target>/releases/<tag>/src` (upstream checkout)
- `<target>/releases/<tag>/venv`
- `<target>/current` (symlink)
- `<target>/registry/mcp-servers.json`

The per-code-index registry written by `install.sh` includes:

- `py-index-central` with:
  - `MCP_PROJECT_PATH=<target>/repos`
  - `MCP_INDEXER_PATH=<target>/indexer`
- `py-index-local` with `MCP_PROJECT_PATH=.`

In the full MCP deployment, `mcp/scripts/write_joint_registry.sh` emits the same
two `py-index` entries into the combined registry.

Run launcher check:

```bash
<target>/current/scripts/start_mcp.sh --help
```

Run stdio smoke test:

```bash
<target>/current/scripts/smoke_test_stdio.py --project-path /absolute/path/to/repo
```

### Where deep-index artifacts are written

By default, if `MCP_INDEXER_PATH` is not set, upstream `code-index-mcp` can write
index data under the system temp area (for example `/tmp/code_indexer/...`).

For deterministic output under your deploy tree, set `MCP_INDEXER_PATH` before
starting or smoke-testing the server:

```bash
export MCP_INDEXER_PATH=<target>/indexer
<target>/current/scripts/smoke_test_stdio.py \
  --project-path /absolute/path/to/repo \
  --build-deep-index
```

Then artifacts should appear under:

- `<target>/indexer/code_indexer/<hash>/index.db`
- `<target>/indexer/code_indexer/<hash>/index.shallow.json`

## Example repo location for testing

Put or clone test repositories under:

- `/exp/mu2e/app/users/rlc/temp/mcp_code_index_repos`

Example:

```bash
mkdir -p /exp/mu2e/app/users/rlc/temp/mcp_code_index_repos
cd /exp/mu2e/app/users/rlc/temp/mcp_code_index_repos
git clone https://github.com/Mu2e/Offline.git
```

Then smoke test with:

```bash
<target>/current/scripts/smoke_test_stdio.py \
  --project-path /exp/mu2e/app/users/rlc/temp/mcp_code_index_repos/Offline
```

## Runtime guidance for users and LLMs

- Prefer `py-index-central` for fast lookup against already-cached shared repos.
- Use `py-index-local` when a user asks to index local code.
- Do not automatically trigger deep/local indexing; run it only when explicitly requested.
- If needed, set or change the project path at runtime with `set_project_path` before indexing.

## Central read-only behavior

The central deployment uses:

- source repos under `<deploy-root>/repos`
- shared prebuilt indexes under `<deploy-root>/indexer`

Regular users should treat both as read-only.

Upstream `code-index-mcp` expects its effective index directory to be writable at
runtime. Because normal users cannot write into the shared deploy area, the local
launcher handles this automatically:

- If `MCP_INDEXER_PATH` is writable, it uses it directly.
- If `MCP_INDEXER_PATH` is not writable, it falls back to a user cache directory:
  - `${XDG_CACHE_HOME}/mu2e-code-index/indexer`, or
  - `${HOME}/.cache/mu2e-code-index/indexer`
- On startup, it keeps user cache in sync with shared indexes by copying missing or
  newer per-hash artifacts from shared (both `index.db` and `index.shallow.json`)
  to the user cache, so you get the latest deep indexes from central even if your
  cache was seeded earlier.

This means `py-index-central` is effectively:

- read-only for shared repos and shared deploy indexes
- writable only in the user's local cache area

In practice, users should not need to do anything special beyond reconnecting to
the MCP after a reinstall/update.

### Verifying the fallback cache

Check whether a user-local cache exists:

```bash
find "${XDG_CACHE_HOME:-$HOME/.cache}/mu2e-code-index/indexer" -maxdepth 5 -type f | head
```

Typical files include:

- `.../code_indexer/<hash>/index.shallow.json`
- `.../code_indexer/<hash>/index.db`

If a hash directory exists in user cache but index.db is missing, the next MCP
startup will copy it from shared so deep indexing becomes available.

### Troubleshooting permission errors

If a user still sees errors like:

```text
Permission denied: .../deploy/code-index/indexer/code_indexer/...
```

then usually one of these is true:

- the deploy was not reinstalled after a launcher update
- the MCP client is still using an older cached process
- the user has not reconnected/restarted the MCP client after reinstall

Recommended recovery steps:

1. Reinstall `code-index` into deploy so `current/scripts/start_mcp.sh` is updated.
2. Regenerate the joint registry.
3. Reconnect or restart the MCP client.
4. Re-test `py-index-central`.

## Refreshing a long-lived session

If a user stays connected to the MCP for a long time, the running process may not
automatically notice that the shared central index was rebuilt by maintenance jobs.

Recommended behavior:

- For `py-index-central`, reconnect or restart the MCP client to pick up a newly
  seeded/shared index after central maintenance.
- After reconnect, call `set_project_path` again for the repo you care about.
- If you only need a quick file-list refresh for the current repo, call `refresh_index`.
- If you need updated symbol-level information, call `build_deep_index`.

Rule of thumb:

- `refresh_index` = fast/shallow refresh
- `build_deep_index` = full symbol rebuild for the selected repo
- reconnect = safest way to pick up central index changes after days-long sessions

## Central repo maintenance

Use the maintenance script in `scripts/sync_and_index_repos.py` to keep the central
repo mirror and indexes fresh.

Example repo list file:

```text
# repo [branch]
Mu2e/Offline main
Mu2e/Production main
Mu2e/aitools main
```

Run fast shallow refreshes for changed repos:

```bash
python3 scripts/sync_and_index_repos.py \
  --deploy-root /exp/mu2e/app/users/mu2epro/mcp/deploy/code-index \
  --repo-list /path/to/repo-list.txt \
  --mode fast
```

Run deep symbol indexing only when branch heads changed since the last deep run:

```bash
python3 scripts/sync_and_index_repos.py \
  --deploy-root /exp/mu2e/app/users/mu2epro/mcp/deploy/code-index \
  --repo-list /path/to/repo-list.txt \
  --mode deep
```

Notes:

- The script clones missing repos into `<deploy-root>/repos`.
- Existing repos are fetched and fast-forwarded to the configured branch head.
- Fast mode runs the MCP shallow index (`refresh_index`).
- Deep mode runs `build_deep_index` and records the last indexed commit.
- Deep indexing is not incremental in upstream code; the script skips unchanged
  commits so a nightly deep run is sensible, while fast mode can run every 15 min.
