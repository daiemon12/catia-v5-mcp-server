"""Live MCP smoke test for PLAN.md item 14 solver semantics."""

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
    text = "\n".join(item.text for item in response.content if hasattr(item, "text"))
    if text.startswith(f"Error in {name}:"):
        raise RuntimeError(text)
    return text


async def make_pad(session: ClientSession) -> None:
    await call(session, "catia_create_sketch", {"plane": "xy"})
    await call(
        session,
        "catia_sketch_rectangle",
        {"x1": -20.0, "y1": -15.0, "x2": 20.0, "y2": 15.0},
    )
    await call(session, "catia_close_sketch", {})
    await call(session, "catia_pad", {"height": 30.0})


def vertical_edge(edges: list[dict[str, Any]]) -> dict[str, Any]:
    matches = []
    for edge in edges:
        start = edge.get("start_mm", [])
        end = edge.get("end_mm", [])
        if len(start) != 3 or len(end) != 3:
            continue
        vector = [float(end[index]) - float(start[index]) for index in range(3)]
        length = math.sqrt(sum(value * value for value in vector))
        if length > 0 and abs(vector[2]) / length > 0.99:
            matches.append(edge)
    if not matches:
        return max(edges, key=lambda edge: float(edge.get("length_mm", 0.0)))
    return max(matches, key=lambda edge: float(edge.get("length_mm", 0.0)))


def draft_faces(faces: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    neutral_candidates = [
        face
        for face in faces
        if face.get("planar")
        and len(face.get("normal", [])) == 3
        and abs(float(face["normal"][2])) > 0.99
    ]
    side_candidates = [
        face
        for face in faces
        if face.get("planar")
        and len(face.get("normal", [])) == 3
        and abs(float(face["normal"][2])) < 0.01
    ]
    if not neutral_candidates:
        neutral_candidates = [
            face for face in faces if "Sketch." not in str(face.get("brep_name", ""))
        ]
    if not side_candidates:
        side_candidates = [
            face for face in faces if "Sketch." in str(face.get("brep_name", ""))
        ]
    if not neutral_candidates or not side_candidates:
        raise RuntimeError("Smoke pad does not expose the expected planar bottom/side faces")
    neutral = min(
        neutral_candidates,
        key=lambda face: float(face.get("origin_mm", [0.0, 0.0, 0.0])[2]),
    )
    return neutral, side_candidates[0]


async def smoke(uri: str, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        async with streamable_http_client(uri, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                await call(session, "catia_new_part", {})
                try:
                    await make_pad(session)
                    edges = json.loads(
                        await call(session, "catia_list_edges_geometry", {"feature": "Pad.1"})
                    )
                    edge = vertical_edge(edges)
                    result = await call(
                        session,
                        "catia_variable_fillet",
                        {
                            "edge": {"feature": "Pad.1", "kind": "edge", "index": edge["index"]},
                            "radius": 3.0,
                            "variations": [
                                {"position": 0.25, "radius": 2.0},
                                {"position": 0.75, "radius": 5.0},
                            ],
                            "name": "Item14_VariableFillet_Smoke",
                        },
                    )
                    print(f"variable_fillet: PASS\n{result}")
                finally:
                    await call(session, "catia_close_document", {"save": False})

                await call(session, "catia_new_part", {})
                try:
                    await make_pad(session)
                    faces = json.loads(
                        await call(session, "catia_list_faces", {"feature": "Pad.1"})
                    )
                    neutral, side = draft_faces(faces)
                    result = await call(
                        session,
                        "catia_advanced_draft",
                        {
                            "faces": [
                                {"feature": "Pad.1", "kind": "face", "index": side["index"]}
                            ],
                            "neutral": {
                                "feature": "Pad.1",
                                "kind": "face",
                                "index": neutral["index"],
                            },
                            "pull_direction": "xy",
                            "angle": 5.0,
                            "name": "Item14_AdvancedDraft_Smoke",
                        },
                    )
                    print(f"advanced_draft: PASS\n{result}")
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
