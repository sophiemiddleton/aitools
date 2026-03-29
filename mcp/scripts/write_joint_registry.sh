#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  write_joint_registry.sh <deploy-root> [output-json]
                          [--py-central-repos <path>] [--py-local-default-path <path>]

Arguments:
  deploy-root    Root of the MCP deployment tree (required).
  output-json    Where to write the registry (default: <deploy-root>/registry/mcp-servers.json).

Options:
  --py-central-repos <path>      Path to central mirror for py-index-central.
                                 Default: <deploy-root>/code-index/repos
  --py-local-default-path <path> Default project path for py-index-local.
                                 Default: .

Examples:
  ./scripts/write_joint_registry.sh /exp/mu2e/app/users/mu2epro/mcp/deploy

  ./scripts/write_joint_registry.sh /exp/mu2e/app/users/mu2epro/mcp/deploy \
      --py-central-repos /exp/mu2e/app/users/mu2epro/mcp/deploy/code-index/repos

Notes:
  - Expects deploy-root to contain: sim-epochs/current, metacat/current, dqm/current
  - Adds py-index servers if code-index/current exists under deploy-root.
  - Logical MCP names are py-index-*; install directory remains code-index/.
  - Writes one MCP registry with all servers for Cline/clients.
USAGE
  exit 2
}

deploy_root=""
output_json=""
py_central_repos=""
py_local_default_path=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --py-central-repos) py_central_repos="$2"; shift 2 ;;
    --py-local-default-path) py_local_default_path="$2"; shift 2 ;;
    --help|-h) usage ;;
    -*)
      echo "ERROR: Unknown option: $1" >&2; usage ;;
    *)
      if [[ -z "$deploy_root" ]]; then
        deploy_root="$1"
      elif [[ -z "$output_json" ]]; then
        output_json="$1"
      else
        echo "ERROR: Unexpected argument: $1" >&2; usage
      fi
      shift ;;
  esac
done

if [[ -z "$deploy_root" ]]; then
  usage
fi

output_json="${output_json:-$deploy_root/registry/mcp-servers.json}"
py_central_repos="${py_central_repos:-$deploy_root/code-index/repos}"
py_local_default_path="${py_local_default_path:-.}"

sim_root="$deploy_root/sim-epochs"
metacat_root="$deploy_root/metacat"
dqm_root="$deploy_root/dqm"
code_index_root="$deploy_root/code-index"

if [[ ! -d "$sim_root/current" ]]; then
  echo "ERROR: missing sim-epochs current release at $sim_root/current" >&2
  exit 2
fi

if [[ ! -d "$metacat_root/current" ]]; then
  echo "ERROR: missing metacat current release at $metacat_root/current" >&2
  exit 2
fi

if [[ ! -d "$dqm_root/current" ]]; then
  echo "ERROR: missing dqm current release at $dqm_root/current" >&2
  exit 2
fi

if [[ ! -d "$code_index_root/current" ]]; then
  echo "WARNING: code-index/current not found at $code_index_root/current — skipping py-index servers" >&2
fi

mkdir -p "$(dirname "$output_json")"

python3 - "$deploy_root" "$output_json" "$py_central_repos" "$py_local_default_path" <<'PYEOF'
import json, sys, os

deploy_root, output_json, py_central_repos, py_local_default_path = sys.argv[1:5]
code_index_root = os.path.join(deploy_root, "code-index")
has_py_index = os.path.isdir(os.path.join(code_index_root, "current"))

servers = {}

servers["sim-epochs"] = {
    "command": f"{deploy_root}/sim-epochs/current/scripts/start_mcp.sh",
    "env": {
        "SIM_EPOCHS_FILE": f"{deploy_root}/sim-epochs/catalog/sim_catalog.json",
        "MCP_PYTHON": f"{deploy_root}/sim-epochs/current/venv/bin/python",
        "MCP_PYTHONPATH_MODE": "isolated",
    },
}

servers["metacat-readonly"] = {
    "command": f"{deploy_root}/metacat/current/scripts/start_mcp.sh",
    "env": {
        "MCP_PYTHON": f"{deploy_root}/metacat/current/venv/bin/python",
    },
}

servers["dqm"] = {
    "command": f"{deploy_root}/dqm/current/scripts/start_mcp.sh",
    "env": {
        "MCP_PYTHON": f"{deploy_root}/dqm/current/venv/bin/python",
        "DQM_QE_BASE_URL": "https://dbdata0vm.fnal.gov:9443/QE/mu2e/prod/app/SQ/query?",
        "DQM_QE_DBNAME": "mu2e_dqm_prd",
    },
}

if has_py_index:
  servers["py-index-central"] = {
    "command": f"{code_index_root}/current/scripts/start_mcp.sh",
    "env": {
      "MCP_PYTHON": f"{code_index_root}/current/venv/bin/python",
      "MCP_PROJECT_PATH": py_central_repos,
      "MCP_INDEXER_PATH": f"{code_index_root}/indexer",
    },
  }
  servers["py-index-local"] = {
    "command": f"{code_index_root}/current/scripts/start_mcp.sh",
    "env": {
      "MCP_PYTHON": f"{code_index_root}/current/venv/bin/python",
      "MCP_PROJECT_PATH": py_local_default_path,
    },
  }

with open(output_json, "w") as f:
    json.dump({"mcpServers": servers}, f, indent=2)
    f.write("\n")

print(f"Wrote: {output_json}")
for name in servers:
    print(f"  - {name}")
PYEOF
