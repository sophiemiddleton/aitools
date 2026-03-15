#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

set +u
# Temporary guard for current CVMFS setup script behavior under set -e.
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

# Use nocache endpoint by default for DQM reads.
export DQM_QE_BASE_URL="${DQM_QE_BASE_URL:-https://dbdata0vm.fnal.gov:9443/QE/mu2e/prod/app/SQ/query?}"
export DQM_QE_DBNAME="${DQM_QE_DBNAME:-mu2e_dqm_prd}"

if [[ -n "${MCP_PYTHON:-}" ]]; then
  PYTHON_BIN="$MCP_PYTHON"
elif [[ -x .venv/bin/python ]]; then
  PYTHON_BIN=".venv/bin/python"
elif [[ -x venv/bin/python ]]; then
  PYTHON_BIN="venv/bin/python"
else
  PYTHON_BIN="python3"
fi

VENV_SITE="$($PYTHON_BIN - <<'PY'
import site
paths = [p for p in site.getsitepackages() if 'site-packages' in p]
print(paths[0] if paths else '')
PY
)"

MU2E_OPS_PYTHONPATH="${PYTHONPATH:-}"
export MU2E_OPS_PYTHONPATH

if [[ -n "$VENV_SITE" && -n "$MU2E_OPS_PYTHONPATH" ]]; then
  export PYTHONPATH="$VENV_SITE:$MU2E_OPS_PYTHONPATH"
elif [[ -n "$VENV_SITE" ]]; then
  export PYTHONPATH="$VENV_SITE"
else
  export PYTHONPATH="$MU2E_OPS_PYTHONPATH"
fi

if [[ "${1:-}" == "--check" ]]; then
  "$PYTHON_BIN" - <<'PY'
import importlib

importlib.import_module("mcp.server.fastmcp")
importlib.import_module("requests")
importlib.import_module("dqm_mcp.server")
print("OK: imported mcp + requests + dqm_mcp.server")
PY
  exit 0
fi

exec "$PYTHON_BIN" -m dqm_mcp.server
