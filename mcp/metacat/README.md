# metacat-mcp (prototype)

Read-only MCP stdio server for Mu2e metacat discovery using the Python API.

## Scope

- Read-only operations only
- No explicit auth/token handling in server code
- Uses environment-provided metacat config (`MetaCatClient()`)
- Stdio transport
- Always runs Mu2e ops setup at server start (`source setupmu2e-art.sh` + `muse setup ops`)
- Fixed merged Python path mode with venv-first precedence (no runtime switch)

## Exposed MCP tools

- `discover_datasets(...)`
  - explicit filters for namespace, name wildcard, created date range, non-empty/counts, pagination
- `get_dataset_details(dataset_did, include_sample_file, include_sample_metadata)`
  - dataset info + optional sample file and sample metadata keys
- `query_dataset_files(...)`
  - common file filters: created date, size, n_events, run/subrun ranges, sorting, pagination
- `get_server_info()`
  - capabilities and safety notes

## Local setup

```bash
cd aitools/mcp/metacat
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
```

Run directly (after Mu2e setup):

```bash
source /cvmfs/mu2e.opensciencegrid.org/setupmu2e-art.sh
muse setup ops
python3 -m metacat_mcp.server
```

Or with launcher:

```bash
chmod +x scripts/start_mcp.sh
./scripts/start_mcp.sh
```

Startup compatibility check (no server run):

```bash
./scripts/start_mcp.sh --check
```

Local stdio smoke test (initialize + tools/list):

```bash
./scripts/smoke_test_stdio.py
```

## Central/group install

Install as shared account (example: `mu2epro`) to a deploy tree:

```bash
cd /exp/mu2e/app/users/rlc/temp/aitools/mcp/metacat
./scripts/install.sh /exp/mu2e/app/users/mu2epro/mcp/deploy/metacat 0.1.0 mu2e
```

This creates:

- `/exp/mu2e/app/users/mu2epro/mcp/deploy/metacat/releases/0.1.0`
- `/exp/mu2e/app/users/mu2epro/mcp/deploy/metacat/current`
- `/exp/mu2e/app/users/mu2epro/mcp/deploy/metacat/registry/mcp-servers.json`

Generate one shared registry with both MCP servers (sim-epochs + metacat):

```bash
/exp/mu2e/app/users/rlc/temp/aitools/mcp/scripts/write_joint_registry.sh /exp/mu2e/app/users/mu2epro/mcp/deploy
```

Default output path:

- `/exp/mu2e/app/users/mu2epro/mcp/deploy/registry/mcp-servers.json`

## MCP client config example

```json
{
  "mcpServers": {
    "metacat-readonly": {
      "command": "/exp/mu2e/app/users/rlc/temp/aitools/mcp/metacat/scripts/start_mcp.sh"
    }
  }
}
```

## Notes

- `discover_datasets(..., with count filters)` may be slower on broad scope.
- Prefer narrowing by namespace + name pattern + date window first.
- This prototype intentionally does not expose write tools.
- Launcher composes `PYTHONPATH` as `venv-site-packages : ops-PYTHONPATH`.
- This keeps MCP dependencies from venv first while still exposing ops-provided modules.
- Original ops path is preserved in `MU2E_OPS_PYTHONPATH`.
- MCP environment is established when the server process starts and remains for that session.
- There is no `mode` toggle for this prototype; restart the server to pick up environment changes.
- Stdio uses line-delimited JSON-RPC messages in this environment, not `Content-Length` framing.
