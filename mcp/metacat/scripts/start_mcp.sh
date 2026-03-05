#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Required setup for Mu2e metacat Python environment
set +u
# Temporary guard for current CVMFS setup script behavior under set -e.
# Remove once updated setupmu2e-art.sh is deployed on CVMFS.
if [[ $- == *e* ]]; then
  _mcp_restore_errexit=1
  set +e
else
  _mcp_restore_errexit=0
fi
source /cvmfs/mu2e.opensciencegrid.org/setupmu2e-art.sh 1>&2
_mcp_setup_rc=$?
if [[ ${_mcp_restore_errexit} -eq 1 ]]; then
  set -e
fi
unset _mcp_restore_errexit
if [[ ${_mcp_setup_rc} -ne 0 ]]; then
  exit ${_mcp_setup_rc}
fi
unset _mcp_setup_rc
muse setup ops 1>&2
set -u

# Preserve ops PYTHONPATH and compose merged runtime path with venv-first precedence.
MU2E_OPS_PYTHONPATH="${PYTHONPATH:-}"
export MU2E_OPS_PYTHONPATH

# Prefer explicit interpreter, then local venv, then python3.
if [[ -n "${MCP_PYTHON:-}" ]]; then
  PYTHON_BIN="$MCP_PYTHON"
elif [[ -x .venv/bin/python ]]; then
  PYTHON_BIN=".venv/bin/python"
elif [[ -x venv/bin/python ]]; then
  PYTHON_BIN="venv/bin/python"
else
  PYTHON_BIN="python3"
fi

# Build venv site-packages path (if available), then append ops path.
VENV_SITE="$($PYTHON_BIN - <<'PY'
import site
paths = [p for p in site.getsitepackages() if 'site-packages' in p]
print(paths[0] if paths else '')
PY
)"

if [[ -n "$VENV_SITE" && -n "$MU2E_OPS_PYTHONPATH" ]]; then
  export PYTHONPATH="$VENV_SITE:$MU2E_OPS_PYTHONPATH"
elif [[ -n "$VENV_SITE" ]]; then
  export PYTHONPATH="$VENV_SITE"
else
  export PYTHONPATH="$MU2E_OPS_PYTHONPATH"
fi

# One-time startup compatibility check.
if [[ "${1:-}" == "--check" ]]; then
  "$PYTHON_BIN" - <<'PY'
import importlib

importlib.import_module("mcp.server.fastmcp")
importlib.import_module("metacat.webapi")

from metacat.webapi import MetaCatClient
client = MetaCatClient()
print("OK: imported mcp + metacat, server URL:", client.ServerURL)
PY
  exit 0
fi

exec "$PYTHON_BIN" -m metacat_mcp.server
