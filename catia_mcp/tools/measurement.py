"""Measurement and analysis tools for CATIA V5.

Distance, angle, inertia, bounding box, and part property queries.
"""

from __future__ import annotations

import json
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools._geometry import byref_doubles


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
                    "Returns distance in mm."
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
                    "Get inertia properties of the active part: volume, surface area, "
                    "center of gravity, mass (if density is defined), moments of inertia."
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
                    "Get the bounding box of the active part. "
                    "Returns min/max coordinates in mm."
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

    def _measure_distance(self, elem1_name: str, elem2_name: str) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        spa = self.conn.active_document.GetWorkbench("SPAWorkbench")

        # Create references from names
        sel = self.conn.hso
        sel.Clear()

        # Search for the elements
        sel.Search(f"Name={elem1_name},all")
        if sel.Count == 0:
            raise RuntimeError(f"Element '{elem1_name}' not found")
        ref1 = part.CreateReferenceFromObject(sel.Item(1).Value)

        sel.Clear()
        sel.Search(f"Name={elem2_name},all")
        if sel.Count == 0:
            raise RuntimeError(f"Element '{elem2_name}' not found")
        ref2 = part.CreateReferenceFromObject(sel.Item(1).Value)
        sel.Clear()

        # Measure
        measurable = spa.GetMeasurable(ref1)
        # CATIA's Measurable interface returns lengths in its base unit
        # (meters), regardless of the document's display unit.
        distance_mm = measurable.GetMinimumDistance(ref2) * 1000

        return f"Minimum distance between '{elem1_name}' and '{elem2_name}': {distance_mm:.4f} mm"

    def _get_inertia(self, density: float | None = None) -> str:
        self.conn.ensure_connected()
        spa = self.conn.active_document.GetWorkbench("SPAWorkbench")
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        ref = part.CreateReferenceFromObject(body)

        measurable = spa.GetMeasurable(ref)

        result: dict[str, Any] = {}

        # CATIA's Measurable interface returns Volume/Area/coordinates in its
        # base SI units (m3, m2, m) regardless of the document's display
        # unit; convert explicitly rather than assuming mm.
        try:
            volume_m3 = measurable.Volume
            result["volume_mm3"] = round(volume_m3 * 1e9, 4)
            result["volume_cm3"] = round(volume_m3 * 1e6, 4)
        except Exception:
            pass

        try:
            area_m2 = measurable.Area
            result["area_mm2"] = round(area_m2 * 1e6, 4)
            result["area_cm2"] = round(area_m2 * 1e4, 4)
        except Exception:
            pass

        try:
            # A VARIANT-wrapped array (VT_R8 and VT_VARIANT both tried) made
            # this raise where a plain list at least didn't error - reverted
            # pending a proper fix. See docs/PLAN.md for the ByRef findings.
            cog = [0.0, 0.0, 0.0]
            measurable.GetCOG(cog)
            result["center_of_gravity_mm"] = {
                "x": round(cog[0] * 1000, 4),
                "y": round(cog[1] * 1000, 4),
                "z": round(cog[2] * 1000, 4),
            }
        except Exception:
            pass

        if density and "volume_mm3" in result:
            volume_m3 = result["volume_mm3"] * 1e-9  # mm3 to m3
            mass_kg = density * volume_m3
            result["mass_kg"] = round(mass_kg, 6)
            result["mass_g"] = round(mass_kg * 1000, 3)
            result["density_kg_m3"] = density

        try:
            inertia = [0.0] * 9
            measurable.GetInertia(inertia)
            result["inertia_matrix"] = [
                [round(inertia[0], 4), round(inertia[1], 4), round(inertia[2], 4)],
                [round(inertia[3], 4), round(inertia[4], 4), round(inertia[5], 4)],
                [round(inertia[6], 4), round(inertia[7], 4), round(inertia[8], 4)],
            ]
        except Exception:
            pass

        return json.dumps(result, indent=2)

    def _get_bounding_box(self) -> str:
        self.conn.ensure_connected()
        spa = self.conn.active_document.GetWorkbench("SPAWorkbench")
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        ref = part.CreateReferenceFromObject(body)

        measurable = spa.GetMeasurable(ref)

        # Two attempts at a single 6-element ByRef array (VT_R8, then
        # VT_VARIANT) both failed identically ("GetMeasurable.GetBoundingBox",
        # no COM error tuple) - a signature-independent failure suggests the
        # problem was never argument type, but argument count: CATIA's VBA-era
        # Automation IDL commonly declares GetBoundingBox(oMin, oMax) as two
        # separate 3-element out-params, not one combined 6-element array.
        omin, omax = byref_doubles(3), byref_doubles(3)
        measurable.GetBoundingBox(omin, omax)
        bbox_mm = [v * 1000 for v in (*omin.value, *omax.value)]

        result = {
            "min": {"x": round(bbox_mm[0], 4), "y": round(bbox_mm[1], 4), "z": round(bbox_mm[2], 4)},
            "max": {"x": round(bbox_mm[3], 4), "y": round(bbox_mm[4], 4), "z": round(bbox_mm[5], 4)},
            "dimensions": {
                "length_x": round(bbox_mm[3] - bbox_mm[0], 4),
                "length_y": round(bbox_mm[4] - bbox_mm[1], 4),
                "length_z": round(bbox_mm[5] - bbox_mm[2], 4),
            },
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
