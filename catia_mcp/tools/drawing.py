"""Drafting (Drawing) tools for CATIA V5.

Built from field-validated automation probes run on CATIA V5R20 by
contributor ESE3X: Drawing document creation, generative view
creation (Sheets / Views.Add / GenerativeBehavior / DefineFrontView /
Update) and view positioning are confirmed working through COM.

Dimensioning: CATIA never exposes the projected curves of generative
views to Automation (field-proven on V5R20), so generative views are
dimensioned from the part's 3D sketch constraints through
DrawingSheet.GenerateDimensions (the agent expresses design intent as
constraints, CATIA places the dimensions). The manual Add path only
works on 2D geometry drawn in the view. Projection, section and detail
views, text and tables are provided; frame/title-block generators are
the next step.
"""

from __future__ import annotations

import re
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools.measurement import read_measurable_array

# DefineFrontView takes the two sheet-plane axis vectors expressed in the
# 3D part's coordinate system.
# CatProjViewType (R20 automation enum, verified against the V5 reference
# binding): the projection of a view relative to its parent.
_PROJECTION_TYPES = {"right": 0, "left": 1, "top": 2, "bottom": 3, "rear": 4}

_PLANE_VECTORS = {
    "xy": (1, 0, 0, 0, 1, 0),
    "yz": (0, 1, 0, 0, 0, 1),
    "zx": (0, 0, 1, 1, 0, 0),
}


class DraftingTools:
    """Tools for CATIA V5 Drawing documents (generative drafting)."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_new_drawing",
                "description": (
                    "Create a new empty Drawing document (CATDrawing) for "
                    "generative drafting. The drawing becomes the active "
                    "document; the source Part stays open and is referenced "
                    "by catia_drawing_add_view."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_drawing_list_view_geometry",
                "description": (
                    "List the manually drawn 2D geometry of a drawing view "
                    "as indexed elements for catia_drawing_add_dimension. "
                    "Field-proven on V5R20: generated projection curves are "
                    "NOT exposed here (GeometricElements shows only the axis "
                    "and Factory2D items). To dimension generative views use "
                    "catia_drawing_generate_dimensions. Defaults to the last "
                    "view of the active sheet."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "view_name": {
                            "type": "string",
                            "description": "View to inspect (default: last view of the active sheet)",
                        },
                    },
                },
            },
            {
                "name": "catia_drawing_add_dimension",
                "description": (
                    "Add a dimension between one or two manually drawn 2D "
                    "elements (indices from catia_drawing_list_view_geometry). "
                    "Works on Factory2D geometry only (R20: generated curves "
                    "are not addressable); for generative views use "
                    "catia_drawing_generate_dimensions."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["distance", "length", "angle", "radius", "diameter"],
                            "description": (
                                "Dimension type. 'length'/'radius'/'diameter' "
                                "take one element; 'distance'/'angle' take two."
                            ),
                        },
                        "element_index_1": {
                            "type": "integer",
                            "description": "First element index from catia_drawing_list_view_geometry",
                        },
                        "element_index_2": {
                            "type": "integer",
                            "description": "Second element index (distance/angle)",
                        },
                        "view_name": {
                            "type": "string",
                            "description": "Target view (default: last view of the active sheet)",
                        },
                    },
                    "required": ["type", "element_index_1"],
                },
            },
            {
                "name": "catia_drawing_generate_dimensions",
                "description": (
                    "Generate associative dimensions on a generative view "
                    "from the part's 3D sketch constraints (one dimension per "
                    "distance/length/angle/radius/diameter constraint). This "
                    "is the only route that dimensions generated geometry in "
                    "CATIA V5 (field-proven on R20): add constraints with "
                    "catia_sketch_constraint, then call this. Reports the "
                    "dimensions with values; generated ones follow the 3D "
                    "model (status 3d_driven)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "view_name": {
                            "type": "string",
                            "description": "Target view (default: last view of the active sheet)",
                        },
                    },
                },
            },
            {
                "name": "catia_drawing_list_dimensions",
                "description": (
                    "List the dimensions of a drawing view with their values "
                    "and status (basic_2d or 3d_driven). Regenerates the view "
                    "first so 3d_driven values reflect the current part "
                    "(set refresh=false to skip)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "view_name": {
                            "type": "string",
                            "description": "View to inspect (default: last view of the active sheet)",
                        },
                        "refresh": {
                            "type": "boolean",
                            "description": "Regenerate the view before reading (default true)",
                        },
                    },
                },
            },
            {
                "name": "catia_drawing_projection_view",
                "description": (
                    "Add a projection view (right/left/top/bottom/rear) "
                    "derived from an existing generative view, placed next "
                    "to it at the same scale. DefineProjectionView with the "
                    "documented CatProjViewType enum."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["right", "left", "top", "bottom", "rear"],
                            "description": "Projection relative to the parent view",
                        },
                        "parent_view": {
                            "type": "string",
                            "description": "Parent view name (default: last view of the active sheet)",
                        },
                        "name": {"type": "string", "description": "New view name (default '<direction> view')"},
                        "gap": {
                            "type": "number",
                            "description": "Distance from the parent view in mm (default 100)",
                        },
                        "x": {"type": "number", "description": "Explicit X position in mm (overrides gap)"},
                        "y": {"type": "number", "description": "Explicit Y position in mm (overrides gap)"},
                    },
                    "required": ["direction"],
                },
            },
            {
                "name": "catia_drawing_section_view",
                "description": (
                    "Add a section view or section cut from a cutting "
                    "profile drawn as a polyline in the parent view's 2D "
                    "coordinates (mm). DefineSectionView per the V5 "
                    "reference: profile points, section type, profile type, "
                    "side to draw, parent view."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "profile": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Flat list [x1, y1, x2, y2, ...] of the cutting polyline in parent view coordinates (mm), at least two points",
                        },
                        "parent_view": {"type": "string", "description": "Parent view name (default: last view)"},
                        "section_type": {
                            "type": "string",
                            "enum": ["SectionView", "SectionCut"],
                            "description": "SectionView shows geometry behind the plane, SectionCut only the cut (default SectionView)",
                        },
                        "profile_type": {
                            "type": "string",
                            "enum": ["Offset", "Aligned"],
                            "description": "Cutting profile type (default Offset)",
                        },
                        "side": {
                            "type": "integer",
                            "enum": [0, 1],
                            "description": "Side to draw: 0 clockwise, 1 counterclockwise (default 1)",
                        },
                        "name": {"type": "string", "description": "New view name"},
                        "x": {"type": "number", "description": "X position in mm (default: parent x + 150)"},
                        "y": {"type": "number", "description": "Y position in mm (default: parent y)"},
                    },
                    "required": ["profile"],
                },
            },
            {
                "name": "catia_drawing_detail_view",
                "description": (
                    "Add a circular detail view of a region of the parent "
                    "view (center and radius in the parent view's 2D "
                    "coordinates, mm). DefineCircularDetailView."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "center_x": {"type": "number", "description": "Circle center X in parent view coordinates (mm)"},
                        "center_y": {"type": "number", "description": "Circle center Y in parent view coordinates (mm)"},
                        "radius": {"type": "number", "description": "Circle radius (mm)"},
                        "parent_view": {"type": "string", "description": "Parent view name (default: last view)"},
                        "scale": {"type": "number", "description": "Detail scale factor (default 2)"},
                        "name": {"type": "string", "description": "New view name"},
                        "x": {"type": "number", "description": "X position in mm (default: parent x + 150)"},
                        "y": {"type": "number", "description": "Y position in mm (default: parent y + 100)"},
                    },
                    "required": ["center_x", "center_y", "radius"],
                },
            },
            {
                "name": "catia_drawing_add_text",
                "description": (
                    "Add a text annotation to a drawing view at (x, y) mm in "
                    "the view's coordinate system (DrawingTexts.Add). Use the "
                    "sheet's Background view for title block text."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text content"},
                        "x": {"type": "number", "description": "X in mm (view coordinates)"},
                        "y": {"type": "number", "description": "Y in mm (view coordinates)"},
                        "view_name": {
                            "type": "string",
                            "description": "Target view (default: last view; use 'Background View' for frames and title blocks)",
                        },
                    },
                    "required": ["text", "x", "y"],
                },
            },
            {
                "name": "catia_drawing_add_table",
                "description": (
                    "Add a table to a drawing view (DrawingTables.Add) and "
                    "optionally fill its cells. Building block for title "
                    "blocks, revision tables and BOMs: pass 'cells' as rows "
                    "of strings, optional per-column widths, and the "
                    "Background View as target for sheet-level tables."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "Table X in mm (view coordinates)"},
                        "y": {"type": "number", "description": "Table Y in mm (view coordinates)"},
                        "rows": {"type": "integer", "description": "Number of rows"},
                        "columns": {"type": "integer", "description": "Number of columns"},
                        "row_height": {"type": "number", "description": "Row height in mm (default 8)"},
                        "column_width": {"type": "number", "description": "Column width in mm (default 40)"},
                        "cells": {
                            "type": "array",
                            "items": {"type": "array", "items": {"type": "string"}},
                            "description": "Optional cell contents, row-major, e.g. [[\"Part\", \"Qty\"], [\"Bracket\", \"2\"]]",
                        },
                        "column_widths": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Optional per-column widths in mm (0 = automatic)",
                        },
                        "view_name": {
                            "type": "string",
                            "description": "Target view (default: last view; use 'Background View' for title blocks)",
                        },
                    },
                    "required": ["x", "y", "rows", "columns"],
                },
            },
            {
                "name": "catia_drawing_add_view",
                "description": (
                    "Add a generative front view of an open Part to the "
                    "active Drawing's active sheet, projected on the chosen "
                    "plane or on a planar face, then update it. Create the "
                    "drawing first with catia_new_drawing; derive other "
                    "views with catia_drawing_projection_view / "
                    "section_view / detail_view. Field-validated on V5R20."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_name": {
                            "type": "string",
                            "description": (
                                "Open Part document to represent (e.g. "
                                "'Part1.CATPart'). Defaults to the only "
                                "open Part when unambiguous."
                            ),
                        },
                        "body_name": {
                            "type": "string",
                            "description": (
                                "Optional body to draw alone (e.g. 'PartBody' "
                                "or 'Body.2'); other bodies are excluded. "
                                "Field-validated on V5R20."
                            ),
                        },
                        "plane": {
                            "type": "string",
                            "enum": ["xy", "yz", "zx"],
                            "description": "Projection plane (default xy); ignored when 'face' is given",
                        },
                        "face": {
                            "type": "string",
                            "description": (
                                "Face-driven projection: 'Face.N' of the "
                                "body's final shape, as listed by "
                                "catia_list_faces run with the SAME body_name; "
                                "the view is projected on that planar face's "
                                "own plane, orientation-independent. "
                                "Field-proven on V5R20."
                            ),
                        },
                        "angle": {
                            "type": "number",
                            "description": "In-plane rotation of the view in degrees (default 0)",
                        },
                        "x": {
                            "type": "number",
                            "description": "View X position on the sheet in mm (default 300)",
                        },
                        "y": {
                            "type": "number",
                            "description": "View Y position on the sheet in mm (default 150)",
                        },
                        "name": {
                            "type": "string",
                            "description": "View name (default 'Front View')",
                        },
                    },
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_new_drawing":
                return self._new_drawing()
            case "catia_drawing_add_view":
                return self._add_view(arguments)
            case "catia_drawing_projection_view":
                return self._projection_view(arguments)
            case "catia_drawing_section_view":
                return self._section_view(arguments)
            case "catia_drawing_detail_view":
                return self._detail_view(arguments)
            case "catia_drawing_add_text":
                return self._add_text(arguments)
            case "catia_drawing_add_table":
                return self._add_table(arguments)
            case "catia_drawing_generate_dimensions":
                return self._generate_dimensions(arguments)
            case "catia_drawing_list_dimensions":
                return self._list_dimensions(arguments)
            case "catia_drawing_list_view_geometry":
                return self._list_view_geometry(arguments)
            case "catia_drawing_add_dimension":
                return self._add_dimension(arguments)
            case _:
                raise ValueError(f"Unknown drafting tool: {tool_name}")

    def _new_drawing(self) -> str:
        self.conn.ensure_connected()
        drawing = self.conn.documents.Add("Drawing")
        sheet = drawing.Sheets.ActiveSheet
        return (
            f"Drawing created: '{drawing.Name}' (active sheet '{sheet.Name}', "
            f"{drawing.Sheets.Count} sheet(s)). Use catia_drawing_add_view "
            "to project a part onto it."
        )

    def _find_part_document(self, part_name: str | None) -> Any:
        docs = self.conn.documents
        open_parts = []
        for i in range(1, docs.Count + 1):
            doc = docs.Item(i)
            try:
                doc_name = str(doc.Name)
            except Exception:
                continue
            if doc_name.lower().endswith(".catpart"):
                open_parts.append(doc)
                if part_name and doc_name == part_name:
                    return doc

        if part_name:
            names = ", ".join(str(d.Name) for d in open_parts) or "none"
            raise RuntimeError(
                f"No open Part named '{part_name}'. Open parts: {names}."
            )
        if len(open_parts) == 1:
            return open_parts[0]
        names = ", ".join(str(d.Name) for d in open_parts) or "none"
        raise RuntimeError(
            "Pass 'part_name' to pick the part to project. "
            f"Open parts: {names}."
        )

    def _find_active_drawing(self) -> Any:
        app = self.conn.app
        try:
            active = app.ActiveDocument
            if str(active.Name).lower().endswith(".catdrawing"):
                return active
        except Exception:
            pass
        docs = self.conn.documents
        drawings = []
        for i in range(1, docs.Count + 1):
            doc = docs.Item(i)
            try:
                if str(doc.Name).lower().endswith(".catdrawing"):
                    drawings.append(doc)
            except Exception:
                continue
        if len(drawings) == 1:
            return drawings[0]
        raise RuntimeError(
            "No active Drawing document. Run catia_new_drawing first."
        )

    def _add_view(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        app = self.conn.app
        part_doc = self._find_part_document(args.get("part_name"))
        drawing = self._find_active_drawing()

        plane = (args.get("plane") or "xy").lower()
        if plane not in _PLANE_VECTORS:
            raise ValueError(f"Unknown plane '{plane}'. Use 'xy', 'yz', or 'zx'.")
        vx1, vy1, vz1, vx2, vy2, vz2 = _PLANE_VECTORS[plane]

        # Resolve every input before touching the sheet, so a bad argument
        # never leaves an empty unconfigured view behind.
        body_name = args.get("body_name")
        target_body = None
        if body_name:
            bodies = part_doc.Part.Bodies
            try:
                target_body = bodies.Item(body_name)
            except Exception:
                names = ", ".join(str(bodies.Item(i).Name) for i in range(1, bodies.Count + 1))
                raise RuntimeError(
                    f"No body named '{body_name}' in '{part_doc.Name}'. "
                    f"Top-level bodies: {names or 'none'}."
                )
        face_name = args.get("face")
        face_plane = None
        if face_name:
            # Face enumeration and GetPlane run with the PART active, as in
            # the proven run; the drawing is re-activated afterwards.
            try:
                part_doc.Activate()
            except Exception:
                pass
            try:
                face_plane = self._face_plane(part_doc, body_name, face_name)
            finally:
                try:
                    drawing.Activate()
                except Exception:
                    pass
        angle = args.get("angle")

        sheet = drawing.Sheets.ActiveSheet
        view = sheet.Views.Add(args.get("name") or "Front View")

        gb = view.GenerativeBehavior
        if target_body is not None:
            # gb.Document accepts a Body and then draws that body only
            # (field-validated with a control view on V5R20).
            gb.Document = target_body
            source = f"{part_doc.Name} / {body_name}"
        else:
            gb.Document = part_doc
            source = str(part_doc.Name)
        if face_plane is not None:
            # SetProjectionPlane takes the two in-plane direction vectors
            # (normal = V1 x V2), field-corrected and proven on V5R20.
            gb.SetProjectionPlane(
                face_plane[3], face_plane[4], face_plane[5],
                face_plane[6], face_plane[7], face_plane[8],
            )
            projection = f"plane of {face_name}"
        else:
            gb.DefineFrontView(vx1, vy1, vz1, vx2, vy2, vz2)
            projection = f"{plane.upper()} projection"

        view.x = args.get("x", 300)
        view.y = args.get("y", 150)
        if angle:
            import math as _math

            view.Angle = _math.radians(angle)
        gb.Update()

        self.conn.refresh_display()
        return (
            f"View '{view.Name}' of '{source}' added to sheet "
            f"'{sheet.Name}' ({projection}) and updated."
        )

    # CatDimType is 0-based in R20 (enum_CatDimType, 21 values, verified
    # live: catDimRadius = 5): Distance=0, DistanceOffset=1, Length=2,
    # LengthCurvilinear=3, Angle=4, Radius=5, RadiusTangent=6,
    # RadiusCylinder=7, RadiusEdge=8, Diameter=9, ...
    _DIM_TYPES = {
        "distance": 0,
        "length": 2,
        "angle": 4,
        "radius": 5,
        "diameter": 9,
    }

    def _find_view(self, view_name: str | None) -> Any:
        drawing = self._find_active_drawing()
        views = drawing.Sheets.ActiveSheet.Views
        if view_name:
            for i in range(1, views.Count + 1):
                v = views.Item(i)
                if str(v.Name) == view_name:
                    return v
            names = ", ".join(str(views.Item(i).Name) for i in range(1, views.Count + 1))
            raise RuntimeError(f"No view named '{view_name}'. Views: {names}.")
        if views.Count < 3:
            raise RuntimeError(
                "The active sheet has no user view yet (only Main/Background). "
                "Add one with catia_drawing_add_view."
            )
        # Items 1 and 2 are the sheet's Main and Background views; the last
        # item is the most recently added user view.
        return views.Item(views.Count)

    def _list_view_geometry(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        view = self._find_view(args.get("view_name"))
        geoms = view.GeometricElements
        elements = []
        for i in range(1, geoms.Count + 1):
            try:
                name = str(geoms.Item(i).Name)
            except Exception:
                name = "<unnamed>"
            elements.append({"index": i, "name": name})
        if not elements:
            return (
                f"View '{view.Name}' exposes no 2D geometry. For a "
                "generative view, make sure it was updated "
                "(catia_drawing_add_view updates automatically)."
            )
        import json as _json

        return _json.dumps(
            {"view": str(view.Name), "elements": elements}, indent=2
        )

    def _add_dimension(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        dim_type = args["type"]
        code = self._DIM_TYPES.get(dim_type)
        if code is None:
            raise ValueError(
                f"Unknown dimension type '{dim_type}'. Use one of: "
                + ", ".join(self._DIM_TYPES)
            )
        view = self._find_view(args.get("view_name"))
        geoms = view.GeometricElements

        idx1 = args["element_index_1"]
        idx2 = args.get("element_index_2")
        two_element_types = ("distance", "angle")
        if dim_type in two_element_types and idx2 is None:
            raise ValueError(f"'{dim_type}' needs element_index_2 as well.")

        elems = [geoms.Item(idx1)]
        if idx2 is not None:
            elems.append(geoms.Item(idx2))

        # DrawingDimensions.Add(iTypeDim, iGeomElem, iPtCoordElem, iLineRep).
        # Input safearrays marshal fine through late-bound COM (only in/out
        # arrays do not). Field-proven form on V5R20: view activated first,
        # zeroed selection points, iLineRep = 3 (catDimAuto, CATIA places
        # the dimension line).
        try:
            view.Activate()
        except Exception:
            pass
        pt_coords = [0.0] * (2 * len(elems))
        dim = view.Dimensions.Add(code, elems, pt_coords, 3)

        self.conn.refresh_display()
        return (
            f"{dim_type.capitalize()} dimension '{dim.Name}' added on view "
            f"'{view.Name}' (associative value computed by CATIA)."
        )

    def _face_plane(self, part_doc: Any, body_name: str | None, face_name: str) -> list[float]:
        """Return the 9 GetPlane components (origin, dir1, dir2) of Face.N of
        the body's final shape, through the SystemService.Evaluate detour."""
        m = re.match(r"^Face\.(\d+)$", face_name or "")
        if not m:
            raise ValueError(f"'face' must look like 'Face.3' (from catia_list_faces), got '{face_name}'.")
        idx = int(m.group(1))
        part = part_doc.Part
        body = part.Bodies.Item(body_name) if body_name else part.MainBody
        if body.Shapes.Count == 0:
            raise RuntimeError("The body has no solid shape to take a face from.")
        last_shape = body.Shapes.Item(body.Shapes.Count)
        sel = part_doc.Selection
        try:
            sel.Clear()
            sel.Add(last_shape)
            sel.Search("Topology.Face,sel")
            if idx < 1 or idx > sel.Count:
                raise RuntimeError(
                    f"{face_name} is out of range: the final shape exposes "
                    f"{sel.Count} face(s)."
                )
            ref = sel.Item(idx).Reference
        finally:
            try:
                sel.Clear()
            except Exception:
                pass
        spa = part_doc.GetWorkbench("SPAWorkbench")
        measurable = spa.GetMeasurable(ref)
        try:
            plane = read_measurable_array(self.conn.app, measurable, "GetPlane", 9)
        except Exception as e:
            raise RuntimeError(
                f"{face_name} has no plane (GetPlane failed: {e}). Only "
                "planar faces can drive a projection; pick another face."
            )
        if not any(abs(v) > 0 for v in plane):
            raise RuntimeError(
                f"{face_name} returned no usable plane (not planar?). Pick a "
                "planar face."
            )
        return plane

    def _dimension_rows(self, view: Any) -> list[dict[str, Any]]:
        rows = []
        dims = view.Dimensions
        for j in range(1, dims.Count + 1):
            d = dims.Item(j)
            row: dict[str, Any] = {"name": str(d.Name)}
            try:
                row["value"] = round(float(d.GetValue().Value), 4)
            except Exception:
                row["value"] = None
            try:
                row["dim_type"] = int(d.DimType)
            except Exception:
                pass
            try:
                # 6 = catBasic (manual 2D parents), 7 = cat3DDrivableDim
                # (generated from a 3D constraint, follows the part).
                status = int(d.DimStatus)
                row["status"] = {6: "basic_2d", 7: "3d_driven"}.get(status, status)
            except Exception:
                pass
            rows.append(row)
        return rows

    def _generate_dimensions(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        drawing = self._find_active_drawing()
        view = self._find_view(args.get("view_name"))
        before = view.Dimensions.Count

        # Field-proven on V5R20: DrawingSheet.GenerateDimensions() is a
        # silent no-op unless the DRAWING is the active document and the
        # view is active. One dimension per supported 3D constraint
        # (distance/length/angle/radius/diameter), idempotent on re-run.
        app = self.conn.app
        try:
            drawing.Activate()
        except Exception:
            pass
        try:
            view.Activate()
        except Exception:
            pass
        sheet = drawing.Sheets.ActiveSheet
        active_doc = str(app.ActiveDocument.Name)
        if active_doc != str(drawing.Name):
            raise RuntimeError(
                f"Could not activate drawing '{drawing.Name}' (active "
                f"document is '{active_doc}'); GenerateDimensions would "
                "silently do nothing. Bring the drawing window to front and "
                "retry."
            )
        try:
            active_view = str(sheet.Views.ActiveView.Name)
        except Exception:
            active_view = None
        if active_view is not None and active_view != str(view.Name):
            raise RuntimeError(
                f"Could not activate view '{view.Name}' (active view is "
                f"'{active_view}'); retry or pass view_name explicitly."
            )
        sheet.GenerateDimensions()
        self.conn.refresh_display()

        after = view.Dimensions.Count
        rows = self._dimension_rows(view)
        created = max(0, after - before)
        import json as _json

        if created == 0:
            return _json.dumps({
                "view": str(view.Name),
                "generated": 0,
                "dimensions": rows,
                "note": (
                    "No dimension was generated. Causes: the part's sketches "
                    "carry no supported constraints (use "
                    "catia_sketch_constraint: distance, length/radius, angle), "
                    "or they were already generated (idempotent)."
                ),
            }, indent=2)
        return _json.dumps({
            "view": str(view.Name),
            "generated": created,
            "dimensions": rows,
        }, indent=2)

    def _list_dimensions(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        view = self._find_view(args.get("view_name"))
        # 3d_driven dimensions only follow the part after the generative
        # view is regenerated (field-proven: part.Update alone leaves the
        # old value). Refresh before reading.
        if args.get("refresh", True):
            try:
                view.GenerativeBehavior.Update()
            except Exception:
                pass
        import json as _json

        return _json.dumps(
            {"view": str(view.Name), "dimensions": self._dimension_rows(view)},
            indent=2,
        )

    def _find_view_any(self, view_name: str | None) -> Any:
        """Resolve a view for annotations: by name (Main/Background views
        included), else the last user view, else the Background View so
        title blocks can be filled on an otherwise empty sheet."""
        if view_name:
            return self._find_view(view_name)
        views = self._find_active_drawing().Sheets.ActiveSheet.Views
        if views.Count >= 3:
            return views.Item(views.Count)
        return views.Item(2) if views.Count >= 2 else views.Item(1)

    def _parent_generative_view(self, parent_name: str | None) -> Any:
        parent = self._find_view(parent_name)
        try:
            generative = bool(parent.IsGenerative())
        except Exception:
            generative = True  # cannot tell; let CATIA decide
        if not generative:
            raise ValueError(
                f"'{parent.Name}' is not a generative view; derive from a "
                "view created by catia_drawing_add_view."
            )
        return parent

    def _create_derived_view(self, sheet: Any, parent: Any, name: str, define: Any) -> Any:
        """Add a view, link it to the parent's 3D source, run the Define*
        call; remove the view again if anything fails so no empty orphan
        is left on the sheet (and becomes the next default parent)."""
        view = sheet.Views.Add(name)
        try:
            linked = False
            try:
                view.GenerativeBehavior.Document = parent.GenerativeBehavior.Document
                linked = True
            except Exception:
                try:
                    parent.GenerativeLinks.CopyLinksTo(view.GenerativeLinks)
                    linked = True
                except Exception:
                    pass
            if not linked:
                raise RuntimeError(
                    "Could not carry the parent's 3D link to the new view; "
                    "it would generate no geometry."
                )
            define(view)
            return view
        except Exception:
            try:
                sheet.Views.Remove(view.Name)
            except Exception:
                pass
            raise

    @staticmethod
    def _parent_placement(parent: Any) -> tuple[float, float, float]:
        try:
            return float(parent.x), float(parent.y), float(parent.Scale)
        except Exception:
            return 0.0, 0.0, 1.0

    @staticmethod
    def _place(view: Any, x: float, y: float, scale: float | None = None) -> float | None:
        applied = None
        if scale:
            try:
                view.Scale = scale
                applied = float(view.Scale)
            except Exception:
                applied = None
        view.x = x
        view.y = y
        return applied

    def _projection_view(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        direction = str(args["direction"]).lower()
        if direction not in _PROJECTION_TYPES:
            raise ValueError(f"Unknown direction '{direction}'. Use right, left, top, bottom or rear.")
        gap = float(args.get("gap", 100.0))
        drawing = self._find_active_drawing()
        sheet = drawing.Sheets.ActiveSheet
        parent = self._parent_generative_view(args.get("parent_view"))

        # Placement follows the sheet's projection method: third angle puts
        # the right view to the right of the front view, first angle (the
        # ISO default) puts it to the left. CatSheetProjectionMethod:
        # 0 = first angle, 1 = third angle.
        try:
            first_angle = int(sheet.ProjectionMethod) == 0
        except Exception:
            first_angle = False
        sign = -1.0 if first_angle else 1.0
        offsets = {
            "right": (sign * gap, 0.0), "left": (-sign * gap, 0.0),
            "top": (0.0, sign * gap), "bottom": (0.0, -sign * gap),
            "rear": (2 * sign * gap, 0.0),
        }
        dx, dy = offsets[direction]
        px, py, pscale = self._parent_placement(parent)

        def define(view: Any) -> None:
            view.GenerativeBehavior.DefineProjectionView(
                parent.GenerativeBehavior, _PROJECTION_TYPES[direction]
            )

        view = self._create_derived_view(sheet, parent, args.get("name") or f"{direction} view", define)
        self._place(view, args.get("x", px + dx), args.get("y", py + dy), pscale)
        view.GenerativeBehavior.Update()
        self.conn.refresh_display()
        method = "first angle" if first_angle else "third angle"
        return (
            f"Projection view '{view.Name}' ({direction}) of '{parent.Name}' "
            f"added to sheet '{sheet.Name}' ({method} layout) and updated."
        )

    def _section_view(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        profile = [float(v) for v in args["profile"]]
        if len(profile) < 4 or len(profile) % 2:
            raise ValueError("profile must be a flat list [x1, y1, x2, y2, ...] with at least two points")
        section_type = args.get("section_type") or "SectionView"
        profile_type = args.get("profile_type") or "Offset"
        if section_type not in ("SectionView", "SectionCut"):
            raise ValueError("section_type must be 'SectionView' or 'SectionCut'")
        if profile_type not in ("Offset", "Aligned"):
            raise ValueError("profile_type must be 'Offset' or 'Aligned'")
        side = int(args.get("side", 1))
        if side not in (0, 1):
            raise ValueError("side must be 0 (clockwise) or 1 (counterclockwise)")
        drawing = self._find_active_drawing()
        sheet = drawing.Sheets.ActiveSheet
        parent = self._parent_generative_view(args.get("parent_view"))
        px, py, pscale = self._parent_placement(parent)

        def define(view: Any) -> None:
            # DefineSectionView(iProfile, iSectionType, iProfileType,
            # iSideToDraw, iParentGB); the profile is an input safearray.
            view.GenerativeBehavior.DefineSectionView(
                profile, section_type, profile_type, side, parent.GenerativeBehavior
            )

        view = self._create_derived_view(sheet, parent, args.get("name") or "section view", define)
        self._place(view, args.get("x", px + 150.0), args.get("y", py), pscale)
        view.GenerativeBehavior.Update()
        self.conn.refresh_display()
        return (
            f"{section_type} '{view.Name}' from '{parent.Name}' added to sheet "
            f"'{sheet.Name}' ({profile_type}, {len(profile) // 2} profile points) and updated."
        )

    def _detail_view(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        cx, cy, radius = float(args["center_x"]), float(args["center_y"]), float(args["radius"])
        if radius <= 0:
            raise ValueError("radius must be positive")
        factor = float(args.get("scale", 2.0))
        drawing = self._find_active_drawing()
        sheet = drawing.Sheets.ActiveSheet
        parent = self._parent_generative_view(args.get("parent_view"))
        px, py, pscale = self._parent_placement(parent)

        def define(view: Any) -> None:
            view.GenerativeBehavior.DefineCircularDetailView(cx, cy, radius, parent.GenerativeBehavior)

        view = self._create_derived_view(sheet, parent, args.get("name") or "detail view", define)
        applied = self._place(view, args.get("x", px + 150.0), args.get("y", py + 100.0), factor * pscale)
        view.GenerativeBehavior.Update()
        self.conn.refresh_display()
        scale_note = f"scale {applied:g}" if applied else "scale unchanged (CATIA kept the parent scale)"
        return (
            f"Detail view '{view.Name}' of '{parent.Name}' (r={radius} mm at "
            f"({cx}, {cy}), {scale_note}) added."
        )

    def _add_text(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        view = self._find_view_any(args.get("view_name"))
        text = view.Texts.Add(str(args["text"]), float(args["x"]), float(args["y"]))
        self.conn.refresh_display()
        return f"Text '{text.Name}' added to view '{view.Name}' at ({args['x']}, {args['y']}) mm."

    def _add_table(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        view = self._find_view_any(args.get("view_name"))
        rows, cols = int(args["rows"]), int(args["columns"])
        if rows < 1 or cols < 1:
            raise ValueError("rows and columns must be at least 1")
        table = view.Tables.Add(
            float(args["x"]), float(args["y"]), rows, cols,
            float(args.get("row_height", 8.0)), float(args.get("column_width", 40.0)),
        )
        widths = args.get("column_widths") or []
        for c, w in enumerate(widths[:cols], start=1):
            table.SetColumnSize(c, float(w))
        filled = 0
        cells = args.get("cells") or []
        for r, row in enumerate(cells[:rows], start=1):
            for c, value in enumerate(list(row)[:cols], start=1):
                if value is None or value == "":
                    continue
                table.SetCellString(r, c, str(value))
                filled += 1
        self.conn.refresh_display()
        return (
            f"Table '{table.Name}' ({rows}x{cols}) added to view '{view.Name}' "
            f"at ({args['x']}, {args['y']}) mm, {filled} cell(s) filled."
        )
