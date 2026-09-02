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


MARKER = "SEARCH_AGENT_FETCH_OK"


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


def require_playwright_chromium() -> None:
    browser_root = Path(
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/root/.cache/ms-playwright")
    )
    candidates = browser_root.glob("chromium-*/chrome-linux*/chrome")
    if not any(os.access(candidate, os.X_OK) for candidate in candidates):
        raise RuntimeError(f"Playwright Chromium executable missing under {browser_root}")


def server_parameters(name: str) -> StdioServerParameters:
    config_path = Path("/root/.acode/config.toml")
    with config_path.open("rb") as config_file:
        server = tomllib.load(config_file)["mcp_servers"][name]
    environment = os.environ.copy()
    environment.update(server.get("env", {}))
    return StdioServerParameters(
        command=server["command"],
        args=server.get("args", []),
        env=environment,
    )


async def require_tool(name: str, expected_tool: str) -> None:
    parameters = server_parameters(name)
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
    tool_names = {tool.name for tool in tools.tools}
    if expected_tool not in tool_names:
        raise RuntimeError(
            f"{name} MCP did not expose {expected_tool!r}: {sorted(tool_names)}"
        )


def contains_marker(value: Any) -> bool:
    if isinstance(value, str):
        return MARKER in value.replace("\\_", "_")
    if isinstance(value, dict):
        return any(contains_marker(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_marker(item) for item in value)
    return False


async def verify_fetch(url: str) -> None:
    parameters = server_parameters("scrapling")
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            if "fetch" not in tool_names:
                raise RuntimeError(
                    f"Scrapling MCP did not expose 'fetch': {sorted(tool_names)}"
                )
            result = await session.call_tool("fetch", {
                "url": url,
                "extraction_type": "markdown",
                "main_content_only": False,
            })
    if getattr(result, "isError", False):
        raise RuntimeError(f"Scrapling fetch returned an error: {result}")
    result_data = result.model_dump(mode="json")
    if not contains_marker(result_data):
        raise RuntimeError(
            "Scrapling fetch response did not contain smoke marker: "
            f"{result_data}"
        )


async def verify_search_agent(url: str) -> None:
    await require_tool("web-search", "web-search")
    await verify_fetch(url)


def main() -> None:
    require_playwright_chromium()
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        asyncio.run(
            asyncio.wait_for(
                verify_search_agent(f"http://{host}:{port}/"),
                180,
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    print(MARKER)


if __name__ == "__main__":
    main()
