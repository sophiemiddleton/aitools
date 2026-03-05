#!/usr/bin/env bash
set -eo pipefail

# Cluster-standard Mu2e setup (do not depend on user ~/.bashrc).
setup_script="/cvmfs/mu2e.opensciencegrid.org/setupmu2e-art.sh"
if [[ ! -f "$setup_script" ]]; then
  echo "ERROR: required setup script not found: $setup_script" >&2
  exit 2
fi

# shellcheck source=/dev/null
set +e
source "$setup_script"
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "ERROR: failed to source $setup_script (exit $rc)" >&2
  exit $rc
fi

# Optional shell setup step for site-specific environments.
# Example:
#   export MCP_BASH_SETUP=/shared/tools/setup_mcp_env.sh
if [[ -n "${MCP_BASH_SETUP:-}" ]]; then
  if [[ -f "$MCP_BASH_SETUP" ]]; then
    # shellcheck source=/dev/null
    source "$MCP_BASH_SETUP"
  else
    echo "ERROR: MCP_BASH_SETUP is set but file not found: $MCP_BASH_SETUP" >&2
    exit 2
  fi
fi

# Mu2e environment setup (required on this cluster for modern Python/toolchain).
# Send setup chatter to stderr so MCP stdio protocol on stdout stays clean.
if ! command -v muse >/dev/null 2>&1; then
  echo "ERROR: muse not found after sourcing $setup_script" >&2
  exit 2
fi

set +e
muse setup ops 1>&2
rc=$?
set -e
if [[ $rc -ne 0 ]]; then
  echo "ERROR: 'muse setup ops' failed (exit $rc)" >&2
  exit $rc
fi

export PYTHONUNBUFFERED=1

# Preserve ops-provided Python path for downstream subprocess use inside tools.
export MU2E_OPS_PYTHONPATH="${PYTHONPATH:-}"

# Prefer explicit interpreter selection:
# 1) MCP_PYTHON env var
# 2) project-local virtualenv interpreter
# 3) python3 from current environment
project_root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${MCP_PYTHON:-}" ]]; then
  python_bin="$MCP_PYTHON"
elif [[ -x "$project_root/.venv/bin/python" ]]; then
  python_bin="$project_root/.venv/bin/python"
else
  python_bin="python3"
fi

if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "ERROR: python interpreter not found: $python_bin" >&2
  exit 2
fi

# PYTHONPATH strategy:
# - isolated (default): server imports use only selected interpreter site-packages.
# - merged: prepend interpreter site-packages, then keep ops PYTHONPATH.
#
# Even in isolated mode, ops PYTHONPATH is preserved in MU2E_OPS_PYTHONPATH so
# MCP tools can pass it to subprocesses that need Mu2e/Spack Python modules.
mode="${MCP_PYTHONPATH_MODE:-isolated}"

site_pkg="$($python_bin - <<'PY'
import site
paths = [p for p in site.getsitepackages() if 'site-packages' in p]
print(paths[0] if paths else '')
PY
)"

if [[ "$mode" == "isolated" ]]; then
  if [[ -n "$site_pkg" ]]; then
    export PYTHONPATH="$site_pkg"
  else
    unset PYTHONPATH || true
  fi
elif [[ "$mode" == "merged" ]]; then
  if [[ -n "$site_pkg" ]]; then
    if [[ -n "${MU2E_OPS_PYTHONPATH:-}" ]]; then
      export PYTHONPATH="$site_pkg:$MU2E_OPS_PYTHONPATH"
    else
      export PYTHONPATH="$site_pkg"
    fi
  fi
else
  echo "ERROR: invalid MCP_PYTHONPATH_MODE='$mode' (use isolated|merged)" >&2
  exit 2
fi

exec "$python_bin" -m sim_epochs_mcp.server
