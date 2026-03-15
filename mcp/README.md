# Mu2e MCP Workspace (AI-facing)

This directory contains MCP server source projects only.

## Goals

- Keep MCP source under git in one place.
- Keep runtime/deployed artifacts out of git.
- Install each MCP independently (different schedules, dependencies, and ownership windows).
- Keep one per-MCP registry plus an optional combined registry for clients like Cline.

## Directory structure

- `metacat/`
  - Source for the read-only metacat MCP server.
  - Own install script: `metacat/scripts/install.sh`
  - Own registry output target (in shared deploy tree):
    - `<deploy-root>/metacat/registry/mcp-servers.json`
- `sim-epochs/`
  - Source for the sim-epochs MCP server.
  - Own install script: `sim-epochs/scripts/install.sh`
  - Own registry output target (in shared deploy tree):
    - `<deploy-root>/sim-epochs/registry/mcp-servers.json`
- `dqm/`
  - Source for the DQM Query Engine read-only MCP server.
  - Own install script: `dqm/scripts/install.sh`
  - Own registry output target (in shared deploy tree):
    - `<deploy-root>/dqm/registry/mcp-servers.json`
- `scripts/`
  - Cross-MCP helper scripts.
  - `write_joint_registry.sh` creates one registry with all MCP servers.
  - `install_user_mcp_config.sh` links or copies a user-local MCP config to the joint registry.
- `.gitignore`
  - Excludes virtual environments and runtime artifacts (`.venv`, `venv`, caches, local deploy sandbox).

## Shared deploy layout (outside git, group account)

Recommended target root example:

- `/exp/mu2e/app/users/mu2epro/mcp/deploy`

Installed MCP subtrees:

- `/exp/mu2e/app/users/mu2epro/mcp/deploy/metacat`
- `/exp/mu2e/app/users/mu2epro/mcp/deploy/sim-epochs`
- `/exp/mu2e/app/users/mu2epro/mcp/deploy/dqm`

Each subtree follows:

- `releases/<version>/`
- `current` (symlink)
- `registry/mcp-servers.json`
- optional `catalog/` (sim-epochs)

## Install flow

1. Install sim-epochs (as `mu2epro`):
  - `sim-epochs/scripts/install.sh /exp/mu2e/app/users/mu2epro/mcp/deploy/sim-epochs <version> [catalog] [group]`
2. Install metacat (as `mu2epro`):
  - `metacat/scripts/install.sh /exp/mu2e/app/users/mu2epro/mcp/deploy/metacat <version> [group]`
3. Install dqm (as `mu2epro`):
  - `dqm/scripts/install.sh /exp/mu2e/app/users/mu2epro/mcp/deploy/dqm <version> [group]`
4. Generate combined registry:
   - `scripts/write_joint_registry.sh /exp/mu2e/app/users/mu2epro/mcp/deploy`
5. Point a user config at the joint registry:
  - `scripts/install_user_mcp_config.sh /exp/mu2e/app/users/mu2epro/mcp/deploy/registry/mcp-servers.json ~/.config/llm-harness/mcp.json link`

Default combined registry output:

- `/exp/mu2e/app/users/mu2epro/mcp/deploy/registry/mcp-servers.json`

## Dependency policy

- Do not commit virtual environments.
- Each MCP keeps a `requirements.txt` for dependency bootstrap in install scripts.
- Install scripts create a fresh `venv` in the release directory and run pip there.

## AI guidance

- Treat this directory as source-of-truth for MCP code.
- Do not write runtime data or deploy trees inside git paths.
- Preserve per-MCP install independence.
- Keep tool names stable once published; avoid silent renames.
