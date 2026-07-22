"""Live MCP smoke test for CATDrawing dimension generation."""

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


TOOL_NAME = "catia_drawing_generate_dimensions"


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


async def make_constrained_part(session: ClientSession) -> None:
    await call(session, "catia_create_sketch", {"plane": "xy"})
    await call(session, "catia_sketch_circle", {"cx": 0.0, "cy": 0.0, "radius": 20.0})
    geometry = json.loads(await call(session, "catia_sketch_get_geometry", {}))
    circle = next(
        (item for item in reversed(geometry) if "circle" in item["name"].lower()),
        None,
    )
    if circle is None:
        raise RuntimeError(f"The smoke sketch did not contain the created circle: {geometry}")
    await call(
        session,
        "catia_sketch_constraint",
        {"type": "radius", "geometry_index_1": circle["index"], "value": 20.0},
    )
    await call(session, "catia_close_sketch", {})
    await call(session, "catia_pad", {"height": 30.0})


async def smoke(uri: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        async with streamable_http_client(uri, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                if not any(tool.name == TOOL_NAME for tool in tools.tools):
                    raise RuntimeError(f"The live server does not publish {TOOL_NAME}")

                source_part_created = False
                drawing_created = False
                try:
                    await call(session, "catia_new_part", {})
                    source_part_created = True
                    await make_constrained_part(session)
                    await call(
                        session,
                        "catia_drawing_from_part",
                        {"part_name": "active", "paper_size": "A4", "view_scale": 0.5},
                    )
                    drawing_created = True
                    generated = json.loads(await call(session, TOOL_NAME, {}))
                    if generated.get("tool") != TOOL_NAME:
                        raise RuntimeError(f"Unexpected tool result: {generated}")
                    for field in ("before", "after", "generated_by_view", "generated_total"):
                        if field not in generated:
                            raise RuntimeError(f"Missing {field} in result: {generated}")
                    if generated["generated_total"] <= 0:
                        raise RuntimeError(
                            "CATIA generated no dimensions from the constrained source part: "
                            f"{generated}"
                        )

                    info = json.loads(await call(session, "catia_drawing_info", {}))
                    views = [view for sheet in info["sheets"] for view in sheet["views"]]
                    if not views or any("dimensions" not in view for view in views):
                        raise RuntimeError(f"Dimension diagnostics are incomplete: {info}")
                    if not any(view["dimensions"] for view in views):
                        raise RuntimeError(f"No generated dimensions in drawing diagnostics: {info}")
                    print(f"drawing_dimensions: PASS\n{json.dumps(generated, ensure_ascii=False)}")
                finally:
                    if drawing_created:
                        await call(session, "catia_close_document", {"save": False})
                    if source_part_created:
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
