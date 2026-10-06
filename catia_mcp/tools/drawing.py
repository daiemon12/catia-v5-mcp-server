"""Drafting (Drawing) tools for CATIA V5.

Built from field-validated automation probes run on CATIA V5R20 by
contributor ESE3X: Drawing document creation, generative view
creation (Sheets / Views.Add / GenerativeBehavior / DefineFrontView /
Update) and view positioning are confirmed working through COM.

The dimensioning tools follow the MCP philosophy: the AI agent decides
where dimensions belong (list the view's 2D geometry, pick elements),
the server only executes the mechanical Add. Projection/section views
and title blocks are planned follow-ups.
"""

from __future__ import annotations

import re
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools.measurement import read_measurable_array

# DefineFrontView takes the two sheet-plane axis vectors expressed in the
# 3D part's coordinate system.
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
                    "and status (basic_2d or 3d_driven)."
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
                "name": "catia_drawing_add_view",
                "description": (
                    "Add a generative front view of an open Part to the "
                    "active Drawing's active sheet, projected on the chosen "
                    "plane, then update it. Create the drawing first with "
                    "catia_new_drawing. Experimental: field-validated on "
                    "V5R20 for front views; projection/section views are "
                    "planned."
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
                                "body's final shape (see catia_list_faces); "
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
        part_doc = self._find_part_document(args.get("part_name"))
        drawing = self._find_active_drawing()

        plane = (args.get("plane") or "xy").lower()
        if plane not in _PLANE_VECTORS:
            raise ValueError(f"Unknown plane '{plane}'. Use 'xy', 'yz', or 'zx'.")
        vx1, vy1, vz1, vx2, vy2, vz2 = _PLANE_VECTORS[plane]

        sheet = drawing.Sheets.ActiveSheet
        view = sheet.Views.Add(args.get("name") or "Front View")

        gb = view.GenerativeBehavior
        body_name = args.get("body_name")
        face_name = args.get("face")
        face_plane = None
        if face_name:
            face_plane = self._face_plane(part_doc, body_name, face_name)
        if body_name:
            # gb.Document accepts a Body and then draws that body only
            # (field-validated with a control view on V5R20).
            bodies = part_doc.Part.Bodies
            try:
                target_body = bodies.Item(body_name)
            except Exception:
                names = ", ".join(str(bodies.Item(i).Name) for i in range(1, bodies.Count + 1))
                raise RuntimeError(
                    f"No body named '{body_name}' in '{part_doc.Name}'. "
                    f"Top-level bodies: {names or 'none'}."
                )
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
        angle = args.get("angle")
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
        # arrays do not). Selection points zeroed: CATIA anchors on the
        # geometry; placement can be adjusted interactively.
        pt_coords = [0.0] * (2 * len(elems))
        dim = view.Dimensions.Add(code, elems, pt_coords, 0)

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
        plane = read_measurable_array(self.conn.app, measurable, "GetPlane", 9)
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
        try:
            drawing.Activate()
        except Exception:
            pass
        try:
            view.Activate()
        except Exception:
            pass
        sheet = drawing.Sheets.ActiveSheet
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
        import json as _json

        return _json.dumps(
            {"view": str(view.Name), "dimensions": self._dimension_rows(view)},
            indent=2,
        )
