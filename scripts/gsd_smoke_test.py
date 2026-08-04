"""Runtime smoke test for the GSD (Generative Shape Design) tool module.

Requires Windows with CATIA V5 installed and licensed. Drives a running
CATIA instance (or launches one) through the same GSDTools.execute()
dispatch path the MCP server uses, exercising every GSD tool once in a
fresh Part document.

Usage (from repo root, with a Python that has pywin32):
    python scripts/gsd_smoke_test.py

Outputs a PASS/FAIL line per tool, saves the part and a screenshot next
to the repo, and exits non-zero if any step failed.
"""

from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from catia_mcp.connection import CATIAConnection  # noqa: E402
from catia_mcp.tools.export import ExportTools  # noqa: E402
from catia_mcp.tools.gsd import GSDTools  # noqa: E402

OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

results: list[tuple[str, str, str]] = []  # (status, label, message)


def step(label: str, fn) -> bool:
    try:
        msg = fn()
        results.append(("PASS", label, str(msg)[:120]))
        print(f"  PASS  {label}")
        return True
    except Exception as e:
        results.append(("FAIL", label, f"{type(e).__name__}: {e}"))
        print(f"  FAIL  {label}: {e}")
        return False


def main() -> int:
    conn = CATIAConnection()
    print(conn.connect())

    gsd = GSDTools(conn)
    export = ExportTools(conn)

    # Fresh Part document so the test never touches user data
    conn.documents.Add("Part")
    print(f"Test document: {conn.active_document.Name}")

    run = gsd.execute  # shorthand: same dispatch path as the MCP server

    # ── Geoset management ──
    step("create_geoset", lambda: run("catia_gsd_create_geoset", {"name": "GSD_Smoke"}))
    step("set_active_geoset", lambda: run("catia_gsd_set_active_geoset", {"name": "GSD_Smoke"}))

    # ── Wireframe ──
    step("point", lambda: run("catia_gsd_point", {"x": 0, "y": 0, "z": 0, "name": "P0"}))
    step("line", lambda: run("catia_gsd_line", {
        "point1": [60, 0, 0], "point2": [90, 0, 0], "name": "LN1"}))
    step("plane_offset (40)", lambda: run("catia_gsd_plane_offset", {
        "base_plane": "xy", "offset": 40, "name": "Pl40"}))
    step("plane_offset (80)", lambda: run("catia_gsd_plane_offset", {
        "base_plane": "xy", "offset": 80, "name": "Pl80"}))
    step("plane_3points", lambda: run("catia_gsd_plane_3points", {
        "point1": [100, 0, 0], "point2": [100, 50, 0], "point3": [100, 0, 50],
        "name": "Pl3P"}))
    step("spline", lambda: run("catia_gsd_spline", {
        "points": [[60, 0, 0], [70, 20, 30], [60, 0, 60], [80, -10, 90]],
        "name": "SP1"}))
    step("circle C0", lambda: run("catia_gsd_circle", {
        "center": [0, 0, 0], "support_plane": "xy", "radius": 30, "name": "C0"}))
    step("circle C1", lambda: run("catia_gsd_circle", {
        "center": [0, 0, 40], "support_plane": "Pl40", "radius": 18, "name": "C1"}))
    step("circle C2", lambda: run("catia_gsd_circle", {
        "center": [0, 0, 80], "support_plane": "Pl80", "radius": 28, "name": "C2"}))
    step("project", lambda: run("catia_gsd_project", {
        "element": "SP1", "support": "xy", "name": "Proj1"}))

    # ── Surfaces ──
    loft_ok = step("multi_section_surface", lambda: run("catia_gsd_multi_section_surface", {
        "sections": ["C0", "C1", "C2"], "name": "Loft1"}))
    step("sweep", lambda: run("catia_gsd_sweep", {
        "profile": "LN1", "guide": "SP1", "name": "Sweep1"}))
    step("extrude", lambda: run("catia_gsd_extrude", {
        "profile": "C0", "direction": [0, 0, 1], "limit1": 20, "name": "Ext1"}))
    step("revolve", lambda: (
        run("catia_gsd_line", {"point1": [-80, 0, 0], "point2": [-80, 0, 100],
                               "name": "RevAxis"}),
        run("catia_gsd_line", {"point1": [-60, 0, 0], "point2": [-45, 0, 70],
                               "name": "RevProf"}),
        run("catia_gsd_revolve", {"profile": "RevProf", "axis": "RevAxis",
                                  "angle1": 360, "name": "Rev1"}),
    )[-1])
    fill_ok = step("fill (bottom)", lambda: run("catia_gsd_fill", {
        "boundaries": ["C0"], "name": "Fill_Bottom"}))
    step("fill (top)", lambda: run("catia_gsd_fill", {
        "boundaries": ["C2"], "name": "Fill_Top"}))
    step("blend", lambda: run("catia_gsd_blend", {
        "curve1": "C0", "curve2": "C2", "name": "Blend1"}))
    step("offset_surface", lambda: run("catia_gsd_offset_surface", {
        "surface": "Fill_Bottom", "offset": 5, "name": "Off1"}))

    # ── Wireframe on surfaces ──
    if loft_ok:
        step("intersection", lambda: run("catia_gsd_intersection", {
            "element1": "Loft1", "element2": "Pl40", "name": "Int1"}))

    # ── Operations ──
    join_ok = False
    if loft_ok and fill_ok:
        join_ok = step("join", lambda: run("catia_gsd_join", {
            "elements": ["Loft1", "Fill_Bottom", "Fill_Top"], "name": "JoinAll"}))
    if loft_ok:
        step("split", lambda: run("catia_gsd_split", {
            "element": "Loft1", "cutter": "Pl40", "name": "Split1"}))
    step("trim", lambda: (
        run("catia_gsd_line", {"point1": [-50, 0, 0], "point2": [50, 0, 0],
                               "name": "LNX"}),
        run("catia_gsd_extrude", {"profile": "LNX", "direction": [0, 0, 1],
                                  "limit1": 20, "name": "ExtB"}),
        run("catia_gsd_trim", {"element1": "Ext1", "element2": "ExtB",
                               "name": "Trim1"}),
    )[-1])
    step("symmetry", lambda: run("catia_gsd_symmetry", {
        "element": "SP1", "plane": "yz", "name": "Sym1"}))

    # ── Surface → solid bridges ──
    if fill_ok:
        step("thick_surface", lambda: run("catia_gsd_thick_surface", {
            "surface": "Off1", "thickness1": 2}))
    if join_ok:
        step("close_surface", lambda: run("catia_gsd_close_surface", {
            "surface": "JoinAll"}))

    # ── Listing ──
    step("list_elements", lambda: run("catia_gsd_list_elements", {}))

    # ── Screenshot + save for visual inspection ──
    shot_path = os.path.join(OUTPUT_DIR, "gsd_smoke_test.jpg")
    step("screenshot", lambda: (
        export.execute("catia_set_view", {"view": "isometric"}),
        export.execute("catia_fit_all", {}),
        export.execute("catia_screenshot", {"file_path": shot_path}),
    )[-1])

    part_path = os.path.join(OUTPUT_DIR, "GSD_SmokeTest.CATPart")
    n = 2
    while os.path.exists(part_path):
        part_path = os.path.join(OUTPUT_DIR, f"GSD_SmokeTest_{n}.CATPart")
        n += 1
    step("save part", lambda: conn.active_document.SaveAs(part_path) or part_path)

    # ── Summary ──
    failed = [r for r in results if r[0] == "FAIL"]
    print()
    print("=" * 60)
    print(f"GSD smoke test: {len(results) - len(failed)}/{len(results)} passed")
    for status, label, message in failed:
        print(f"  {status}  {label}")
        print(f"        {message}")
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
