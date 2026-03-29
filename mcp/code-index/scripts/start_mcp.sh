#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$script_dir/.." && pwd)"

# Use the release venv dependencies deterministically. Inherited shell
# PYTHONPATH (for example from Mu2e/CVMFS setups) can shadow required wheels.
unset PYTHONPATH
export PYTHONNOUSERSITE=1

if [[ -n "${MCP_PYTHON:-}" ]]; then
  PYTHON_BIN="$MCP_PYTHON"
elif [[ -x "$root/venv/bin/python" ]]; then
  PYTHON_BIN="$root/venv/bin/python"
else
  PYTHON_BIN="python3"
fi

if [[ -x "$root/venv/bin/code-index-mcp" ]]; then
  CODE_INDEX_BIN="$root/venv/bin/code-index-mcp"
else
  CODE_INDEX_BIN=""
fi

args=()
if [[ -n "${MCP_PROJECT_PATH:-}" ]]; then
  args+=(--project-path "$MCP_PROJECT_PATH")
fi
if [[ -n "${MCP_INDEXER_PATH:-}" ]]; then
  shared_indexer="$MCP_INDEXER_PATH"
  effective_indexer="$shared_indexer"
  shared_probe_dir="$shared_indexer/code_indexer"

  # For central shared deploys, most users cannot write to the deploy index dir.
  # Fall back to a user-writable cache path and seed it from shared indexes.
  if ! mkdir -p "$shared_probe_dir" 2>/dev/null || ! test -w "$shared_probe_dir"; then
    user_cache_root="${XDG_CACHE_HOME:-${HOME:-/tmp}/.cache}"
    effective_indexer="${MCP_USER_INDEXER_PATH:-$user_cache_root/mu2e-code-index/indexer}"
    mkdir -p "$effective_indexer"

    if [[ -d "$shared_probe_dir" ]]; then
      cache_code_indexer="$effective_indexer/code_indexer"
      mkdir -p "$cache_code_indexer"

      # Keep user cache in sync with shared hash directories. Copy only when
      # missing or older so user-local indexes are not clobbered unnecessarily.
      for shared_hash_dir in "$shared_probe_dir"/*; do
        [[ -d "$shared_hash_dir" ]] || continue
        hash_name="$(basename "$shared_hash_dir")"
        cache_hash_dir="$cache_code_indexer/$hash_name"
        mkdir -p "$cache_hash_dir"

        for rel in index.db index.shallow.json; do
          shared_file="$shared_hash_dir/$rel"
          cache_file="$cache_hash_dir/$rel"
          [[ -f "$shared_file" ]] || continue

          if [[ ! -f "$cache_file" ]] || [[ "$shared_file" -nt "$cache_file" ]]; then
            cp -p "$shared_file" "$cache_file" 2>/dev/null || true
          fi
        done
      done
    fi
  else
    mkdir -p "$effective_indexer"
  fi

  # Upstream index managers derive storage from tempfile.gettempdir(), so pin
  # temp vars to the selected index root for deterministic persistence.
  export TMPDIR="$effective_indexer"
  export TMP="$effective_indexer"
  export TEMP="$effective_indexer"
  args+=(--indexer-path "$effective_indexer")
fi

if [[ -n "$CODE_INDEX_BIN" ]]; then
  exec "$CODE_INDEX_BIN" "${args[@]}" "$@"
else
  # Fallback path if console script name changes
  exec "$PYTHON_BIN" -m code_index_mcp "${args[@]}" "$@"
fi
