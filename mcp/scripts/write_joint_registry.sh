#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  write_joint_registry.sh <deploy-root> [output-json]

Examples:
  ./scripts/write_joint_registry.sh /exp/mu2e/app/users/mu2epro/mcp/deploy
  ./scripts/write_joint_registry.sh /exp/mu2e/app/users/mu2epro/mcp/deploy /exp/mu2e/app/users/mu2epro/mcp/deploy/registry/mcp-servers.json

Notes:
  - Expects deploy-root to contain:
      sim-epochs/current
      metacat/current
  - Writes one MCP registry with both servers for Cline/clients.
USAGE
  exit 2
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
fi

deploy_root="$1"
output_json="${2:-$deploy_root/registry/mcp-servers.json}"

sim_root="$deploy_root/sim-epochs"
metacat_root="$deploy_root/metacat"

if [[ ! -d "$sim_root/current" ]]; then
  echo "ERROR: missing sim-epochs current release at $sim_root/current" >&2
  exit 2
fi

if [[ ! -d "$metacat_root/current" ]]; then
  echo "ERROR: missing metacat current release at $metacat_root/current" >&2
  exit 2
fi

mkdir -p "$(dirname "$output_json")"

cat > "$output_json" <<JSON
{
  "mcpServers": {
    "sim-epochs": {
      "command": "$sim_root/current/scripts/start_mcp.sh",
      "env": {
        "SIM_EPOCHS_FILE": "$sim_root/catalog/sim_catalog.json",
        "MCP_PYTHON": "$sim_root/current/venv/bin/python",
        "MCP_PYTHONPATH_MODE": "isolated"
      }
    },
    "metacat-readonly": {
      "command": "$metacat_root/current/scripts/start_mcp.sh",
      "env": {
        "MCP_PYTHON": "$metacat_root/current/venv/bin/python"
      }
    }
  }
}
JSON

echo "Wrote: $output_json"
