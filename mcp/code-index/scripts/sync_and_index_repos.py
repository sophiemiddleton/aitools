#!/usr/bin/env python3
import argparse
import json
import os
import select
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RepoSpec:
    raw: str
    clone_url: str
    owner: str
    name: str
    branch: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def directory_name(self) -> str:
        return self.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clone/pull central repos and refresh code-index shallow or deep indexes"
    )
    parser.add_argument("--deploy-root", required=True, help="Deploy code-index root")
    parser.add_argument("--repo-list", required=True, help="File containing repo specs")
    parser.add_argument(
        "--mode",
        choices=("fast", "deep"),
        default="fast",
        help="fast=shallow refresh, deep=full symbol index",
    )
    parser.add_argument(
        "--default-owner",
        default="Mu2e",
        help="GitHub owner/org for bare repo names in the list file",
    )
    parser.add_argument(
        "--default-branch",
        default="main",
        help="Default branch to track when not given in the list file",
    )
    parser.add_argument(
        "--github-base",
        default="https://github.com",
        help="GitHub base URL for owner/repo specs",
    )
    parser.add_argument(
        "--force-deep",
        action="store_true",
        help="Run deep index even when the branch head has not changed",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue processing remaining repos after a failure",
    )
    return parser.parse_args()


def parse_repo_specs(path: Path, default_owner: str, default_branch: str, github_base: str) -> list[RepoSpec]:
    specs: list[RepoSpec] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        repo_token = parts[0]
        branch = parts[1] if len(parts) > 1 else default_branch

        if repo_token.startswith(("https://", "http://", "git@", "file://")) or repo_token.startswith("/"):
            clone_url = repo_token
            repo_name = repo_token.rstrip("/").rsplit("/", 1)[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            if repo_token.startswith("file://"):
                slug = repo_name
            elif repo_token.startswith("/"):
                slug = repo_name
            elif ":" in repo_token and repo_token.startswith("git@"):
                slug = repo_token.split(":", 1)[1]
            else:
                slug = repo_token.rstrip("/").split("github.com/", 1)[-1]
            slug = slug[:-4] if slug.endswith(".git") else slug
            if "/" in slug:
                owner, name = slug.split("/", 1)
            else:
                owner, name = default_owner, repo_name
        else:
            if "/" in repo_token:
                owner, name = repo_token.split("/", 1)
            else:
                owner, name = default_owner, repo_token
            clone_url = f"{github_base.rstrip('/')}/{owner}/{name}.git"

        specs.append(RepoSpec(raw=line, clone_url=clone_url, owner=owner, name=name, branch=branch))
    return specs


def run(cmd: list[str], cwd: Optional[Path] = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def ensure_repo(spec: RepoSpec, repos_root: Path) -> tuple[Path, str]:
    repo_dir = repos_root / spec.directory_name
    if not repo_dir.exists():
        run(["git", "clone", spec.clone_url, str(repo_dir)])

    run(["git", "remote", "set-url", "origin", spec.clone_url], cwd=repo_dir)
    run(["git", "fetch", "origin", spec.branch], cwd=repo_dir)
    run(["git", "checkout", "-B", spec.branch, f"origin/{spec.branch}"], cwd=repo_dir)
    run(["git", "pull", "--ff-only", "origin", spec.branch], cwd=repo_dir)
    head = run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture=True).stdout.strip()
    return repo_dir, head


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"repos": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"repos": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def send_line(proc: subprocess.Popen[str], payload: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def read_line(proc: subprocess.Popen[str], timeout: float = 300.0) -> dict:
    assert proc.stdout is not None
    end = time.time() + timeout
    while time.time() < end:
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if not ready:
            continue
        line = proc.stdout.readline()
        if not line:
            break
        text = line.strip()
        if text:
            return json.loads(text)
    stderr = proc.stderr.read() if proc.stderr is not None else ""
    raise RuntimeError(f"Timed out waiting for MCP response. STDERR: {stderr}")


def rpc(proc: subprocess.Popen[str], req_id: int, method: str, params: dict) -> dict:
    send_line(proc, {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
    return read_line(proc)


def run_index_cycle(start_script: Path, repo_dir: Path, indexer_root: Path, mode: str) -> str:
    env = os.environ.copy()
    env["MCP_PROJECT_PATH"] = str(repo_dir)
    env["MCP_INDEXER_PATH"] = str(indexer_root)
    env.pop("PYTHONPATH", None)

    proc = subprocess.Popen(
        [str(start_script)],
        cwd=str(start_script.parent.parent),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    stderr_text = ""
    try:
        init_resp = rpc(
            proc,
            1,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "central-index-maint", "version": "0.1"},
            },
        )
        if "result" not in init_resp:
            raise RuntimeError(f"initialize failed: {init_resp}")

        send_line(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        set_resp = rpc(proc, 2, "tools/call", {"name": "set_project_path", "arguments": {"path": str(repo_dir)}})
        if "result" not in set_resp:
            raise RuntimeError(f"set_project_path failed: {set_resp}")

        tool_name = "refresh_index" if mode == "fast" else "build_deep_index"
        op_resp = rpc(proc, 3, "tools/call", {"name": tool_name, "arguments": {}})
        if "result" not in op_resp:
            raise RuntimeError(f"{tool_name} failed: {op_resp}")
        return ""
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        if proc.stderr is not None:
            try:
                stderr_text = proc.stderr.read() or ""
            except Exception:
                stderr_text = ""
        if stderr_text:
            return stderr_text


def main() -> int:
    args = parse_args()
    deploy_root = Path(args.deploy_root).resolve()
    repos_root = deploy_root / "repos"
    indexer_root = deploy_root / "indexer"
    current_root = deploy_root / "current"
    start_script = current_root / "scripts" / "start_mcp.sh"
    state_path = deploy_root / "indexer" / "repo-sync-state.json"

    if not start_script.exists():
        print(f"ERROR missing start script: {start_script}", file=sys.stderr)
        return 2

    repos_root.mkdir(parents=True, exist_ok=True)
    indexer_root.mkdir(parents=True, exist_ok=True)

    specs = parse_repo_specs(Path(args.repo_list), args.default_owner, args.default_branch, args.github_base)
    state = load_state(state_path)
    state.setdefault("repos", {})

    failures = 0
    for spec in specs:
        try:
            repo_dir, head = ensure_repo(spec, repos_root)
            repo_state = state["repos"].setdefault(spec.slug, {})
            repo_state["branch"] = spec.branch
            repo_state["path"] = str(repo_dir)
            repo_state["head"] = head

            if args.mode == "fast":
                mcp_stderr = run_index_cycle(start_script, repo_dir, indexer_root, "fast")
                repo_state["last_fast_head"] = head
                repo_state["last_fast_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                print(f"FAST_OK {spec.slug} {head}")
                if mcp_stderr.strip():
                    print(f"MCP_STDERR_BEGIN {spec.slug}")
                    print(mcp_stderr.rstrip())
                    print(f"MCP_STDERR_END {spec.slug}")
            else:
                if not args.force_deep and repo_state.get("last_deep_head") == head:
                    print(f"DEEP_SKIP {spec.slug} {head}")
                else:
                    mcp_stderr = run_index_cycle(start_script, repo_dir, indexer_root, "deep")
                    repo_state["last_deep_head"] = head
                    repo_state["last_deep_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    print(f"DEEP_OK {spec.slug} {head}")
                    if mcp_stderr.strip():
                        print(f"MCP_STDERR_BEGIN {spec.slug}")
                        print(mcp_stderr.rstrip())
                        print(f"MCP_STDERR_END {spec.slug}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {spec.raw}: {exc}", file=sys.stderr)
            if not args.keep_going:
                save_state(state_path, state)
                return 1

    save_state(state_path, state)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())