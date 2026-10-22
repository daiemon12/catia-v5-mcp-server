"""Measurement and analysis tools for CATIA V5 and CATIA 3DEXPERIENCE.

Distance, inertia, bounding box, element measures, and part parameters.
Platform specifics (V5 SPAWorkbench vs 3DEXPERIENCE MeasurableService /
InertiaService) live in catia_mcp.measure.Measurer.
"""

from __future__ import annotations

import json
import re
from typing import Any

from catia_mcp.automation import call_fill_array
from catia_mcp.connection import CATIAConnection
from catia_mcp.measure import (
    M2_TO_MM2,
    M3_TO_MM3,
    M_TO_MM,
    UNIT_NOTE_3DX,
    Measurer,
)
from catia_mcp.references import search_final_topology

# CATIA V5's SPAWorkbench Measurable API returns every value in MKS units
# (meters, m2, m3, kg.m2) regardless of the document's display units.
# Feature creation APIs, by contrast, take millimeters. All measurement
# results are therefore converted to mm-based units here, at the server
# boundary, so agents always see consistent mm/mm2/mm3 values.
_M_TO_MM = M_TO_MM
_M2_TO_MM2 = M2_TO_MM2
_M3_TO_MM3 = M3_TO_MM3


def read_measurable_array(app: Any, measurable: Any, method: str, count: int) -> list[float]:
    """Run `measurable.<method> a` inside CATIA via SystemService.Evaluate and
    return the filled array (field-proven on V5R20 for GetCOG/GetPlane).

    Coordinates returned this way (GetCOG, GetPoint, GetPlane) are observed in
    the document's length unit (mm), unlike Area/Volume which are MKS.
    """
    return call_fill_array(app, measurable, method, count)


class MeasurementTools:
    """Tools for measurement and analysis in CATIA V5 and 3DEXPERIENCE."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self.measure = Measurer(connection)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_measure_distance",
                "description": (
                    "Measure the minimum distance between two geometry elements. "
                    "Returns distance in mm. Elements resolve by tree name "
                    "(features, sketches, e.g. 'Pad.1', 'Sketch.2') or by "
                    "indexed topology ('Face.N' / 'Edge.N' as enumerated by "
                    "catia_list_faces / catia_list_edges on the final solid)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "element1": {
                            "type": "string",
                            "description": "Name of first element (feature, face, edge, point)",
                        },
                        "element2": {
                            "type": "string",
                            "description": "Name of second element",
                        },
                    },
                    "required": ["element1", "element2"],
                },
            },
            {
                "name": "catia_get_inertia",
                "description": (
                    "Get inertia properties of the active part: volume (mm3 and cm3), "
                    "surface area (mm2 and cm2), center of gravity (mm), mass in kg "
                    "(if a density is passed), inertia matrix (kg.m2, from the material "
                    "density defined in CATIA). All values are converted server-side "
                    "from CATIA's internal MKS measurement units."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "density": {
                            "type": "number",
                            "description": "Material density in kg/m3 (optional, for mass calculation)",
                        },
                    },
                },
            },
            {
                "name": "catia_get_bounding_box",
                "description": (
                    "Get the bounding box of the active part from a vertex "
                    "sweep of the final shape, in mm. Exact for planar-faced "
                    "solids; curved faces may extend beyond the reported "
                    "bounds (stated in the result)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_get_parameters",
                "description": (
                    "List all user-defined and computed parameters of the active part. "
                    "Includes dimensions, formulas, and design tables."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filter": {
                            "type": "string",
                            "description": "Optional name filter (partial match)",
                        },
                    },
                },
            },
            {
                "name": "catia_set_parameter",
                "description": (
                    "Set the value of a named parameter in the active part. "
                    "Useful for parametric design modifications."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Full parameter name (e.g., 'Part1\\\\Pad.1\\\\FirstLimit\\\\Length')",
                        },
                        "value": {
                            "type": "number",
                            "description": "New value for the parameter",
                        },
                    },
                    "required": ["name", "value"],
                },
            },
            {
                "name": "catia_update_part",
                "description": "Force update/rebuild of the active part. Recalculates all features.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_measure_element",
                "description": (
                    "Measure one element: volume, area, length, radius, center of "
                    "gravity or point coordinates, whichever apply. Elements resolve by "
                    "tree name ('Pad.1', 'Sketch.2', GSD names) or indexed topology "
                    "('Face.N' / 'Edge.N' / 'Vertex.N'). Values in mm, mm2, mm3."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "element": {"type": "string", "description": "Element to measure"},
                    },
                    "required": ["element"],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_measure_distance":
                return self._measure_distance(arguments["element1"], arguments["element2"])
            case "catia_get_inertia":
                return self._get_inertia(arguments.get("density"))
            case "catia_get_bounding_box":
                return self._get_bounding_box()
            case "catia_get_parameters":
                return self._get_parameters(arguments.get("filter"))
            case "catia_set_parameter":
                return self._set_parameter(arguments["name"], arguments["value"])
            case "catia_update_part":
                return self._update_part()
            case "catia_measure_element":
                return self._measure_element(arguments["element"])
            case _:
                raise ValueError(f"Unknown measurement tool: {tool_name}")

    def _resolve_reference(self, part: Any, name: str) -> Any:
        """Resolve an element name to a CATIA Reference.

        Tree-named objects (Pad.1, Sketch.2) resolve through a Name= search.
        Topology uses the indexed form Face.N / Edge.N / Vertex.N over the
        body's final shape, matching the indices listed by catia_list_faces
        and catia_list_edges. Topology references come from the selection's
        Reference property: CreateReferenceFromObject rejects HSO-resolved
        topology cells (field-verified E_INVALIDARG on V5R20).
        """
        sel = self.conn.hso
        topo = re.match(r"^(Face|Edge|Vertex)\.(\d+)$", name)
        try:
            if topo:
                kind, idx = topo.group(1), int(topo.group(2))
                body = self.conn.get_active_part_body()
                if body.Shapes.Count == 0:
                    raise RuntimeError(
                        f"Cannot resolve '{name}': the active body has no "
                        "solid shape to enumerate topology from."
                    )
                count = search_final_topology(sel, body, kind, is_3dx=self.conn.is_3dx)
                if idx < 1 or idx > count:
                    raise RuntimeError(
                        f"'{name}' is out of range: the final shape exposes "
                        f"{count} {kind.lower()}(s). Use catia_list_faces / "
                        "catia_list_edges to enumerate valid indices."
                    )
                return sel.Item(idx).Reference

            sel.Clear()
            sel.Search(f"Name={name},all")
            if sel.Count == 0:
                raise RuntimeError(
                    f"Element '{name}' not found by tree name. Use feature "
                    "or sketch names (e.g. 'Pad.1'), or the indexed topology "
                    "form Face.N / Edge.N from catia_list_faces / "
                    "catia_list_edges."
                )
            obj = sel.Item(1).Value
            return part.CreateReferenceFromObject(obj)
        finally:
            try:
                sel.Clear()
            except Exception:
                pass

    def _measure_distance(self, elem1_name: str, elem2_name: str) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()

        ref1 = self._resolve_reference(part, elem1_name)
        ref2 = self._resolve_reference(part, elem2_name)

        measured = self.measure.min_distance(ref1, ref2)
        points = ""
        if "point1_mm" in measured:
            p1 = ", ".join(f"{v:g}" for v in measured["point1_mm"])
            p2 = ", ".join(f"{v:g}" for v in measured["point2_mm"])
            points = f"; closest points ({p1}) and ({p2}) mm"
        note = f" ({UNIT_NOTE_3DX})" if self.conn.is_3dx else ""
        return (
            f"Minimum distance between '{elem1_name}' and '{elem2_name}': "
            f"{measured['distance_mm']:.4f} mm{points}{note}"
        )

    def _get_inertia(self, density: float | None = None) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()

        result: dict[str, Any] = {}
        volume_m3: float | None = None

        try:
            volume_mm3 = self.measure.volume_mm3(part, body)
            volume_m3 = volume_mm3 / _M3_TO_MM3
            result["volume_mm3"] = round(volume_mm3, 4)
            result["volume_cm3"] = round(volume_m3 * 1e6, 4)
        except Exception as e:
            result["volume_mm3"] = f"unavailable: {e}"

        try:
            area_mm2 = self.measure.area_mm2(part, body)
            result["area_mm2"] = round(area_mm2, 4)
            result["area_cm2"] = round(area_mm2 / 100.0, 4)
        except Exception as e:
            result["area_mm2"] = f"unavailable: {e}"

        try:
            # GetCOG coordinates come back in the document's length unit
            # (mm), not MKS: field-observed on V5R20 for GetPlane/GetCOG.
            cog = self.measure.cog_mm(part, body)
            result["center_of_gravity_mm"] = {
                "x": round(cog[0], 4),
                "y": round(cog[1], 4),
                "z": round(cog[2], 4),
            }
        except Exception as e:
            result["center_of_gravity_mm"] = f"unavailable: {e}"

        if density and volume_m3 is not None:
            mass_kg = density * volume_m3
            result["mass_kg"] = round(mass_kg, 6)
            result["mass_g"] = round(mass_kg * 1000, 3)
            result["density_kg_m3"] = density

        try:
            # Inertia data lives on the inertia object (V5 SPAWorkbench
            # Inertias, 3DEXPERIENCE InertiaService), not on Measurable.
            inertia = self.measure.inertia(part, body)
            result["mass_from_material_kg"] = round(inertia["mass_kg"], 6)
            matrix = inertia.get("matrix")
            if matrix:
                result["inertia_matrix_kg_m2"] = [
                    [round(matrix[0], 4), round(matrix[1], 4), round(matrix[2], 4)],
                    [round(matrix[3], 4), round(matrix[4], 4), round(matrix[5], 4)],
                    [round(matrix[6], 4), round(matrix[7], 4), round(matrix[8], 4)],
                ]
            else:
                result["inertia_matrix_kg_m2"] = f"unavailable: {inertia.get('matrix_error')}"
            if "cog_raw" in inertia:
                result["inertia_cog_raw"] = [round(v, 6) for v in inertia["cog_raw"]]
        except Exception as e:
            result["inertia_matrix_kg_m2"] = f"unavailable: {e}"

        if self.conn.is_3dx:
            result["units_note"] = UNIT_NOTE_3DX
        return json.dumps(result, indent=2)

    def _get_bounding_box(self) -> str:
        # Measurable has no bounding-box method in any V5 release, so the
        # box is computed from the final shape's vertices (exact for
        # planar-faced solids; curved faces can extend past their vertices,
        # which the output states explicitly).
        self.conn.ensure_connected()
        self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        if body.Shapes.Count == 0:
            raise RuntimeError("The active body has no solid shape yet.")
        sel = self.conn.hso
        refs = []
        try:
            count = search_final_topology(sel, body, "Vertex", is_3dx=self.conn.is_3dx)
            if count == 0:
                raise RuntimeError(
                    "UNSUPPORTED_CAPABILITY: the final shape exposes no "
                    "vertices (fully curved solid); a bounding box cannot be "
                    "derived through the automation API."
                )
            truncated = count > 200
            if truncated:
                count = 200  # cap the sweep; stated in the output below
            for i in range(1, count + 1):
                refs.append(sel.Item(i).Reference)
        finally:
            try:
                sel.Clear()
            except Exception:
                pass

        xs, ys, zs = [], [], []
        for ref in refs:
            # Vertex coordinates in the document's length unit (mm).
            pt = self.measure.point_mm(ref)
            xs.append(pt[0])
            ys.append(pt[1])
            zs.append(pt[2])

        result = {
            "min": {"x": round(min(xs), 4), "y": round(min(ys), 4), "z": round(min(zs), 4)},
            "max": {"x": round(max(xs), 4), "y": round(max(ys), 4), "z": round(max(zs), 4)},
            "dimensions": {
                "length_x": round(max(xs) - min(xs), 4),
                "length_y": round(max(ys) - min(ys), 4),
                "length_z": round(max(zs) - min(zs), 4),
            },
            "method": (
                f"vertex sweep over {len(refs)} vertices of the final shape; "
                "exact for planar-faced solids, curved faces may extend "
                "beyond these bounds"
                + (" (vertex count capped at 200)" if truncated else "")
            ),
        }
        return json.dumps(result, indent=2)

    def _measure_element(self, name: str) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        ref = self._resolve_reference(part, name)
        result: dict[str, Any] = {"element": name}
        if self.conn.is_3dx:
            for kind, label, scale in (
                ("volume", "volume_mm3", M3_TO_MM3),
                ("surface", "area_mm2", M2_TO_MM2),
                ("curve", "length_mm", M_TO_MM),
            ):
                try:
                    measurable = self.measure.measurable_3dx(ref, kind)
                    names = {
                        "volume": ("GetVolume", "Volume"),
                        "surface": ("GetArea", "Area"),
                        "curve": ("GetLength", "Length"),
                    }[kind]
                    result[label] = round(self.measure.scalar(measurable, names) * scale, 4)
                except Exception:
                    continue
            try:
                result["point_mm"] = [round(v, 4) for v in self.measure.point_mm(ref)]
            except Exception:
                pass
            result["units_note"] = UNIT_NOTE_3DX
        else:
            measurable = self.measure.spa_workbench().GetMeasurable(ref)
            for attr, label, scale in (
                ("Volume", "volume_mm3", M3_TO_MM3),
                ("Area", "area_mm2", M2_TO_MM2),
                ("Length", "length_mm", M_TO_MM),
                ("Radius", "radius_mm", M_TO_MM),
                ("Perimeter", "perimeter_mm", M_TO_MM),
            ):
                try:
                    value = float(getattr(measurable, attr))
                except Exception:
                    continue
                result[label] = round(value * scale, 4)
            for method, label in (("GetCOG", "center_of_gravity_mm"), ("GetPoint", "point_mm")):
                try:
                    values = call_fill_array(self.conn.app, measurable, method, 3)
                    result[label] = [round(v, 4) for v in values]
                except Exception:
                    continue
            if any(k in result for k in ("length_mm", "radius_mm", "perimeter_mm")):
                result["units_note"] = (
                    "length, radius and perimeter converted from MKS (m) like the "
                    "field-confirmed area and volume; not field-verified themselves"
                )
        if not set(result) - {"element", "units_note"}:
            raise RuntimeError(
                f"No measure applies to '{name}' through the automation API (tried "
                "volume, area, length, radius, point)."
            )
        return json.dumps(result, indent=2)

    def _get_parameters(self, name_filter: str | None = None) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        params = part.Parameters

        result = []
        for i in range(1, params.Count + 1):
            param = params.Item(i)
            name = param.Name

            if name_filter and name_filter.lower() not in name.lower():
                continue

            info: dict[str, Any] = {"name": name}
            try:
                info["value"] = param.Value
            except Exception:
                info["value"] = "N/A"
            try:
                info["comment"] = param.Comment
            except Exception:
                pass

            result.append(info)

        if not result:
            return "No parameters found" + (f" matching '{name_filter}'" if name_filter else "")
        return json.dumps(result, indent=2, ensure_ascii=False)

    def _set_parameter(self, name: str, value: float) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        params = part.Parameters

        param = params.Item(name)
        old_value = param.Value
        param.Value = value
        part.Update()

        self.conn.refresh_display()
        return f"Parameter '{name}' changed: {old_value} -> {value}"

    def _update_part(self) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        part.Update()
        self.conn.refresh_display()
        return "Part updated successfully"
