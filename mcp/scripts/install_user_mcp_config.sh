#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  cat >&2 <<'USAGE'
Usage:
  install_user_mcp_config.sh <shared-config-json> <user-config-json> [link|copy]

Examples:
  install_user_mcp_config.sh /shared/mcp/registry/mcp-servers.json ~/.config/llm-harness/mcp.json link
  install_user_mcp_config.sh /shared/mcp/registry/mcp-servers.json ~/.config/llm-harness/mcp.json copy
USAGE
  exit 2
fi

shared_config="$1"
user_config="$2"
mode="${3:-link}"

if [[ ! -f "$shared_config" ]]; then
  echo "ERROR: shared config does not exist: $shared_config" >&2
  exit 2
fi

mkdir -p "$(dirname "$user_config")"

case "$mode" in
  link)
    ln -sfn "$shared_config" "$user_config"
    echo "Linked $user_config -> $shared_config"
    ;;
  copy)
    cp "$shared_config" "$user_config"
    echo "Copied $shared_config -> $user_config"
    ;;
  *)
    echo "ERROR: mode must be 'link' or 'copy'" >&2
    exit 2
    ;;
esac
