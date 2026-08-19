"""Live MCP smoke test for CATDrawing BOM table creation and updates."""

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


def assert_bom_result(output: str, expected: dict[str, int], created: bool) -> None:
    result = json.loads(output)
    if result.get("tool") != "catia_fill_drawing_bom":
        raise RuntimeError(f"Unexpected tool result: {result}")
    if result.get("created") is not created:
        raise RuntimeError(f"Unexpected created state: {result}")
    if result.get("written") != expected:
        raise RuntimeError(f"Unexpected written quantities: {result}")
    context = result.get("context", {})
    if context.get("rows") != len(expected) + 1 or context.get("columns") != 2:
        raise RuntimeError(f"Unexpected BOM table size: {result}")


async def smoke(uri: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    initial = {"Bracket": 2, "Fastener M8": 6}
    revised = {"Bracket": 4, "Fastener M8": 8}
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        async with streamable_http_client(uri, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                if not any(tool.name == "catia_fill_drawing_bom" for tool in tools.tools):
                    raise RuntimeError("The live server does not publish catia_fill_drawing_bom")

                await call(session, "catia_new_drawing", {"paper_size": "A4"})
                try:
                    created = await call(
                        session,
                        "catia_fill_drawing_bom",
                        {
                            "rows": [
                                {"name": name, "quantity": quantity}
                                for name, quantity in initial.items()
                            ],
                            "name_header": "Component",
                            "quantity_header": "Qty",
                            "save": False,
                        },
                    )
                    assert_bom_result(created, initial, created=True)
                    print(f"drawing_bom_create: PASS\n{created}")

                    updated = await call(
                        session,
                        "catia_fill_drawing_bom",
                        {
                            "rows": [
                                {"name": name, "quantity": quantity}
                                for name, quantity in revised.items()
                            ],
                            "create_if_missing": False,
                            "save": False,
                        },
                    )
                    assert_bom_result(updated, revised, created=False)
                    print(f"drawing_bom_update: PASS\n{updated}")
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
