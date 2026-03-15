#!/usr/bin/env python3
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


def read_line(proc: subprocess.Popen, timeout: float = 20.0) -> dict:
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


def main() -> int:
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
        send_line(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "local-smoke", "version": "0.1"},
                },
            },
        )
        init_resp = read_line(proc)
        if "result" not in init_resp:
            print("FAIL initialize response missing result")
            print(json.dumps(init_resp, indent=2))
            return 1
        print("INIT_OK")

        send_line(
            proc,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )

        send_line(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools_resp = read_line(proc)
        tools = tools_resp.get("result", {}).get("tools", [])

        if not isinstance(tools, list):
            print("FAIL tools/list malformed response")
            print(json.dumps(tools_resp, indent=2))
            return 1

        print(f"TOOLS_OK {len(tools)}")
        for tool in tools:
            print(f"- {tool.get('name', '<unnamed>')}")

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
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
