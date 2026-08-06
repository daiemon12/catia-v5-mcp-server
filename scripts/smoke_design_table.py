"""Live MCP smoke test for Knowledgeware external design-table associations."""

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


def assert_design_table(output: str, name: str, file_path: str) -> None:
    result = json.loads(output)
    if result.get("name") != name or result.get("file_path") != file_path:
        raise RuntimeError(f"Unexpected design table result: {result}")
    if result.get("parameters") != ["Wheel_Diameter", "Spoke_Count"]:
        raise RuntimeError(f"Unexpected parameter associations: {result}")


async def smoke(uri: str, token: str, file_path: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    name = "Smoke_WheelVariants"
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        async with streamable_http_client(uri, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                if not any(tool.name == "catia_create_design_table" for tool in tools.tools):
                    raise RuntimeError("The live server does not publish catia_create_design_table")

                await call(session, "catia_new_part", {})
                try:
                    await call(
                        session,
                        "catia_create_parameter",
                        {"name": "Wheel_Diameter", "type": "length", "value": 400.0},
                    )
                    await call(
                        session,
                        "catia_create_parameter",
                        {"name": "Spoke_Count", "type": "integer", "value": 5},
                    )
                    output = await call(
                        session,
                        "catia_create_design_table",
                        {
                            "name": name,
                            "file_path": file_path,
                            "parameters": ["Wheel_Diameter", "Spoke_Count"],
                            "copy_mode": True,
                        },
                    )
                    assert_design_table(output, name, file_path)
                    relations = json.loads(
                        await call(session, "catia_list_relations", {"filter": name})
                    )
                    if relations.get("count") != 1 or relations["relations"][0].get("name") != name:
                        raise RuntimeError(f"Design table relation was not found: {relations}")
                    print(f"design_table: PASS\n{output}")
                    print(f"design_table_relation: PASS\n{json.dumps(relations)}")
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
        default=r"C:\Users\sup02\Documents\CATIA_MCP_DesignTable_Smoke.txt",
        help="Existing tab-separated design-table file on the CATIA workstation.",
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
