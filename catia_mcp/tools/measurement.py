"""Measurement and analysis tools for CATIA V5.

Distance, angle, inertia, bounding box, and part property queries.
"""

from __future__ import annotations

import json
import re
from typing import Any

from catia_mcp.connection import CATIAConnection

# CATIA V5's SPAWorkbench Measurable API returns every value in MKS units
# (meters, m2, m3, kg.m2) regardless of the document's display units.
# Feature creation APIs, by contrast, take millimeters. All measurement
# results are therefore converted to mm-based units here, at the server
# boundary, so agents always see consistent mm/mm2/mm3 values.
_M_TO_MM = 1000.0
_M2_TO_MM2 = 1e6
_M3_TO_MM3 = 1e9


class MeasurementTools:
    """Tools for measurement and analysis in CATIA V5."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

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
            case _:
                raise ValueError(f"Unknown measurement tool: {tool_name}")

    # In/out CATSafeArrayVariant parameters (GetCOG, GetPoint,
    # GetInertiaMatrix) do not marshal through late-bound IDispatch: the
    # Python list is passed by value and never mutated. The documented
    # workaround (used by pycatia) is to run the array-filling call inside
    # CATIA via SystemService.Evaluate and return the values as a string.
    _VBS_COG = (
        'Function GetCOGStr(oRef)\n'
        '    Dim oSPA, oMeas\n'
        '    Dim aCOG(2)\n'
        '    Set oSPA = CATIA.ActiveDocument.GetWorkbench("SPAWorkbench")\n'
        '    Set oMeas = oSPA.GetMeasurable(oRef)\n'
        '    oMeas.GetCOG aCOG\n'
        '    GetCOGStr = CStr(aCOG(0)) & ";" & CStr(aCOG(1)) & ";" & CStr(aCOG(2))\n'
        'End Function'
    )
    _VBS_POINT = (
        'Function GetPointStr(oRef)\n'
        '    Dim oSPA, oMeas\n'
        '    Dim aPt(2)\n'
        '    Set oSPA = CATIA.ActiveDocument.GetWorkbench("SPAWorkbench")\n'
        '    Set oMeas = oSPA.GetMeasurable(oRef)\n'
        '    oMeas.GetPoint aPt\n'
        '    GetPointStr = CStr(aPt(0)) & ";" & CStr(aPt(1)) & ";" & CStr(aPt(2))\n'
        'End Function'
    )
    _VBS_INERTIA = (
        'Function GetInertiaStr(oBody)\n'
        '    Dim oSPA, oInertias, oInertia, i, sOut\n'
        '    Dim aM(8)\n'
        '    Set oSPA = CATIA.ActiveDocument.GetWorkbench("SPAWorkbench")\n'
        '    Set oInertias = oSPA.Inertias\n'
        '    Set oInertia = oInertias.Add(oBody)\n'
        '    oInertia.GetInertiaMatrix aM\n'
        '    sOut = CStr(oInertia.Mass)\n'
        '    For i = 0 To 8\n'
        '        sOut = sOut & ";" & CStr(aM(i))\n'
        '    Next\n'
        '    GetInertiaStr = sOut\n'
        'End Function'
    )

    def _evaluate_floats(self, script: str, func: str, params: list) -> list[float]:
        """Run a VBScript function inside CATIA and parse its ;-joined floats.

        CStr honors the Windows locale, so decimal commas are normalized.
        """
        raw = self.conn.app.SystemService.Evaluate(script, 0, func, params)
        return [float(tok.replace(",", ".")) for tok in str(raw).split(";")]

    def _spa_workbench(self) -> Any:
        """Get the SPAWorkbench measurement workbench.

        GetWorkbench is documented on Document, not Application, so try the
        active document first and keep the application call as a fallback
        for environments where it happens to resolve there.
        """
        doc = self.conn.active_document
        try:
            return doc.GetWorkbench("SPAWorkbench")
        except AttributeError:
            return self.conn.app.GetWorkbench("SPAWorkbench")

    def _resolve_reference(self, part: Any, name: str) -> Any:
        """Resolve an element name to a CATIA Reference.

        Tree-named objects (Pad.1, Sketch.2) resolve through a Name= search.
        Topology uses the indexed form Face.N / Edge.N over the body's final
        shape, matching the indices listed by catia_list_faces and
        catia_list_edges. Topology references come from the selection's
        Reference property: CreateReferenceFromObject rejects HSO-resolved
        topology cells (field-verified E_INVALIDARG on V5R20).
        """
        sel = self.conn.hso
        topo = re.match(r"^(Face|Edge)\.(\d+)$", name)
        try:
            if topo:
                kind, idx = topo.group(1), int(topo.group(2))
                body = self.conn.get_active_part_body()
                if body.Shapes.Count == 0:
                    raise RuntimeError(
                        f"Cannot resolve '{name}': the active body has no "
                        "solid shape to enumerate topology from."
                    )
                last_shape = body.Shapes.Item(body.Shapes.Count)
                sel.Clear()
                sel.Add(last_shape)
                sel.Search(f"Topology.{kind},sel")
                count = sel.Count
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
        spa = self._spa_workbench()

        ref1 = self._resolve_reference(part, elem1_name)
        ref2 = self._resolve_reference(part, elem2_name)

        # Measure (SPAWorkbench returns meters; convert to mm)
        measurable = spa.GetMeasurable(ref1)
        distance = measurable.GetMinimumDistance(ref2) * _M_TO_MM

        return f"Minimum distance between '{elem1_name}' and '{elem2_name}': {distance:.4f} mm"

    def _get_inertia(self, density: float | None = None) -> str:
        self.conn.ensure_connected()
        spa = self._spa_workbench()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        ref = part.CreateReferenceFromObject(body)

        measurable = spa.GetMeasurable(ref)

        result: dict[str, Any] = {}
        volume_m3: float | None = None

        try:
            volume_m3 = measurable.Volume  # m3
            result["volume_mm3"] = round(volume_m3 * _M3_TO_MM3, 4)
            result["volume_cm3"] = round(volume_m3 * 1e6, 4)
        except Exception:
            pass

        try:
            area_m2 = measurable.Area  # m2
            result["area_mm2"] = round(area_m2 * _M2_TO_MM2, 4)
            result["area_cm2"] = round(area_m2 * 1e4, 4)
        except Exception:
            pass

        try:
            cog = self._evaluate_floats(self._VBS_COG, "GetCOGStr", [ref])
            result["center_of_gravity_mm"] = {
                "x": round(cog[0] * _M_TO_MM, 4),
                "y": round(cog[1] * _M_TO_MM, 4),
                "z": round(cog[2] * _M_TO_MM, 4),
            }
        except Exception as e:
            result["center_of_gravity_mm"] = f"unavailable: {e}"

        if density and volume_m3 is not None:
            mass_kg = density * volume_m3
            result["mass_kg"] = round(mass_kg, 6)
            result["mass_g"] = round(mass_kg * 1000, 3)
            result["density_kg_m3"] = density

        try:
            # Inertia data lives on the SPAWorkbench Inertia object, not on
            # Measurable (Measurable.GetInertia does not exist in V5).
            vals = self._evaluate_floats(self._VBS_INERTIA, "GetInertiaStr", [body])
            result["mass_from_material_kg"] = round(vals[0], 6)
            inertia = vals[1:10]
            result["inertia_matrix_kg_m2"] = [
                [round(inertia[0], 4), round(inertia[1], 4), round(inertia[2], 4)],
                [round(inertia[3], 4), round(inertia[4], 4), round(inertia[5], 4)],
                [round(inertia[6], 4), round(inertia[7], 4), round(inertia[8], 4)],
            ]
        except Exception as e:
            result["inertia_matrix_kg_m2"] = f"unavailable: {e}"

        return json.dumps(result, indent=2)

    def _get_bounding_box(self) -> str:
        # Measurable has no bounding-box method in any V5 release, so the
        # box is computed from the final shape's vertices (exact for
        # planar-faced solids; curved faces can extend past their vertices,
        # which the output states explicitly).
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        if body.Shapes.Count == 0:
            raise RuntimeError("The active body has no solid shape yet.")
        last_shape = body.Shapes.Item(body.Shapes.Count)

        sel = self.conn.hso
        refs = []
        try:
            sel.Clear()
            sel.Add(last_shape)
            sel.Search("Topology.Vertex,sel")
            count = sel.Count
            if count == 0:
                raise RuntimeError(
                    "UNSUPPORTED_CAPABILITY: the final shape exposes no "
                    "vertices (fully curved solid); a bounding box cannot be "
                    "derived through the V5 automation API."
                )
            if count > 200:
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
            pt = self._evaluate_floats(self._VBS_POINT, "GetPointStr", [ref])
            xs.append(pt[0] * _M_TO_MM)
            ys.append(pt[1] * _M_TO_MM)
            zs.append(pt[2] * _M_TO_MM)

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
                + (" (vertex count capped at 200)" if len(refs) == 200 else "")
            ),
        }
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
