#!/usr/bin/env python3
import argparse
import json
import select
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "scripts" / "start_mcp.sh"


def send_line(proc: subprocess.Popen, payload: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def read_line(proc: subprocess.Popen, timeout: float = 30.0) -> dict:
    assert proc.stdout is not None
    end = time.time() + timeout
    while time.time() < end:
        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
        if not ready:
            continue

        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("Server closed stdout")

        text = line.strip()
        if not text:
            continue

        return json.loads(text)

    raise TimeoutError("Timed out waiting for JSON line response")


def rpc(proc: subprocess.Popen, req_id: int, method: str, params: dict) -> dict:
    send_line(
        proc,
        {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
    )
    return read_line(proc)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke-test code-index-mcp over stdio")
    p.add_argument(
        "--project-path",
        required=True,
        help="Absolute path to an existing repository for set_project_path",
    )
    p.add_argument(
        "--build-deep-index",
        action="store_true",
        help="Also call build_deep_index (can take longer)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    project_path = str(Path(args.project_path).resolve())

    if not Path(project_path).exists():
        print(f"FAIL project path does not exist: {project_path}")
        return 2

    proc = subprocess.Popen(
        [str(LAUNCHER)],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        init_resp = rpc(
            proc,
            1,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "local-smoke", "version": "0.1"},
            },
        )
        if "result" not in init_resp:
            print("FAIL initialize response missing result")
            print(json.dumps(init_resp, indent=2))
            return 1
        print("INIT_OK")

        send_line(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        tools_resp = rpc(proc, 2, "tools/list", {})
        tools = tools_resp.get("result", {}).get("tools", [])
        if not isinstance(tools, list):
            print("FAIL tools/list malformed response")
            print(json.dumps(tools_resp, indent=2))
            return 1

        tool_names = {t.get("name") for t in tools}
        print(f"TOOLS_OK {len(tools)}")

        required = {"set_project_path", "find_files", "search_code_advanced"}
        missing = sorted(x for x in required if x not in tool_names)
        if missing:
            print("FAIL required tools missing:", ", ".join(missing))
            return 1

        set_resp = rpc(
            proc,
            3,
            "tools/call",
            {"name": "set_project_path", "arguments": {"path": project_path}},
        )
        if "result" not in set_resp:
            print("FAIL set_project_path")
            print(json.dumps(set_resp, indent=2))
            return 1
        print("SET_PROJECT_PATH_OK")

        find_resp = rpc(
            proc,
            4,
            "tools/call",
            {"name": "find_files", "arguments": {"pattern": "**/*.py"}},
        )
        if "result" not in find_resp:
            print("FAIL find_files")
            print(json.dumps(find_resp, indent=2))
            return 1
        print("FIND_FILES_OK")

        if args.build_deep_index:
            deep_resp = rpc(
                proc,
                5,
                "tools/call",
                {"name": "build_deep_index", "arguments": {}},
            )
            if "result" not in deep_resp:
                print("FAIL build_deep_index")
                print(json.dumps(deep_resp, indent=2))
                return 1
            print("BUILD_DEEP_INDEX_OK")

        print("SMOKE_OK")
        return 0

    except Exception as exc:
        print(f"SMOKE_FAIL {exc!r}")
        if proc.stderr is not None:
            err = proc.stderr.read()
            if err:
                print("STDERR:")
                print(err)
        return 1

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
