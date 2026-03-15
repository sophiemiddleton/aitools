#!/usr/bin/env bash
set -e -o pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  install.sh <target-root> <release-version> [group]

Examples:
  ./scripts/install.sh "$PWD/deploy/dqm" 0.1.0
  ./scripts/install.sh /exp/mu2e/app/users/mu2epro/mcp/deploy/dqm 0.1.0 mu2e
USAGE
  exit 2
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage
fi

target_root="$1"
release_version="$2"
group_name="${3:-}"

script_dir="$(cd "$(dirname "$0")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"

release_dir="$target_root/releases/$release_version"
registry_dir="$target_root/registry"
current_link="$target_root/current"

mkdir -p "$release_dir" "$registry_dir"

echo "Installing release to: $release_dir"

log_file="$target_root/install-${release_version}.log"
mkdir -p "$(dirname "$log_file")"
exec > >(tee -a "$log_file") 2>&1
echo "Install log: $log_file"

cp -a "$project_root/." "$release_dir/"
rm -rf "$release_dir/.venv" "$release_dir/venv"
find "$release_dir" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

chmod +x "$release_dir/scripts/start_mcp.sh" \
         "$release_dir/scripts/smoke_test_stdio.py" \
         "$release_dir/scripts/install.sh"

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

echo "[5/5] Updating current symlink and registry"
ln -sfn "$release_dir" "$current_link"

cat > "$registry_dir/mcp-servers.json" <<JSON
{
  "mcpServers": {
    "dqm": {
      "command": "$current_link/scripts/start_mcp.sh",
      "env": {
        "MCP_PYTHON": "$current_link/venv/bin/python",
        "DQM_QE_BASE_URL": "https://dbdata0vm.fnal.gov:9443/QE/mu2e/prod/app/SQ/query?",
        "DQM_QE_DBNAME": "mu2e_dqm_prd"
      }
    }
  }
}
JSON

if [[ -n "$group_name" ]]; then
  chgrp -R "$group_name" "$target_root"
  chmod -R g+rwX "$target_root"
  find "$target_root" -type d -exec chmod g+s {} +
fi

echo "Done."
echo "Current release: $current_link -> $release_dir"
echo "Registry file: $registry_dir/mcp-servers.json"
