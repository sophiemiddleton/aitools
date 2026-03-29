#!/usr/bin/env bash
set -uo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage:
  install.sh <target-root> [release-tag|latest] [group]

Examples:
  ./scripts/install.sh "$PWD/deploy/code-index" latest
  ./scripts/install.sh /exp/mu2e/app/users/mu2epro/mcp/deploy/code-index v2.14.2 mu2e

Notes:
  - Installs upstream code-index-mcp from a pinned tag into releases/<tag>.
  - Creates venv and installs package in that release.
  - Automatically attempts Mu2e/Spack Python setup if current python is too old.
  - Updates current symlink and writes registry/mcp-servers.json with:
  py-index-central (MCP_PROJECT_PATH=<target-root>/repos)
  py-index-local   (MCP_PROJECT_PATH=.)
USAGE
  exit 2
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
fi

if [[ $# -lt 1 || $# -gt 3 ]]; then
  usage
fi

target_root="$1"
requested_tag="${2:-latest}"
group_name="${3:-}"

UPSTREAM_REPO_URL="https://github.com/johnhuang316/code-index-mcp.git"

script_dir="$(cd "$(dirname "$0")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"

python_is_ge_3_10() {
  local py="$1"
  "$py" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

attempt_mu2e_spack_python_setup() {
  local mu2e_setup="/cvmfs/mu2e.opensciencegrid.org/setupmu2e-art.sh"

  # Run setup in a subprocess so any shell-exit behavior inside setup scripts
  # cannot terminate this installer.
  if [[ ! -r "$mu2e_setup" ]]; then
    echo ""
    return 0
  fi

  bash -lc '
    source /cvmfs/mu2e.opensciencegrid.org/setupmu2e-art.sh >/dev/null 2>&1 || true
    if command -v spack >/dev/null 2>&1; then
      spack load python/hh32mtk >/dev/null 2>&1 || true
    fi
    for cand in python3.12 python3.11 python3.10 python3 python; do
      if command -v "$cand" >/dev/null 2>&1; then
        command -v "$cand"
        exit 0
      fi
    done
    exit 1
  ' 2>/dev/null || true
}

select_python() {
  if [[ -n "${MCP_PYTHON:-}" ]]; then
    echo "$MCP_PYTHON"
    return 0
  fi

  for cand in python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
      local resolved
      resolved="$(command -v "$cand")"
      if python_is_ge_3_10 "$resolved"; then
        echo "$resolved"
        return 0
      fi
    fi
  done

  echo ""
}

python_bin="$(select_python)"

if [[ -z "$python_bin" ]] && [[ -z "${MCP_PYTHON:-}" ]]; then
  fallback_python="$(attempt_mu2e_spack_python_setup | tail -n 1)"
  if [[ -n "$fallback_python" ]] && python_is_ge_3_10 "$fallback_python"; then
    python_bin="$fallback_python"
  else
    python_bin="$(select_python)"
  fi
fi

if [[ -z "$python_bin" ]]; then
  echo "ERROR: could not find Python >= 3.10 for code-index-mcp." >&2
  echo "       Auto setup attempted: source setupmu2e-art + spack load python/hh32mtk" >&2
  echo "       Set MCP_PYTHON explicitly, e.g.:" >&2
  echo "       MCP_PYTHON=/usr/bin/python3.10 ./scripts/install.sh <target> latest" >&2
  exit 2
fi

if ! python_is_ge_3_10 "$python_bin"; then
  echo "ERROR: $python_bin is too old. code-index-mcp requires Python >= 3.10." >&2
  echo "       Set MCP_PYTHON to a 3.10+ interpreter, e.g.:" >&2
  echo "       MCP_PYTHON=/usr/bin/python3.10 ./scripts/install.sh <target> latest" >&2
  exit 2
fi

resolve_latest_tag() {
  "$python_bin" - <<'PY'
import json
import urllib.request

url = "https://api.github.com/repos/johnhuang316/code-index-mcp/releases/latest"
with urllib.request.urlopen(url, timeout=30) as r:
    data = json.load(r)
print(data["tag_name"])
PY
}

if [[ "$requested_tag" == "latest" ]]; then
  release_tag="$(resolve_latest_tag)"
else
  release_tag="$requested_tag"
fi

release_dir="$target_root/releases/$release_tag"
src_dir="$release_dir/src"
registry_dir="$target_root/registry"
current_link="$target_root/current"
default_central_repos="$target_root/repos"
default_central_indexer="$target_root/indexer"

mkdir -p "$release_dir" "$registry_dir" "$default_central_repos" "$default_central_indexer"

echo "Installing code-index-mcp tag: $release_tag"
echo "Target release dir: $release_dir"
echo "Python interpreter: $python_bin"

log_file="$target_root/install-${release_tag}.log"
mkdir -p "$(dirname "$log_file")"
exec > >(tee -a "$log_file") 2>&1

echo "Install log: $log_file"
echo "Upstream repo: $UPSTREAM_REPO_URL"
echo "Release tag: $release_tag"

echo "[1/6] Cloning upstream source"
rm -rf "$src_dir"
git clone --depth 1 --branch "$release_tag" "$UPSTREAM_REPO_URL" "$src_dir"

actual_commit="$(git -C "$src_dir" rev-parse HEAD)"
echo "Resolved commit: $actual_commit"

echo "[2/6] Copying local wrapper scripts"
mkdir -p "$release_dir/scripts"
cp -a "$project_root/scripts/start_mcp.sh" "$release_dir/scripts/start_mcp.sh"
cp -a "$project_root/scripts/smoke_test_stdio.py" "$release_dir/scripts/smoke_test_stdio.py"
chmod +x "$release_dir/scripts/start_mcp.sh" "$release_dir/scripts/smoke_test_stdio.py"

echo "[3/6] Creating Python virtual environment"
"$python_bin" -m venv "$release_dir/venv"
source "$release_dir/venv/bin/activate"

echo "[4/6] Installing Python dependencies and package"
PYTHONPATH= pip install -U pip
if [[ -f "$src_dir/requirements.txt" ]]; then
  PYTHONPATH= pip install -r "$src_dir/requirements.txt"
fi
PYTHONPATH= pip install "$src_dir"

echo "[5/6] Updating current symlink"
ln -sfn "$release_dir" "$current_link"

echo "[6/6] Writing registry"
cat > "$registry_dir/mcp-servers.json" <<JSON
{
  "mcpServers": {
    "py-index-central": {
      "command": "$current_link/scripts/start_mcp.sh",
      "env": {
        "MCP_PYTHON": "$current_link/venv/bin/python",
        "MCP_PROJECT_PATH": "$default_central_repos",
        "MCP_INDEXER_PATH": "$default_central_indexer"
      }
    },
    "py-index-local": {
      "command": "$current_link/scripts/start_mcp.sh",
      "env": {
        "MCP_PYTHON": "$current_link/venv/bin/python",
        "MCP_PROJECT_PATH": "."
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
echo "Default central repo root: $default_central_repos"
echo "Default central index root: $default_central_indexer"
echo "Registry file: $registry_dir/mcp-servers.json"
