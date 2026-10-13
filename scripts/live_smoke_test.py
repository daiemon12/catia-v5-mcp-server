"""Live smoke test against a running CATIA V5 or CATIA 3DEXPERIENCE session.

Runs the MCP tools in-process (exactly as an MCP client would call them) on a
throw-away part and checks measurable postconditions against known geometry:
a 100 x 60 x 40 mm block must measure 240000 mm3 and a 100/60/40 bounding
box. That check also settles the volume/area unit convention on
3DEXPERIENCE, which offline tests cannot establish.

Nothing is saved unless --save is passed (on 3DEXPERIENCE, saving writes to
the shared 3DSpace database). The part is left open for inspection.

Usage (Windows, CATIA started and, for 3DEXPERIENCE, logged in):
    python scripts/live_smoke_test.py
    python scripts/live_smoke_test.py --drawing --report smoke_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from catia_mcp.server import CATIAMCPServer  # noqa: E402

BLOCK = (100.0, 60.0, 40.0)


class Runner:
    def __init__(self, server: CATIAMCPServer) -> None:
        self.server = server
        self.rows: list[dict[str, Any]] = []

    def call(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        check=None,
        allow_unsupported: bool = False,
    ) -> tuple[bool, str]:
        started = time.perf_counter()
        result = asyncio.run(self.server.call_tool(name, args or {}))
        text = result.content[0].text if result.content else ""
        ok = not result.isError
        note = ""
        code = (result.structuredContent or {}).get("code") if result.isError else None
        if ok and check is not None:
            try:
                note = check(text) or ""
            except AssertionError as e:
                ok, note = False, f"postcondition failed: {e}"
            except Exception as e:
                ok, note = False, f"postcondition error: {e}"
        if ok and text.startswith("FEATURE_NO_EFFECT"):
            ok, note = False, "feature had no effect"
        status = "PASS" if ok else "FAIL"
        if not ok and allow_unsupported and code == "UNSUPPORTED_CAPABILITY":
            status, note = "SKIP", "unsupported on this platform (expected)"
        row = {
            "tool": name,
            "args": args or {},
            "ok": ok,
            "status": status,
            "seconds": round(time.perf_counter() - started, 2),
            "note": note,
            "output": text[:4000],
        }
        if code:
            row["code"] = code
        self.rows.append(row)
        print(f"[{status}] {name} {json.dumps(args or {})[:80]} {note}")
        if status == "FAIL":
            print("       " + text.replace("\n", "\n       ")[:1200])
        return ok, text


def check_volume(text: str) -> str:
    data = json.loads(text)
    volume = data.get("volume_mm3")
    expected = BLOCK[0] * BLOCK[1] * BLOCK[2]
    assert isinstance(volume, (int, float)), f"volume unavailable: {volume}"
    ratio = volume / expected
    assert abs(ratio - 1) < 0.01, (
        f"volume {volume} mm3, expected {expected} (ratio {ratio:g}; 1e-9 or 1e9 "
        "means the unit convention differs on this platform)"
    )
    return f"volume {volume:.1f} mm3 OK"


def check_removed(text: str) -> str:
    assert "Removed" in text, "no material removal reported"
    return "material removed"


def feature_name(text: str, default: str) -> str:
    match = re.search(r"'([^']+)'", text)
    return match.group(1) if match else default


def check_bbox(text: str) -> str:
    dims = json.loads(text)["dimensions"]
    got = sorted([dims["length_x"], dims["length_y"], dims["length_z"]])
    assert all(abs(a - b) < 0.01 for a, b in zip(got, sorted(BLOCK))), f"bbox {got}"
    return f"bbox {got} OK"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--platform", default="auto", help="auto, v5 or 3dx")
    parser.add_argument("--save", action="store_true", help="save the test part at the end")
    parser.add_argument("--drawing", action="store_true", help="also test drafting tools")
    parser.add_argument("--report", default="smoke_report.json", help="JSON report path")
    args = parser.parse_args()

    server = CATIAMCPServer(args.platform)
    run = Runner(server)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    try:
        ok, _ = run.call("catia_connect")
        if not ok:
            return 2
        run.call("catia_diagnose")
        ok, _ = run.call("catia_new_part", {"name": f"MCP_Smoke_{stamp}"})
        if not ok:
            print("Cannot create a part; stopping. See catia_diagnose output above.")
            return 3
        run.call("catia_get_active_document_info")

        # Solid: 100 x 60 x 40 block.
        run.call("catia_create_sketch", {"plane": "xy"})
        run.call("catia_sketch_centered_rectangle", {"width": BLOCK[0], "height": BLOCK[1]})
        run.call("catia_close_sketch")
        run.call("catia_pad", {"height": BLOCK[2]})
        run.call("catia_get_inertia", check=check_volume)
        run.call("catia_get_bounding_box", check=check_bbox)
        run.call("catia_list_faces")
        run.call("catia_list_edges")
        run.call("catia_measure_element", {"element": "Face.1"})
        run.call("catia_measure_distance", {"element1": "Face.1", "element2": "Face.2"})

        # Material removal with volume verification, then a circular
        # pattern of it (before any geometrical set exists: V5 refuses
        # circular patterns in parts holding GSD geometry).
        run.call("catia_create_sketch", {"plane": "xy"})
        run.call("catia_sketch_circle", {"cx": 20, "cy": 0, "radius": 4})
        run.call("catia_close_sketch")
        _, pocket_text = run.call("catia_pocket", {"depth": 20}, check=check_removed)
        pocket = feature_name(pocket_text, "Pocket.1")
        run.call("catia_circ_pattern", {"count": 4, "feature_name": pocket})
        run.call("catia_fillet", {"radius": 2, "edge_name": "Edge.1"})
        run.call("catia_list_features")

        # Bodies and booleans.
        run.call("catia_add_body", {"name": "Boss"})
        run.call("catia_create_sketch", {"plane": "zx"})
        run.call("catia_sketch_circle", {"cx": 30, "cy": 20, "radius": 5})
        run.call("catia_close_sketch")
        run.call("catia_pad", {"height": 10})
        run.call("catia_set_active_body")
        run.call("catia_boolean", {"operation": "add", "body_name": "Boss"})

        # GSD.
        run.call("catia_gsd_create_geoset", {"name": "Smoke_GSD"})
        run.call("catia_gsd_point", {"x": 0, "y": 0, "z": 60, "name": "P1"})
        run.call("catia_gsd_point", {"x": 50, "y": 0, "z": 60, "name": "P2"})
        run.call("catia_gsd_line", {"point1": "P1", "point2": "P2", "name": "L1"})
        run.call("catia_gsd_point_on_curve", {"curve": "L1", "ratio": 0.5, "name": "Mid"})
        run.call("catia_gsd_plane_offset", {"base_plane": "xy", "offset": 70, "name": "Top70"})
        run.call("catia_gsd_list_elements")

        # Knowledgeware.
        run.call("catia_create_parameter", {"name": "SmokeThickness", "type": "length", "value": 5})
        run.call("catia_get_parameters", {"filter": "SmokeThickness"})

        # View, screenshot, export.
        run.call("catia_set_view", {"view": "isometric"})
        run.call("catia_fit_all")
        shot = os.path.join(tempfile.gettempdir(), f"mcp_smoke_{stamp}.jpg")
        run.call("catia_screenshot", {"file_path": shot})
        step = os.path.join(tempfile.gettempdir(), f"mcp_smoke_{stamp}.stp")
        run.call("catia_export", {"file_path": step}, allow_unsupported=True)

        # API discovery.
        run.call("catia_inspect_api", {"path": "part.ShapeFactory", "filter": "AddNewPad"})
        if server.connection.is_3dx:
            run.call("catia_get_plm_attributes")
            run.call("catia_inspect_api", {"path": "editor.GetService(\"MeasurableService\")"})

        if args.drawing:
            part_title = None
            if server.connection.is_3dx:
                info = json.loads(run.call("catia_get_active_document_info")[1])
                part_title = info.get("title")
            run.call("catia_new_drawing")
            view_args = {"plane": "xy"}
            if part_title:
                view_args["part_name"] = part_title
            run.call("catia_drawing_add_view", view_args)
            run.call("catia_drawing_projection_view", {"direction": "right"})
            run.call("catia_drawing_add_text", {"text": "MCP smoke test", "x": 20, "y": 20})
            run.call("catia_drawing_list_views")

        if args.save:
            run.call("catia_save_document")
    finally:
        asyncio.run(server.close())
        failed = [r for r in run.rows if r["status"] == "FAIL"]
        report = {
            "platform": server.connection.platform_label,
            "passed": sum(r["status"] == "PASS" for r in run.rows),
            "skipped": sum(r["status"] == "SKIP" for r in run.rows),
            "failed": len(failed),
            "results": run.rows,
        }
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(
            f"\n{report['passed']} passed, {report['skipped']} skipped, "
            f"{report['failed']} failed. Report: {args.report}"
        )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
