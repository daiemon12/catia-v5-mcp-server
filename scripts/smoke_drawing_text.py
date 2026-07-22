"""Live MCP smoke test for CATDrawing text annotations."""

from __future__ import annotations

import argparse
import asyncio
import json
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
    output = "\n".join(item.text for item in response.content if hasattr(item, "text"))
    if output.startswith(f"Error in {name}:"):
        raise RuntimeError(output)
    return output


async def smoke(uri: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        async with streamable_http_client(uri, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                if not any(tool.name == "catia_drawing_add_text" for tool in tools.tools):
                    raise RuntimeError("The live server does not publish catia_drawing_add_text")

                await call(session, "catia_new_drawing", {"paper_size": "A4"})
                try:
                    created = await call(
                        session,
                        "catia_drawing_add_text",
                        {"view": "Background View", "text": "MCP TEXT SMOKE", "x": 35, "y": 25,
                         "name": "SmokeNote"},
                    )
                    payload = json.loads(created)
                    if payload.get("tool") != "catia_drawing_add_text":
                        raise RuntimeError(f"Unexpected tool result: {payload}")
                    if payload.get("view") != "Background View" or payload.get("text") != "MCP TEXT SMOKE":
                        raise RuntimeError(f"Unexpected text result: {payload}")

                    info = json.loads(await call(session, "catia_drawing_info", {}))
                    texts = [
                        text
                        for sheet in info["sheets"]
                        for view in sheet["views"]
                        for text in view["texts"]
                    ]
                    if not any(
                        text.get("name") == "SmokeNote" and text.get("text") == "MCP TEXT SMOKE"
                        for text in texts
                    ):
                        raise RuntimeError(f"Drawing text is absent from diagnostics: {info}")
                    print(f"drawing_text: PASS\n{created}")
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
    args = parser.parse_args()

    credentials = read_credentials(args.credential_file)
    host = credentials.get("Deploy_host", "192.168.5.42")
    token = credentials.get("MCP_TOKEN")
    if not token:
        raise RuntimeError(f"MCP_TOKEN is missing from {args.credential_file}")
    asyncio.run(smoke(f"http://{host}:{args.port}/mcp/", token))


if __name__ == "__main__":
    main()
