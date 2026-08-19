"""Live MCP smoke test for hiding wheel construction geometry by default."""

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
    text = "\n".join(item.text for item in response.content if hasattr(item, "text"))
    if text.startswith(f"Error in {name}:"):
        raise RuntimeError(text)
    return text


async def smoke(uri: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=120.0) as client:
        async with streamable_http_client(uri, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                try:
                    report = json.loads(
                        await call(
                            session,
                            "catia_design_wheel",
                            {
                                "rim_diameter": 457.2,
                                "rim_width": 203.2,
                                "offset": 35.0,
                                "pcd": 114.3,
                                "bolt_count": 5,
                                "center_bore": 67.1,
                                "spoke_count": 4,
                                "spoke_style": "simple_lofted",
                                "apply_spoke_fillets": False,
                                "export_step": False,
                                "part_name": "Wheel_Visibility_Smoke",
                            },
                        )
                    )
                    phase = next(
                        (
                            phase
                            for phase in report.get("phases", [])
                            if phase.get("name") == "construction_visibility"
                        ),
                        None,
                    )
                    if report.get("status") != "complete" or not phase or phase.get("status") != "complete":
                        raise RuntimeError(
                            "Wheel build did not confirm hidden Spoke_Construction: "
                            + json.dumps(report, ensure_ascii=False)
                        )
                    print("wheel_visibility: PASS")
                    print(json.dumps(phase, ensure_ascii=False))
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
