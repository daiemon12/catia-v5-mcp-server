"""Live MCP smoke test for repeatable CATIA viewer close-up zoom."""

from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def read_credentials(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([^#][^=:]*?)\s*[:=]\s*(.*)$", stripped)
        if match:
            values[match.group(1).strip()] = match.group(2).strip()
    return values


async def call(session: ClientSession, name: str, arguments: dict[str, Any]) -> str:
    response = await session.call_tool(name, arguments)
    text = "\n".join(item.text for item in response.content if hasattr(item, "text"))
    if text.startswith(f"Error in {name}:"):
        raise RuntimeError(text)
    return text


async def smoke(uri: str, token: str, file_path: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        async with streamable_http_client(uri, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await call(session, "catia_new_part", {})
                try:
                    await call(session, "catia_create_sketch", {"plane": "xy"})
                    await call(
                        session,
                        "catia_sketch_rectangle",
                        {"x1": -20.0, "y1": -15.0, "x2": 20.0, "y2": 15.0},
                    )
                    await call(session, "catia_close_sketch", {})
                    await call(session, "catia_pad", {"height": 30.0})
                    await call(session, "catia_set_view", {"view": "front"})
                    await call(session, "catia_fit_all", {})
                    zoom = await call(
                        session, "catia_zoom_view", {"direction": "in", "steps": 3}
                    )
                    screenshot = await call(session, "catia_screenshot", {"file_path": file_path})
                    if zoom != "View zoomed in by 3 steps":
                        raise RuntimeError(f"Unexpected zoom response: {zoom}")
                    print("zoom_view: PASS")
                    print(zoom)
                    print(screenshot)
                finally:
                    await call(session, "catia_close_document", {"save": False})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--credential-file",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "192.168.5.42-creds",
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--file-path",
        default=r"C:\Users\sup02\Documents\CATIA_MCP_Zoom_Smoke.jpg",
    )
    args = parser.parse_args()

    credentials = read_credentials(args.credential_file)
    host = credentials.get("Deploy_host", "192.168.5.42")
    token = credentials.get("MCP_TOKEN")
    if not token:
        raise RuntimeError(f"MCP_TOKEN is missing from {args.credential_file}")
    asyncio.run(smoke(f"http://{host}:{args.port}/mcp/", token, args.file_path))


if __name__ == "__main__":
    main()
