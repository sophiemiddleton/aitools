# sim-epochs-mcp (example)

Minimal MCP stdio server that answers:

- "What are the simulation epochs?"
- "What are the datasets in epoch X?"

The server reads a JSON file and exposes two MCP tools.

## Features

- Stdio transport (`mcp.run(transport="stdio")`)
- File-backed catalog (`SIM_EPOCHS_FILE` env override)
- Optional shell setup before Python startup (`MCP_BASH_SETUP`)
- Cluster bootstrap from `/cvmfs/mu2e.opensciencegrid.org/setupmu2e-art.sh`
- `muse setup ops` run in launcher before Python startup
- Interpreter selection: `MCP_PYTHON` > `.venv/bin/python` > `python3`
- PYTHONPATH modes: `isolated` (default) or `merged` via `MCP_PYTHONPATH_MODE`
- Safe logging to `stderr` only

## Catalog format

Default file: `data/sim_catalog.json`

Supported shapes:

1. Preferred:

```json
{
  "epochs": [
    {"name": "MDC2025ad", "datasets": ["...", "..."]}
  ]
}
```

2. Compact:

```json
{
  "MDC2025ad": ["...", "..."],
  "MDC2020": ["..."]
}
```

## Local setup

```bash
cd aitools/mcp/sim-epochs
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
```

Run directly:

```bash
python3 -m sim_epochs_mcp.server
```

Or with launcher:

```bash
chmod +x scripts/start_mcp.sh
./scripts/start_mcp.sh
```

## Optional shell setup before launch

If your environment needs a setup step (for example, to define `PYTHONPATH`):

```bash
export MCP_BASH_SETUP=/path/to/setup_mcp_env.sh
./scripts/start_mcp.sh
```

A sample script is provided at `scripts/setup_example.sh`.

Note: `scripts/start_mcp.sh` does not depend on user `~/.bashrc`; it sources
`/cvmfs/mu2e.opensciencegrid.org/setupmu2e-art.sh` and then runs `muse setup ops`.

If you need a specific interpreter, set:

```bash
export MCP_PYTHON=/shared/mcp/sim-epochs/current/venv/bin/python
```

## Recommended PYTHONPATH strategy (important)

`muse setup ops` can inject a large Spack `PYTHONPATH`. That path is useful for
some downstream tools, but can break MCP server imports when versions conflict.

Launcher behavior:

- `MCP_PYTHONPATH_MODE=isolated` (default)
  - MCP server uses selected interpreter site-packages only.
  - ops path is preserved in `MU2E_OPS_PYTHONPATH` for tool subprocesses.
- `MCP_PYTHONPATH_MODE=merged`
  - Uses interpreter site-packages plus ops path in one `PYTHONPATH`.

Recommendation:

- Keep `isolated` for server stability.
- When a specific MCP tool needs Mu2e/Spack Python modules, launch that
  subprocess with `PYTHONPATH=$MU2E_OPS_PYTHONPATH`.

## MCP client config example

Use your client’s MCP configuration, e.g.:

```json
{
  "mcpServers": {
    "sim-epochs": {
      "command": "/shared/mcp/sim-epochs/current/scripts/start_mcp.sh",
      "env": {
        "SIM_EPOCHS_FILE": "/shared/mcp/sim-epochs/catalog/sim_catalog.json",
        "MCP_BASH_SETUP": "/shared/mcp/sim-epochs/current/scripts/setup_cluster_env.sh"
      }
    }
  }
}
```

## Central shared MCP definition (disk-only)

Yes, this is possible, with one practical caveat:

- Most clients/harnesses do **not** support an `include` directive for MCP config files.
- The usual pattern is a per-user config file that is either:
  - a symlink to one shared JSON file, or
  - a copied file refreshed by a setup script.

Use top-level helper from the MCP workspace:

- `../scripts/install_user_mcp_config.sh`

Example (symlink mode, recommended):

```bash
../scripts/install_user_mcp_config.sh \
  /shared/mcp/registry/mcp-servers.json \
  ~/.config/llm-harness/mcp.json \
  link
```

Example (copy mode):

```bash
../scripts/install_user_mcp_config.sh \
  /shared/mcp/registry/mcp-servers.json \
  ~/.config/llm-harness/mcp.json \
  copy
```

Use `link` when possible so central updates appear immediately for all users.

## Shared-disk multi-user deployment (cluster)

A practical pattern for many Linux users on shared storage:

```text
/shared/mcp/sim-epochs/
  releases/
    0.1.0/
      (this project)
      venv/
  current -> /shared/mcp/sim-epochs/releases/0.1.0
  registry/
    mcp-servers.json
  catalog/
    sim_catalog.json
```

Recommended: perform this install while logged in as the shared/service account
(for example `mu2epro`) so ownership is correct from the start.

Install once per release:

```bash
cd /path/to/aitools/mcp/sim-epochs
./scripts/install.sh "$PWD/deploy/sim-epochs" 0.1.0
# or absolute path:
# ./scripts/install.sh /central/mcp/sim-epochs 0.1.0 ./data/sim_catalog.json mu2e
```

`<target-root>` is an argument to the installer and can be absolute or relative
(including `.`).

This creates/updates:

- `<target-root>/releases/0.1.0`
- `<target-root>/current` (symlink)
- `<target-root>/catalog/sim_catalog.json`
- `<target-root>/registry/mcp-servers.json`

If installation stops early, inspect:

- `<target-root>/install-<release-version>.log`

The installer prints numbered steps and reports the line number on failure.

Recommended launcher tweak for shared installs:

```bash
# inside start_mcp.sh, if desired
exec /shared/mcp/sim-epochs/current/venv/bin/python -m sim_epochs_mcp.server
```

Then users only reference `.../current/scripts/start_mcp.sh` in their MCP config.

For centralized management across many MCP servers, maintain one shared file such as:

- `/shared/mcp/registry/mcp-servers.json`

and have user-local MCP configs symlink to it.

## Exposed tools

- `get_simulation_epochs()`
- `get_datasets_for_epoch(epoch: str)`

Both responses include `catalog_file` for traceability.
