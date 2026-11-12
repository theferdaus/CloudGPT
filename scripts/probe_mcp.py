#!/usr/bin/env python3
"""Read-only MCP protocol probes; retain status and tool names, never account data."""
import asyncio
import json
import os
from pathlib import Path
from audit import write_private

ROOT = Path(__file__).resolve().parents[1]


async def probe(name, command, read_tool=None):
    env = dict(os.environ)
    env.setdefault("NODE_USE_ENV_PROXY", "1")
    process = await asyncio.create_subprocess_exec(*map(str, command), stdout=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.DEVNULL, env=env, cwd=ROOT)

    async def request(identifier, method, params):
        process.stdin.write((json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}) + "\n").encode())
        await process.stdin.drain()
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), 45)
            if not line:
                raise RuntimeError("server_closed_protocol_stream")
            try:
                response = json.loads(line)
            except ValueError:
                continue
            if response.get("id") == identifier:
                return response

    result = {"server": name, "credential_values_exported": False, "account_data_exported": False}
    try:
        init = await request(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "cloudgpt-parity-probe", "version": "1.0"}})
        if "error" in init:
            raise RuntimeError("initialize_failed")
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await process.stdin.drain()
        listing = await request(2, "tools/list", {})
        if "error" in listing:
            raise RuntimeError("tools_list_failed")
        tools = listing.get("result", {}).get("tools", [])
        result.update({"protocol": "initialized", "tool_count": len(tools), "tool_names": [x["name"] for x in tools]})
        if read_tool and read_tool in result["tool_names"]:
            response = await request(3, "tools/call", {"name": read_tool, "arguments": {}})
            body = response.get("result", {})
            raw = json.dumps(body).casefold()
            # Some servers return an error JSON as ordinary text without isError.
            nested_error = '"error"' in raw.replace('\\"', '"') or '"status": "error"' in raw.replace('\\"', '"')
            failed = "error" in response or body.get("isError", False) or nested_error
            auth_error = any(w in raw for w in ["not authenticated", "no authentication", "notebooklm-mcp-auth", "login required", "no api key", "no authentication cookies"])
            result["read_probe"] = {"tool": read_tool, "status": "login_required" if auth_error else "failed" if failed else "passed"}
        return result
    except Exception as exc:
        result.update({"protocol": "failed", "error_type": type(exc).__name__})
        return result
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.kill()
                await process.wait()


async def main():
    results = await asyncio.gather(
        probe("wavespeed", ["node", ROOT / "runtimes/media/node_modules/@wavespeed/mcp/dist/index.js"], "get_balance"),
        probe("notebooklm", [ROOT / "runtimes/python/.venv/bin/notebooklm-mcp"], "notebook_list"),
    )
    write_private(ROOT / "reports/portable-mcp-verification.json", results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
