# dqm-mcp (prototype)

Read-only MCP stdio server for Mu2e DQM metrics using Query Engine HTTP calls.

## Scope

- Read-only operations only
- Fixed dbname default: `mu2e_dqm_prd`
- Fixed endpoint default: QE nocache URL (`:9443`)
- Stdio transport
- JSON table responses intended for client-side LLM interpretation

## Exposed MCP tools

- `get_server_info()`
  - server defaults, QE endpoint/dbname, limits
- `list_sources(...)`
  - list source tuples from `dqm.sources`
- `list_versions(...)`
  - list available source versions
- `list_values(...)`
  - list metric names from `dqm.values`
- `list_intervals(...)`
  - query/sort intervals by run/subrun or time
- `query_metrics(...)`
  - query `dqm.numbers` or `dqm.limits` with source/value/interval filters
  - defaults: `recent_days=10`, `limit=100`
  - supports expanded source/value/interval payloads

## Local setup

```bash
cd aitools/mcp/dqm
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .
```

Run directly:

```bash
python3 -m dqm_mcp.server
```

Or with launcher:

```bash
chmod +x scripts/start_mcp.sh scripts/smoke_test_stdio.py scripts/install.sh
./scripts/start_mcp.sh
```

Startup compatibility check (no server run):

```bash
./scripts/start_mcp.sh --check
```

Local stdio smoke test:

```bash
./scripts/smoke_test_stdio.py
```

## Config env vars

- `DQM_QE_BASE_URL`
  - default: `https://dbdata0vm.fnal.gov:9443/QE/mu2e/prod/app/SQ/query?`
- `DQM_QE_DBNAME`
  - default: `mu2e_dqm_prd`
- `DQM_QE_TIMEOUT_SECONDS`
  - default: `30`
- `DQM_MCP_LOG_LEVEL`
  - default: `INFO`

## Central/group install

```bash
cd aitools/mcp/dqm
./scripts/install.sh /exp/mu2e/app/users/mu2epro/mcp/deploy/dqm 0.1.0 mu2e
```

This creates:

- `/exp/mu2e/app/users/mu2epro/mcp/deploy/dqm/releases/0.1.0`
- `/exp/mu2e/app/users/mu2epro/mcp/deploy/dqm/current`
- `/exp/mu2e/app/users/mu2epro/mcp/deploy/dqm/registry/mcp-servers.json`

## Notes

- All database reads are over Query Engine HTTP.
- Default behavior is nocache endpoint use.
- Query defaults are intentionally conservative (`limit=100`, recent window 10 days).
- If filters are selective, increase `scan_limit` in `query_metrics(...)`.
