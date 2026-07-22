"""Measurement and analysis tools for CATIA V5.

Distance, angle, inertia, bounding box, and part property queries.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pythoncom
from win32com.client import VARIANT

from catia_mcp.connection import CATIAConnection


def _byref_long() -> VARIANT:
    """A ByRef VT_I4 VARIANT for CATIA methods with scalar `long` output args
    (e.g. VisPropertySet.GetRealColor's oRed/oGreen/oBlue) - late-bound
    win32com dispatch can't infer ByRef-ness for scalar params from IDispatch
    alone, so the caller must wrap each one explicitly. Read back via `.value`
    after the call. Mirrors the array case in _geometry.byref_doubles.
    """
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


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
            {
                "name": "catia_list_faces",
                "description": (
                    "Enumerate the topological faces of a body's last shape (or a named "
                    "feature). For each face, reports its area, real RGB color (as applied "
                    "in the CATIA graphic properties, 0-255), and, if the face is planar, "
                    "its origin and unit normal vector (mm, part axis system). Non-planar "
                    "faces report planar=false with no normal. Use this to identify faces "
                    "by color (e.g. a colored draft/parting surface) and pull their exact "
                    "plane geometry for analysis, without needing a stable feature name."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "feature": {
                            "type": "string",
                            "description": "Feature/shape name to enumerate faces of (default: last shape in the active body)",
                        },
                    },
                },
            },
            {
                "name": "catia_list_edges_geometry",
                "description": (
                    "Enumerate the topological edges of a body's last shape (or a named "
                    "feature) with full geometry: length, start/mid/end points (mm), and, "
                    "for straight edges only, the unit direction vector. Curved edges "
                    "report is_line=false with no direction. Use this to find straight "
                    "ruling/generatrix edges (e.g. the straight sides of a ruled/drafted "
                    "surface) and read their exact 3D direction, which plain "
                    "catia_list_edges (names only) cannot do."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "feature": {
                            "type": "string",
                            "description": "Feature/shape name to enumerate edges of (default: last shape in the active body)",
                        },
                    },
                },
            },
            {
                "name": "catia_task06_debug_guides",
                "description": "Read-only diagnostic for task 06 guide curves and their CATIA references.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "document_path": {
                            "type": "string",
                            "description": "Full path to 06.CATPart",
                        },
                    },
                    "required": ["document_path"],
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
            case "catia_list_faces":
                return self._list_faces(arguments.get("feature"))
            case "catia_list_edges_geometry":
                return self._list_edges_geometry(arguments.get("feature"))
            case "catia_task06_debug_guides":
                return self._task06_debug_guides(arguments["document_path"])
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
        # GetBoundingBox does not exist anywhere in CATIA's Automation API.
        # Confirmed by reading pycatia's source (a comprehensive wrapper of
        # the real CAA V5 interfaces, built from official VBA documentation):
        # Measurable has no such method, and no other interface pycatia
        # covers (Selection, drawing views, etc.) exposes one either. Three
        # different call shapes against Measurable (1x6 VT_R8 array, 1x6
        # VT_VARIANT array, 2x3 VT_VARIANT arrays) all failed with the
        # identical "GetMeasurable.GetBoundingBox" error regardless of
        # argument type or count - the signature never mattered because the
        # member itself doesn't resolve. A real bounding box would need to be
        # computed manually (e.g. enumerating vertices via Topology.Vertex
        # search and taking min/max coordinates), which is a separate,
        # non-trivial feature, not a bug fix - see docs/PLAN.md.
        raise RuntimeError(
            "CATIA's Automation API has no bounding-box method on Measurable "
            "(confirmed against the real interface, not a marshaling bug). "
            "Use catia_get_inertia for volume/area/center-of-gravity instead."
        )

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

    def _get_last_shape(self, feature_name: str | None = None) -> Any:
        body = self.conn.get_active_part_body()
        shapes = body.Shapes
        if feature_name:
            return shapes.Item(feature_name)
        if shapes.Count == 0:
            raise RuntimeError("No features found in the active body.")
        return shapes.Item(shapes.Count)

    def _curve_units_to_mm(self, values: list[float]) -> list[float]:
        """Normalize CATIA curve coordinates/lengths to mm.

        On this CATIA install SPA curve measurements for imported solids return
        curve lengths in document units (mm), while other measurable APIs return
        SI units. Coordinates follow the same split. Use a conservative magnitude
        heuristic so small meter-scale values are converted but normal part-size
        millimeter values are left untouched.
        """
        max_abs = max((abs(v) for v in values), default=0.0)
        scale = 1000.0 if 0 < max_abs < 1.0 else 1.0
        return [v * scale for v in values]

    def _get_points_on_curve(self, measurable: Any) -> list[float] | None:
        attempts: list[Any] = [
            [0.0] * 9,
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0] * 9),
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, [0.0] * 9),
        ]
        for holder in attempts:
            try:
                measurable.GetPointsOnCurve(holder)
                values = list(holder.value if hasattr(holder, "value") else holder)
                if len(values) >= 9 and any(abs(float(v)) > 1e-12 for v in values):
                    return [float(v) for v in values[:9]]
            except Exception:
                continue
        return None

    def _list_faces(self, feature_name: str | None) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        spa = self.conn.active_document.GetWorkbench("SPAWorkbench")
        shape = self._get_last_shape(feature_name)

        sel = self.conn.hso
        sel.Clear()
        sel.Add(shape)
        sel.Search("Topology.Face,sel")

        # Collect raw (object, reference) pairs first - Value proxies stay
        # valid after Clear(), but we must not keep reusing `sel` for both
        # enumeration and the later per-face VisProperties queries at once.
        picked: list[tuple[Any, Any]] = []
        for i in range(1, sel.Count + 1):
            item = sel.Item(i)
            obj = item.Value
            try:
                ref = item.Reference
            except Exception:
                ref = part.CreateReferenceFromObject(obj)
            picked.append((obj, ref))
        sel.Clear()

        faces = []
        for index, (obj, ref) in enumerate(picked, start=1):
            entry: dict[str, Any] = {
                "index": index,
                "name": getattr(obj, "Name", f"Face.{index}"),
            }
            try:
                entry["brep_name"] = ref.DisplayName
            except Exception:
                pass

            try:
                measurable = spa.GetMeasurable(ref)
                entry["area_mm2"] = round(measurable.Area * 1e6, 4)
            except Exception as exc:
                entry["area_error"] = str(exc)

            try:
                components = [0.0] * 9
                measurable.GetPlane(components)
                origin = components[0:3]
                d1 = components[3:6]
                d2 = components[6:9]
                normal = (
                    d1[1] * d2[2] - d1[2] * d2[1],
                    d1[2] * d2[0] - d1[0] * d2[2],
                    d1[0] * d2[1] - d1[1] * d2[0],
                )
                length = math.sqrt(sum(v * v for v in normal))
                entry["planar"] = length > 1e-9
                if entry["planar"]:
                    entry["origin_mm"] = [round(v * 1000, 4) for v in origin]
                    entry["normal"] = [round(v / length, 6) for v in normal]
            except Exception:
                entry["planar"] = False

            try:
                sel.Clear()
                sel.Add(obj)
                vis = sel.VisProperties
                color_errors = []
                try:
                    # Strategy A: single 3-element array, like GetCOG/GetPlane's
                    # working single-SAFEARRAY-out-arg pattern elsewhere in this file.
                    rgb = [0, 0, 0]
                    status = vis.GetRealColor(rgb)
                    entry["color_rgb"] = [int(v) for v in rgb]
                    entry["color_status"] = status
                    entry["color_method"] = "array3"
                except Exception as exc_a:
                    color_errors.append(f"array3: {exc_a}")
                    try:
                        # Strategy B: zero-arg call, output params returned as a tuple
                        # (the pattern pycatia's wrapper assumes for early-bound COM).
                        res = vis.GetRealColor()
                        entry["color_rgb"] = [int(v) for v in res[:3]] if hasattr(res, "__len__") else res
                        entry["color_method"] = "zeroarg_tuple"
                    except Exception as exc_b:
                        color_errors.append(f"zeroarg_tuple: {exc_b}")
                        try:
                            # Strategy C: three separate ByRef VT_I4 VARIANTs.
                            r, g, b = _byref_long(), _byref_long(), _byref_long()
                            status = vis.GetRealColor(r, g, b)
                            entry["color_rgb"] = [int(r.value), int(g.value), int(b.value)]
                            entry["color_status"] = status
                            entry["color_method"] = "byref_scalars"
                        except Exception as exc_c:
                            color_errors.append(f"byref_scalars: {exc_c}")
                            entry["color_error"] = "; ".join(color_errors)
            except Exception as exc:
                entry["color_error"] = str(exc)
            finally:
                sel.Clear()

            faces.append(entry)

        if not faces:
            return "No faces found on the specified shape"
        return json.dumps(faces, indent=2, ensure_ascii=False)

    def _list_edges_geometry(self, feature_name: str | None) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        spa = self.conn.active_document.GetWorkbench("SPAWorkbench")
        shape = self._get_last_shape(feature_name)

        sel = self.conn.hso
        sel.Clear()
        sel.Add(shape)
        sel.Search("Topology.Edge,sel")

        picked: list[tuple[Any, Any]] = []
        for i in range(1, sel.Count + 1):
            item = sel.Item(i)
            obj = item.Value
            try:
                ref = item.Reference
            except Exception:
                ref = part.CreateReferenceFromObject(obj)
            picked.append((obj, ref))
        sel.Clear()

        edges = []
        for index, (obj, ref) in enumerate(picked, start=1):
            entry: dict[str, Any] = {
                "index": index,
                "name": getattr(obj, "Name", f"Edge.{index}"),
            }
            try:
                entry["brep_name"] = ref.DisplayName
            except Exception:
                pass

            try:
                measurable = spa.GetMeasurable(ref)
            except Exception as exc:
                entry["error"] = str(exc)
                edges.append(entry)
                continue

            try:
                length_raw = float(measurable.Length)
                entry["length_mm"] = round(self._curve_units_to_mm([length_raw])[0], 4)
            except Exception:
                pass

            try:
                coords = self._get_points_on_curve(measurable)
                if coords:
                    coords_mm = self._curve_units_to_mm(coords)
                    entry["start_mm"] = [round(v, 4) for v in coords_mm[0:3]]
                    entry["mid_mm"] = [round(v, 4) for v in coords_mm[3:6]]
                    entry["end_mm"] = [round(v, 4) for v in coords_mm[6:9]]
            except Exception:
                pass

            try:
                center = [0.0, 0.0, 0.0]
                measurable.GetCOG(center)
                center_mm = self._curve_units_to_mm([float(v) for v in center])
                if any(abs(v) > 1e-12 for v in center_mm):
                    entry["center_mm"] = [round(v, 4) for v in center_mm]
            except Exception:
                pass

            try:
                direction = [0.0] * 3
                measurable.GetDirection(direction)
                length = math.sqrt(sum(v * v for v in direction))
                entry["is_line"] = length > 1e-9
                if entry["is_line"]:
                    entry["direction"] = [round(v / length, 6) for v in direction]
            except Exception:
                entry["is_line"] = False

            edges.append(entry)

        if not edges:
            return "No edges found on the specified shape"
        return json.dumps(edges, indent=2, ensure_ascii=False)

    def _document_from_path(self, document_path: str) -> Any:
        import os

        from catia_mcp.paths import normalize_catia_path

        self.conn.ensure_connected()
        docs = self.conn.documents
        document_path = normalize_catia_path(document_path)
        target = os.path.normcase(os.path.abspath(document_path))
        for index in range(1, docs.Count + 1):
            doc = docs.Item(index)
            full_name = getattr(doc, "FullName", "") or ""
            if full_name and os.path.normcase(os.path.abspath(full_name)) == target:
                try:
                    doc.Activate()
                except Exception:
                    pass
                return doc
        doc = docs.Open(document_path)
        try:
            doc.Activate()
        except Exception:
            pass
        return doc

    def _com_type_name(self, obj: Any) -> str:
        try:
            return obj._oleobj_.GetTypeInfo().GetDocumentation(-1)[0]
        except Exception:
            return type(obj).__name__

    def _task06_debug_guides(self, document_path: str) -> str:
        doc = self._document_from_path(document_path)
        try:
            part = doc.Part
        except Exception as exc:
            raise RuntimeError(f"Document is not a CATPart: {document_path}") from exc

        spa = doc.GetWorkbench("SPAWorkbench")
        sel = doc.Selection
        output: dict[str, Any] = {
            "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
            "guides": [],
        }

        probe_properties = [
            "ElemToExtract",
            "Element",
            "Elements",
            "ObjectToExtract",
            "Support",
            "Curve",
            "Reference",
            "FirstElement",
            "SecondElement",
            "Parent",
        ]

        for guide_name in ("Curve.1", "Curve.2", "Curve.3"):
            entry: dict[str, Any] = {"name": guide_name}
            sel.Clear()
            sel.Search(f"Name={guide_name},all")
            entry["selection_count"] = sel.Count
            objects = []
            for idx in range(1, sel.Count + 1):
                selected = sel.Item(idx)
                obj = selected.Value
                ref = None
                try:
                    ref = selected.Reference
                except Exception:
                    try:
                        ref = part.CreateReferenceFromObject(obj)
                    except Exception:
                        ref = None
                obj_info: dict[str, Any] = {
                    "index": idx,
                    "name": getattr(obj, "Name", ""),
                    "type_name": self._com_type_name(obj),
                }
                if ref is not None:
                    try:
                        obj_info["reference_display_name"] = ref.DisplayName
                    except Exception:
                        pass
                    try:
                        measurable = spa.GetMeasurable(ref)
                        obj_info["length_raw"] = float(measurable.Length)
                    except Exception as exc:
                        obj_info["measure_error"] = str(exc)
                props: dict[str, Any] = {}
                for prop in probe_properties:
                    try:
                        value = getattr(obj, prop)
                    except Exception:
                        continue
                    try:
                        props[prop] = {
                            "name": getattr(value, "Name", ""),
                            "type_name": self._com_type_name(value),
                        }
                    except Exception:
                        props[prop] = repr(value)
                if props:
                    obj_info["properties"] = props
                objects.append(obj_info)
            entry["objects"] = objects

            if sel.Count:
                sel.Search("Topology.Edge,sel")
                subedges = []
                for edge_idx in range(1, sel.Count + 1):
                    selected = sel.Item(edge_idx)
                    obj = selected.Value
                    try:
                        ref = selected.Reference
                    except Exception:
                        ref = None
                    edge_info = {
                        "index": edge_idx,
                        "name": getattr(obj, "Name", ""),
                        "type_name": self._com_type_name(obj),
                    }
                    if ref is not None:
                        try:
                            edge_info["brep_name"] = ref.DisplayName
                        except Exception:
                            pass
                        try:
                            edge_info["length_raw"] = float(spa.GetMeasurable(ref).Length)
                        except Exception as exc:
                            edge_info["measure_error"] = str(exc)
                    subedges.append(edge_info)
                entry["subedges"] = subedges
            sel.Clear()
            output["guides"].append(entry)

        return json.dumps(output, indent=2, ensure_ascii=False)
