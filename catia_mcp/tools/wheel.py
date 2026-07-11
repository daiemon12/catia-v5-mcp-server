"""Validated high-level wheel design orchestration."""

from __future__ import annotations

import json
import math
import os
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools._geometry import object_schema
from catia_mcp.tools.knowledge import KnowledgeTools


DEFAULTS = {
    "hub_thickness": 28.0,
    "flange_height": 12.0,
    "rim_thickness": 8.0,
    "spoke_thickness": 16.0,
    "draft_angle": 2.0,
    "fillet_radius": 4.0,
    "valve_hole_diameter": 11.3,
    "lug_hole_diameter": 14.0,
    "material_density": 2700.0,
    "export_step": True,
}


class WheelTools:
    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        positive = {"type": "number", "exclusiveMinimum": 0}
        props: dict[str, Any] = {
            "rim_diameter": positive,
            "rim_width": positive,
            "offset": {"type": "number"},
            "pcd": positive,
            "bolt_count": {"type": "integer", "minimum": 3, "maximum": 10},
            "center_bore": positive,
            "spoke_count": {"type": "integer", "minimum": 3, "maximum": 30},
            "spoke_style": {"type": "string", "enum": ["simple_lofted"]},
            "hub_thickness": positive,
            "flange_height": positive,
            "rim_thickness": positive,
            "spoke_thickness": positive,
            "draft_angle": {"type": "number", "minimum": 0, "maximum": 10},
            "fillet_radius": positive,
            "valve_hole_diameter": positive,
            "lug_hole_diameter": positive,
            "material_density": positive,
            "output_path": {"type": "string"},
            "export_step": {"type": "boolean", "default": True},
            "part_name": {"type": "string", "default": "MCP_Wheel"},
        }
        required = [
            "rim_diameter",
            "rim_width",
            "offset",
            "pcd",
            "bolt_count",
            "center_bore",
            "spoke_count",
            "spoke_style",
        ]
        return [
            {
                "name": "catia_design_wheel",
                "description": "Create a validated parametric cast-style wheel using the simple_lofted spoke family. Requires Part Design and GSD licenses.",
                "inputSchema": object_schema(props, required),
            }
        ]

    @staticmethod
    def validate(arguments: dict[str, Any]) -> dict[str, Any]:
        values = {**DEFAULTS, **arguments}
        if values.get("spoke_style") != "simple_lofted":
            raise ValueError("V1 supports only spoke_style='simple_lofted'")
        for name in (
            "rim_diameter",
            "rim_width",
            "pcd",
            "center_bore",
            "hub_thickness",
            "flange_height",
            "rim_thickness",
            "spoke_thickness",
            "fillet_radius",
            "valve_hole_diameter",
            "lug_hole_diameter",
            "material_density",
        ):
            if not isinstance(values.get(name), (int, float)) or values[name] <= 0:
                raise ValueError(f"{name} must be greater than zero")
        if not 3 <= values["bolt_count"] <= 10:
            raise ValueError("bolt_count must be between 3 and 10")
        if not 3 <= values["spoke_count"] <= 30:
            raise ValueError("spoke_count must be between 3 and 30")
        outer_radius = values["rim_diameter"] / 2
        inner_radius = outer_radius - values["flange_height"] - values["rim_thickness"]
        hub_radius = max(
            values["pcd"] / 2 + values["lug_hole_diameter"], values["center_bore"] / 2 + 15
        )
        if inner_radius <= hub_radius + values["fillet_radius"] * 2:
            raise ValueError("Rim/PCD/bore dimensions leave no radial room for spokes and fillets")
        if values["pcd"] <= values["center_bore"] + 2 * values["lug_hole_diameter"]:
            raise ValueError("PCD is too small for the center bore and lug holes")
        if abs(values["offset"]) > values["rim_width"] / 2:
            raise ValueError("offset must lie within half the rim width")
        pitch_at_hub = 2 * math.pi * hub_radius / values["spoke_count"]
        if values["spoke_thickness"] >= pitch_at_hub * 0.8:
            raise ValueError("spoke_thickness/spoke_count would cause spoke self-intersection")
        values["inner_radius"] = inner_radius
        values["hub_radius"] = hub_radius
        return values

    def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name != "catia_design_wheel":
            raise ValueError(f"Unknown wheel tool: {tool_name}")
        values = self.validate(args)
        report: dict[str, Any] = {
            "status": "in_progress",
            "parameters": values,
            "phases": [],
            "warnings": [
                "Engineering sign-off, Class-A surfacing, GD&T, DFM and FEA are outside this tool."
            ],
        }
        try:
            self.conn.ensure_connected()
            doc = self.conn.documents.Add("Part")
            try:
                # Part.Name is read-only on some CATIA configurations (it mirrors
                # the document name); a failed rename shouldn't abort the build.
                doc.Part.Name = values.get("part_name", "MCP_Wheel")
            except Exception:
                pass
            report["phases"].append(
                {"name": "document", "status": "complete", "feature": doc.Part.Name}
            )
            knowledge = KnowledgeTools(self.conn)
            for name, kind in (
                ("rim_diameter", "length"),
                ("rim_width", "length"),
                ("offset", "length"),
                ("pcd", "length"),
                ("bolt_count", "integer"),
                ("center_bore", "length"),
                ("spoke_count", "integer"),
                ("hub_thickness", "length"),
                ("spoke_thickness", "length"),
            ):
                knowledge.execute(
                    "catia_create_parameter",
                    {"name": f"Wheel_{name}", "type": kind, "value": values[name]},
                )
            report["phases"].append({"name": "parameters", "status": "complete"})
            features = self._build_geometry(values, report)
            report["features"] = features
            part_path, step_path = self._save_and_export(values, report)
            report["catpart_path"] = part_path
            report["step_path"] = step_path
            try:
                # Mass/volume/bounding-box are a bonus report, not the deliverable -
                # a built and saved solid must not be reported as "failed" just
                # because SPAWorkbench.GetMeasurable couldn't be reached.
                report["measurements"] = self._measure(values["material_density"])
            except Exception as exc:
                report["warnings"].append(f"Measurement step failed (geometry was built and saved): {exc}")
            report["status"] = "complete"
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = str(exc)
            report["warnings"].append("The partial CATIA document was left open for diagnosis.")
        return json.dumps(report, indent=2, ensure_ascii=False)

    @staticmethod
    def _try_rename(obj: Any, name: str) -> None:
        """Best-effort rename. Not all CATIA object types accept a written
        .Name on every configuration; a failed cosmetic rename must not abort
        the build, since nothing downstream looks features up by this name."""
        try:
            obj.Name = name
        except Exception:
            pass

    def _build_geometry(self, v: dict[str, Any], report: dict[str, Any]) -> list[str]:
        """Build a conservative wheel solid; each phase updates before continuing."""
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        origin = part.OriginElements
        names: list[str] = []
        # Rim barrel: annular pad on XY, centered across width.
        sketch = body.Sketches.Add(part.CreateReferenceFromObject(origin.PlaneXY))
        self._try_rename(sketch, "Rim_Profile")
        f = sketch.OpenEdition()
        f.CreateClosedCircle(0, 0, v["rim_diameter"] / 2)
        f.CreateClosedCircle(0, 0, v["inner_radius"])
        sketch.CloseEdition()
        rim = part.ShapeFactory.AddNewPad(sketch, v["rim_width"])
        self._try_rename(rim, "Rim_Barrel")
        rim.IsSymmetric = True
        part.UpdateObject(rim)
        names.append(rim.Name)
        report["phases"].append({"name": "rim", "status": "complete", "feature": rim.Name})
        # Hub disk and straight tapered spoke web are one sketch/pad; the radial sectors
        # create a robust precursor solid that later fillet/draft operations can style.
        sketch = body.Sketches.Add(part.CreateReferenceFromObject(origin.PlaneXY))
        self._try_rename(sketch, "Hub_Spokes_Profile")
        f = sketch.OpenEdition()
        f.CreateClosedCircle(0, 0, v["hub_radius"])
        half = v["spoke_thickness"] / 2
        for i in range(v["spoke_count"]):
            a = 2 * math.pi * i / v["spoke_count"]
            tangent = (-math.sin(a), math.cos(a))
            radial = (math.cos(a), math.sin(a))
            # r1 must be >= hub_radius: the quad's near-hub corners are offset
            # tangentially by `half` from radius r1, so their true distance from
            # the origin is hypot(r1, half) >= r1. Using hub_radius*0.75 (the
            # original value) put those corners well inside the hub circle,
            # producing a self-intersecting/overlapping sketch profile that
            # CATIA's Pad solver rejects (UpdateObject fails with a generic
            # COM error, no useful diagnostic). Starting exactly at hub_radius
            # keeps the spoke flush with, not inside, the hub disk.
            r1, r2 = v["hub_radius"], v["inner_radius"] + v["rim_thickness"] / 2
            pts = [
                (radial[0] * r1 + tangent[0] * half, radial[1] * r1 + tangent[1] * half),
                (
                    radial[0] * r2 + tangent[0] * half * 0.65,
                    radial[1] * r2 + tangent[1] * half * 0.65,
                ),
                (
                    radial[0] * r2 - tangent[0] * half * 0.65,
                    radial[1] * r2 - tangent[1] * half * 0.65,
                ),
                (radial[0] * r1 - tangent[0] * half, radial[1] * r1 - tangent[1] * half),
            ]
            for p1, p2 in zip(pts, pts[1:] + pts[:1]):
                f.CreateLine(*p1, *p2)
        sketch.CloseEdition()
        web = part.ShapeFactory.AddNewPad(sketch, v["hub_thickness"])
        self._try_rename(web, "Simple_Lofted_Spoke_Web")
        web.IsSymmetric = True
        part.UpdateObject(web)
        names.append(web.Name)
        report["phases"].append(
            {
                "name": "hub_and_spokes",
                "status": "complete",
                "feature": web.Name,
                "note": "Tapered radial spoke precursor; apply GSD surface tools for style-specific crown surfaces.",
            }
        )
        # Bore and lug holes in one through pocket.
        sketch = body.Sketches.Add(part.CreateReferenceFromObject(origin.PlaneXY))
        self._try_rename(sketch, "Bore_Lugs_Profile")
        f = sketch.OpenEdition()
        f.CreateClosedCircle(0, 0, v["center_bore"] / 2)
        for i in range(v["bolt_count"]):
            a = 2 * math.pi * i / v["bolt_count"]
            f.CreateClosedCircle(
                math.cos(a) * v["pcd"] / 2, math.sin(a) * v["pcd"] / 2, v["lug_hole_diameter"] / 2
            )
        sketch.CloseEdition()
        pocket = part.ShapeFactory.AddNewPocket(sketch, v["rim_width"] * 2)
        self._try_rename(pocket, "Center_Bore_And_Lugs")
        pocket.IsSymmetric = True
        part.UpdateObject(pocket)
        names.append(pocket.Name)
        report["phases"].append(
            {"name": "mounting_features", "status": "complete", "feature": pocket.Name}
        )
        part.Update()
        self.conn.refresh_display()
        report["warnings"].append(
            "Valve drilling, back-cavity optimization, GSD crown surfaces, casting draft and final fillet selection require live topology qualification for the target CATIA release."
        )
        return names

    def _save_and_export(
        self, values: dict[str, Any], report: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        output = values.get("output_path")
        if not output:
            return None, None
        root, ext = os.path.splitext(os.path.abspath(output))
        part_path = output if ext.lower() == ".catpart" else root + ".CATPart"
        os.makedirs(os.path.dirname(part_path), exist_ok=True)
        self.conn.active_document.SaveAs(part_path)
        step_path = None
        if values.get("export_step", True):
            # STEP export can fail independently of the CATPart save - commonly
            # because the CATIA seat lacks an interoperability/STEP license.
            # The built and saved solid is the valuable result; a missing
            # export format must not discard it.
            try:
                candidate = root + ".stp"
                self.conn.active_document.ExportData(candidate, "stp")
                step_path = candidate
            except Exception as exc:
                report["warnings"].append(
                    f"STEP export failed (CATPart was saved successfully): {exc}"
                )
        return part_path, step_path

    def _measure(self, density: float) -> dict[str, Any]:
        part = self.conn.get_active_part()
        ref = part.CreateReferenceFromObject(self.conn.get_active_part_body())
        m = self.conn.app.GetWorkbench("SPAWorkbench").GetMeasurable(ref)
        data: dict[str, Any] = {}
        try:
            data["volume_mm3"] = m.Volume
            data["mass_kg"] = m.Volume * 1e-9 * density
        except Exception:
            pass
        try:
            bbox = [0.0] * 6
            m.GetBoundingBox(bbox)
            data["bounding_box_mm"] = bbox
        except Exception:
            pass
        return data
