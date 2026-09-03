from __future__ import annotations

import asyncio
import os
import threading
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


CONFIG_PATH = Path("/opt/astroncode/search-agent.config.toml")
EXPECTED_TOOLS = {
    "open_session",
    "close_session",
    "list_sessions",
    "get",
    "fetch",
    "stealthy_fetch",
    "screenshot",
}
MARKER = "SEARCH_AGENT_WEB_FETCH_OK"


class SmokeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = f"<html><main><h1>{MARKER}</h1></main></html>".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def server_parameters() -> StdioServerParameters:
    with CONFIG_PATH.open("rb") as config_file:
        server = tomllib.load(config_file)["mcp_servers"]["web_fetch"]
    environment = os.environ.copy()
    environment.update(server.get("env", {}))
    return StdioServerParameters(
        command=server["command"],
        args=server.get("args", []),
        env=environment,
    )


def contains_marker(value: Any) -> bool:
    if isinstance(value, str):
        return MARKER in value.replace("\\_", "_")
    if isinstance(value, dict):
        return any(contains_marker(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_marker(item) for item in value)
    return False


async def verify_web_fetch(url: str) -> None:
    async with stdio_client(server_parameters()) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            if tool_names != EXPECTED_TOOLS:
                raise RuntimeError(
                    "web_fetch MCP tool inventory mismatch: "
                    f"expected={sorted(EXPECTED_TOOLS)}, actual={sorted(tool_names)}"
                )
            result = await session.call_tool("fetch", {"url": url})
    if getattr(result, "isError", False):
        raise RuntimeError(f"web_fetch returned an error: {result}")
    if not contains_marker(result.model_dump(mode="json")):
        raise RuntimeError("web_fetch response did not contain the smoke marker")


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        asyncio.run(
            asyncio.wait_for(
                verify_web_fetch(f"http://{host}:{port}/"),
                timeout=180,
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    print(MARKER)


if __name__ == "__main__":
    main()
