#!/usr/bin/env bash
set -e -o pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  install.sh <target-root> <release-version> [catalog-json] [group]

Examples:
  ./scripts/install.sh "$PWD/deploy/sim-epochs" 0.1.0
  ./scripts/install.sh /shared/mcp/sim-epochs 0.1.0
  ./scripts/install.sh /shared/mcp/sim-epochs 0.1.0 ./data/sim_catalog.json mu2e

Notes:
  - Run this script as the service/shared account (e.g. mu2epro) to preserve ownership.
  - <target-root> may be absolute or relative (including '.').
  - It creates:
      <target-root>/releases/<release-version>
      <target-root>/current (symlink)
      <target-root>/catalog/sim_catalog.json
      <target-root>/registry/mcp-servers.json
USAGE
  exit 2
}

if [[ $# -lt 2 || $# -gt 4 ]]; then
  usage
fi

target_root="$1"
release_version="$2"
catalog_src="${3:-$(cd "$(dirname "$0")/.." && pwd)/data/sim_catalog.json}"
group_name="${4:-}"

if [[ ! -f "$catalog_src" ]]; then
  echo "ERROR: catalog source file not found: $catalog_src" >&2
  exit 2
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"

release_dir="$target_root/releases/$release_version"
catalog_dir="$target_root/catalog"
registry_dir="$target_root/registry"
current_link="$target_root/current"

mkdir -p "$release_dir" "$catalog_dir" "$registry_dir"

echo "Installing release to: $release_dir"

log_file="$target_root/install-${release_version}.log"
mkdir -p "$(dirname "$log_file")"
exec > >(tee -a "$log_file") 2>&1
echo "Install log: $log_file"

echo "Source provenance (best effort):"
if command -v git >/dev/null 2>&1; then
  if git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "  git root: $project_root"
    echo "  branch: $(git -C "$project_root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
    echo "  commit: $(git -C "$project_root" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "  describe: $(git -C "$project_root" describe --tags --always 2>/dev/null || echo unknown)"
    echo "  status (--short):"
    git -C "$project_root" status --short 2>/dev/null || true
  else
    echo "  git metadata not available (not a work tree): $project_root"
  fi
else
  echo "  git command not available"
fi

# Copy project content into release directory (exclude local virtual env and caches).
cp -a "$project_root/." "$release_dir/"
rm -rf "$release_dir/.venv" "$release_dir"/**/__pycache__ 2>/dev/null || true
find "$release_dir" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

# Ensure launcher scripts are executable.
chmod +x "$release_dir/scripts/start_mcp.sh" \
         "$release_dir/scripts/setup_example.sh" \
         "$release_dir/scripts/install.sh"

# Build runtime environment using Mu2e ops setup.
echo "[1/5] Sourcing Mu2e setup"
set +e
source /cvmfs/mu2e.opensciencegrid.org/setupmu2e-art.sh
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "ERROR: failed to source /cvmfs/mu2e.opensciencegrid.org/setupmu2e-art.sh (exit $rc)" >&2
  exit $rc
fi

echo "[2/5] Running muse setup ops"
set +e
muse setup ops
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "ERROR: 'muse setup ops' failed (exit $rc)" >&2
  exit $rc
fi

echo "[3/5] Creating Python virtual environment"
python3 -m venv "$release_dir/venv"
source "$release_dir/venv/bin/activate"

echo "[4/5] Installing Python dependencies"
PYTHONPATH= pip install -U pip
if [[ -f "$release_dir/requirements.txt" ]]; then
  PYTHONPATH= pip install -r "$release_dir/requirements.txt"
fi
PYTHONPATH= pip install --ignore-installed "$release_dir"

# Install catalog and current symlink.
echo "[5/5] Installing catalog, current symlink, and registry"
cp -f "$catalog_src" "$catalog_dir/sim_catalog.json"
ln -sfn "$release_dir" "$current_link"

# Write central MCP registry definition.
cat > "$registry_dir/mcp-servers.json" <<JSON
{
  "mcpServers": {
    "sim-epochs": {
      "command": "$current_link/scripts/start_mcp.sh",
      "env": {
        "SIM_EPOCHS_FILE": "$catalog_dir/sim_catalog.json",
        "MCP_PYTHON": "$current_link/venv/bin/python",
        "MCP_PYTHONPATH_MODE": "isolated"
      }
    }
  }
}
JSON

# Optional group ownership/permissions for shared maintenance.
if [[ -n "$group_name" ]]; then
  chgrp -R "$group_name" "$target_root"
  chmod -R g+rwX "$target_root"
  find "$target_root" -type d -exec chmod g+s {} +
fi

echo "Done."
echo "Current release: $current_link -> $release_dir"
echo "Registry file: $registry_dir/mcp-servers.json"
echo "Catalog file:  $catalog_dir/sim_catalog.json"
