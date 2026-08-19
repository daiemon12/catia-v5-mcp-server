"""Live MCP smoke test for a solid slinky built from explicit guide points."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
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


def slinky_points(
    radius: float = 25.0,
    pitch: float = 8.0,
    turns: int = 3,
    samples_per_turn: int = 16,
) -> list[list[float]]:
    return [
        [
            radius * math.cos(2.0 * math.pi * index / samples_per_turn),
            radius * math.sin(2.0 * math.pi * index / samples_per_turn),
            pitch * index / samples_per_turn,
        ]
        for index in range(turns * samples_per_turn + 1)
    ]


def assert_slinky_result(output: str, point_count: int, wire_radius: float) -> None:
    result = json.loads(output)
    expected_names = {
        "feature": "Smoke_Slinky_Solid",
        "guide": "Smoke_Slinky_Guide",
        "surface": "Smoke_Slinky_Surface",
    }
    if result.get("tool") != "catia_build_slinky_from_points":
        raise RuntimeError(f"Unexpected tool result: {result}")
    if result.get("points") != point_count or result.get("wire_radius") != wire_radius:
        raise RuntimeError(f"Unexpected slinky dimensions: {result}")
    for key, expected_name in expected_names.items():
        if result.get(key, {}).get("name") != expected_name:
            raise RuntimeError(f"Unexpected {key} result: {result}")


async def smoke(uri: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    points = slinky_points()
    wire_radius = 2.0
    async with httpx.AsyncClient(headers=headers, timeout=60.0) as client:
        async with streamable_http_client(uri, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                if not any(tool.name == "catia_build_slinky_from_points" for tool in tools.tools):
                    raise RuntimeError(
                        "The live server does not publish catia_build_slinky_from_points"
                    )

                await call(session, "catia_new_part", {})
                try:
                    output = await call(
                        session,
                        "catia_build_slinky_from_points",
                        {
                            "points": points,
                            "wire_radius": wire_radius,
                            "geoset": "Smoke_Slinky_Construction",
                            "guide_name": "Smoke_Slinky_Guide",
                            "profile_name": "Smoke_Slinky_Profile",
                            "surface_name": "Smoke_Slinky_Surface",
                            "solid_name": "Smoke_Slinky_Solid",
                        },
                    )
                    assert_slinky_result(output, len(points), wire_radius)
                    print(f"slinky_solid: PASS\n{output}")
                finally:
                    await call(session, "catia_close_document", {"save": False})

                print("documents_after_smoke:")
                print(await call(session, "catia_list_documents", {}))


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
