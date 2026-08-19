"""Part Design tools for CATIA V5.

3D feature creation: Pad, Pocket, Fillet, Chamfer, Shaft, Groove, Hole,
RectPattern, CircPattern, Mirror, Rib, Slot, Shell, Thickness, Draft.
"""

from __future__ import annotations

import json
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools._geometry import GeometryContext, REF_SCHEMA, set_revolution_angle


class PartDesignTools:
    """Tools for 3D Part Design features in CATIA V5."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self.geo = GeometryContext(connection)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_pad",
                "description": (
                    "Create a Pad (extrusion) from the last sketch. "
                    "Extrudes a 2D profile into a 3D solid along the normal to the sketch plane."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "height": {
                            "type": "number",
                            "description": "Extrusion height/depth in mm",
                        },
                        "direction": {
                            "type": "string",
                            "description": "Extrusion direction: 'normal' (default), 'reverse', 'both'",
                            "enum": ["normal", "reverse", "both"],
                            "default": "normal",
                        },
                        "symmetric": {
                            "type": "boolean",
                            "description": "If true, extrude equally on both sides (total = height)",
                            "default": False,
                        },
                        "sketch_name": {
                            "type": "string",
                            "description": "Name of sketch to use. If not specified, uses the last created sketch.",
                        },
                    },
                    "required": ["height"],
                },
            },
            {
                "name": "catia_pocket",
                "description": (
                    "Create a Pocket (cut extrusion) from the last sketch. "
                    "Removes material by extruding a 2D profile inward."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "depth": {
                            "type": "number",
                            "description": "Cut depth in mm",
                        },
                        "direction": {
                            "type": "string",
                            "description": (
                                "Cut direction: 'normal', 'reverse', or 'both' "
                                "(symmetric — cuts depth on each side of the sketch "
                                "plane; use for through-holes when unsure which side "
                                "the material is on)."
                            ),
                            "enum": ["normal", "reverse", "both"],
                            "default": "normal",
                        },
                        "symmetric": {
                            "type": "boolean",
                            "description": "Cut equally on both sides of the sketch plane (same as direction='both').",
                            "default": False,
                        },
                        "sketch_name": {
                            "type": "string",
                            "description": "Name of sketch to use. If not specified, uses the last sketch.",
                        },
                    },
                    "required": ["depth"],
                },
            },
            {
                "name": "catia_shaft",
                "description": (
                    "Create a Shaft (revolution) from the last sketch. "
                    "Revolves a 2D profile around an axis to create a solid of revolution. "
                    "The sketch must contain a line to use as the revolution axis."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "angle": {
                            "type": "number",
                            "description": "Revolution angle in degrees (default: 360 for full revolution)",
                            "default": 360,
                        },
                        "sketch_name": {
                            "type": "string",
                            "description": "Name of sketch to use.",
                        },
                    },
                },
            },
            {
                "name": "catia_groove",
                "description": (
                    "Create a Groove (revolution cut). "
                    "Removes material by revolving a 2D profile around an axis."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "angle": {
                            "type": "number",
                            "description": "Revolution angle in degrees (default: 360)",
                            "default": 360,
                        },
                        "sketch_name": {
                            "type": "string",
                            "description": "Name of sketch to use.",
                        },
                    },
                },
            },
            {
                "name": "catia_fillet",
                "description": (
                    "Add a fillet (rounded edge) to one or more edges of the current solid. "
                    "Specify the radius and the edge names or feature to fillet."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "radius": {
                            "type": "number",
                            "description": "Fillet radius in mm",
                        },
                        "edge_name": {
                            "type": "string",
                            "description": (
                                "Name of the edge to fillet (e.g., 'Edge.1'). "
                                "Use catia_list_edges to find edge names."
                            ),
                        },
                        "edge": REF_SCHEMA,
                    },
                    "required": ["radius"],
                },
            },
            {
                "name": "catia_fillet_edges",
                "description": (
                    "Add one constant-radius edge fillet to multiple topological edges "
                    "of a named feature, selected by Topology.Edge search indices."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "radius": {
                            "type": "number",
                            "description": "Fillet radius in mm",
                        },
                        "edge_indices": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1},
                            "minItems": 1,
                            "description": "Topology.Edge indices on the target feature",
                        },
                        "feature": {
                            "type": "string",
                            "description": "Feature to enumerate edges from (default: last PartBody shape)",
                        },
                        "document_path": {
                            "type": "string",
                            "description": "Optional CATPart path to activate/open before applying the fillet",
                        },
                        "name": {
                            "type": "string",
                            "description": "Optional name for the fillet feature",
                        },
                        "save": {
                            "type": "boolean",
                            "description": "Save the document after successful update (default false)",
                            "default": False,
                        },
                        "propagation": {
                            "type": "string",
                            "description": "Fillet edge propagation mode: none or tangent (default none)",
                            "enum": ["none", "tangent"],
                            "default": "none",
                        },
                    },
                    "required": ["radius", "edge_indices"],
                },
            },
            {
                "name": "catia_probe_fillet_edges",
                "description": (
                    "Probe whether individual topological edges can accept a temporary "
                    "constant-radius fillet. Temporary features are deleted and the "
                    "document is not saved."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "document_path": {"type": "string"},
                        "feature": {"type": "string"},
                        "radius": {"type": "number"},
                        "edge_indices": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1},
                            "minItems": 1,
                        },
                        "propagation": {
                            "type": "string",
                            "enum": ["none", "tangent"],
                            "default": "none",
                        },
                    },
                    "required": ["document_path", "radius", "edge_indices"],
                },
            },
            {
                "name": "catia_face_fillet_from_edges",
                "description": (
                    "Create face fillets between the two faces adjacent to each selected "
                    "topological edge index."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "document_path": {"type": "string"},
                        "feature": {"type": "string"},
                        "radius": {"type": "number"},
                        "edge_indices": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1},
                            "minItems": 1,
                        },
                        "name_prefix": {"type": "string", "default": "FaceFillet"},
                        "save": {"type": "boolean", "default": False},
                    },
                    "required": ["document_path", "radius", "edge_indices"],
                },
            },
            {
                "name": "catia_chamfer",
                "description": "Add a chamfer (beveled edge) to an edge of the current solid.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "length": {
                            "type": "number",
                            "description": "Chamfer length in mm",
                        },
                        "angle": {
                            "type": "number",
                            "description": "Chamfer angle in degrees (default: 45)",
                            "default": 45,
                        },
                        "edge_name": {
                            "type": "string",
                            "description": "Name of the edge to chamfer",
                        },
                    },
                    "required": ["length"],
                },
            },
            {
                "name": "catia_hole",
                "description": (
                    "Create a Hole feature at a point in the active sketch. "
                    "Supports simple, tapered, counterbored, and countersunk holes."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "diameter": {
                            "type": "number",
                            "description": "Hole diameter in mm",
                        },
                        "depth": {
                            "type": "number",
                            "description": "Hole depth in mm",
                        },
                        "type": {
                            "type": "string",
                            "description": "Hole type: 'simple', 'counterbored', 'countersunk', 'tapered'",
                            "enum": ["simple", "counterbored", "countersunk", "tapered"],
                            "default": "simple",
                        },
                        "threaded": {
                            "type": "boolean",
                            "description": "Whether to add threading (default: false)",
                            "default": False,
                        },
                        "sketch_name": {
                            "type": "string",
                            "description": "Sketch containing the hole center point",
                        },
                    },
                    "required": ["diameter", "depth"],
                },
            },
            {
                "name": "catia_rect_pattern",
                "description": (
                    "Create a Rectangular Pattern of the last feature. "
                    "Duplicates a feature in a grid along two directions."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "dir1_count": {
                            "type": "integer",
                            "description": "Number of instances in first direction",
                        },
                        "dir1_spacing": {
                            "type": "number",
                            "description": "Spacing in first direction (mm)",
                        },
                        "dir2_count": {
                            "type": "integer",
                            "description": "Number of instances in second direction (default: 1)",
                            "default": 1,
                        },
                        "dir2_spacing": {
                            "type": "number",
                            "description": "Spacing in second direction (mm)",
                            "default": 0,
                        },
                        "feature_name": {
                            "type": "string",
                            "description": "Name of the feature to pattern. Defaults to last feature.",
                        },
                    },
                    "required": ["dir1_count", "dir1_spacing"],
                },
            },
            {
                "name": "catia_circ_pattern",
                "description": (
                    "Create a Circular Pattern of the last feature. "
                    "Duplicates a feature around a central axis."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Number of instances around the circle",
                        },
                        "angular_spacing": {
                            "type": "number",
                            "description": "Angular spacing in degrees (default: equal spacing = 360/count)",
                        },
                        "feature_name": {
                            "type": "string",
                            "description": "Feature to pattern. Defaults to last feature.",
                        },
                    },
                    "required": ["count"],
                },
            },
            {
                "name": "catia_mirror",
                "description": (
                    "Mirror a feature or body about a plane. "
                    "Creates a symmetric copy of the geometry."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "plane": {
                            "type": "string",
                            "description": "Mirror plane: 'xy', 'yz', or 'zx'",
                            "enum": ["xy", "yz", "zx"],
                        },
                        "feature_name": {
                            "type": "string",
                            "description": "Feature to mirror. Defaults to last feature.",
                        },
                    },
                    "required": ["plane"],
                },
            },
            {
                "name": "catia_shell",
                "description": (
                    "Create a Shell feature: hollows out a solid leaving walls of specified thickness. "
                    "Optionally remove faces to create openings."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "thickness": {
                            "type": "number",
                            "description": "Wall thickness in mm",
                        },
                        "faces_to_remove": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Names of faces to remove (create openings). E.g., ['Face.1']",
                        },
                    },
                    "required": ["thickness"],
                },
            },
            {
                "name": "catia_draft",
                "description": (
                    "Add a Draft Angle to faces for mold-release purposes. "
                    "Tapers faces by a given angle relative to a pulling direction."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "angle": {
                            "type": "number",
                            "description": "Draft angle in degrees",
                        },
                        "face_name": {
                            "type": "string",
                            "description": "Name of the face to draft",
                        },
                        "pulling_direction": {
                            "type": "string",
                            "description": "Pulling direction plane: 'xy', 'yz', 'zx'",
                            "enum": ["xy", "yz", "zx"],
                            "default": "xy",
                        },
                    },
                    "required": ["angle"],
                },
            },
            {
                "name": "catia_thickness",
                "description": (
                    "Add or remove thickness from faces of a solid. "
                    "Offsets faces inward or outward."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "offset": {
                            "type": "number",
                            "description": "Thickness offset in mm (positive = outward, negative = inward)",
                        },
                        "face_name": {
                            "type": "string",
                            "description": "Name of the face to offset",
                        },
                    },
                    "required": ["offset"],
                },
            },
            {
                "name": "catia_list_features",
                "description": "List all features in the active Part Body with their names and types.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_list_edges",
                "description": "List all edges of the active solid body with their names for use with fillet/chamfer.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_pad":
                return self._pad(arguments)
            case "catia_pocket":
                return self._pocket(arguments)
            case "catia_shaft":
                return self._shaft(arguments)
            case "catia_groove":
                return self._groove(arguments)
            case "catia_fillet":
                return self._fillet(arguments)
            case "catia_fillet_edges":
                return self._fillet_edges(arguments)
            case "catia_probe_fillet_edges":
                return self._probe_fillet_edges(arguments)
            case "catia_face_fillet_from_edges":
                return self._face_fillet_from_edges(arguments)
            case "catia_chamfer":
                return self._chamfer(arguments)
            case "catia_hole":
                return self._hole(arguments)
            case "catia_rect_pattern":
                return self._rect_pattern(arguments)
            case "catia_circ_pattern":
                return self._circ_pattern(arguments)
            case "catia_mirror":
                return self._mirror(arguments)
            case "catia_shell":
                return self._shell(arguments)
            case "catia_draft":
                return self._draft(arguments)
            case "catia_thickness":
                return self._thickness(arguments)
            case "catia_list_features":
                return self._list_features()
            case "catia_list_edges":
                return self._list_edges()
            case _:
                raise ValueError(f"Unknown part design tool: {tool_name}")

    def _get_last_sketch(self, sketch_name: str | None = None) -> Any:
        """Get a sketch by name or the last sketch in the body."""
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sketches = body.Sketches

        if sketch_name:
            return sketches.Item(sketch_name)

        # Prefer the sketch the sketcher most recently created. Sketches.Item(Count)
        # is unreliable: once a sketch is absorbed into a feature, the collection's
        # index order no longer matches creation order, so Item(Count) can return
        # an earlier sketch (observed: a hub pad silently reused the web sketch).
        tracked = getattr(self.conn, "active_sketch_name", None)
        if tracked:
            try:
                return sketches.Item(tracked)
            except Exception:
                pass  # fall through if it was consumed/renamed

        # Fallback: last sketch by collection index.
        if sketches.Count == 0:
            raise RuntimeError("No sketches found in the active body. Create a sketch first.")
        return sketches.Item(sketches.Count)

    def _get_last_shape(self, feature_name: str | None = None) -> Any:
        """Get a shape/feature by name or the last one in the body."""
        body = self.conn.get_active_part_body()
        shapes = body.Shapes

        if feature_name:
            return shapes.Item(feature_name)

        if shapes.Count == 0:
            raise RuntimeError("No features found in the active body.")
        return shapes.Item(shapes.Count)

    def _pad(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        sketch = self._get_last_sketch(args.get("sketch_name"))
        height = args["height"]
        direction = args.get("direction", "normal")
        symmetric = args.get("symmetric", False)

        pad = sf.AddNewPad(sketch, height)

        if symmetric:
            pad.IsSymmetric = True
        elif direction == "reverse":
            pad.DirectionOrientation = 1  # catReverse
        elif direction == "both":
            pad.IsSymmetric = True

        part.UpdateObject(pad)
        self.conn.refresh_display()
        return f"Pad created: {height} mm ({direction}). Feature: '{pad.Name}'"

    def _pocket(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        sketch = self._get_last_sketch(args.get("sketch_name"))
        depth = args["depth"]
        direction = args.get("direction", "normal")
        symmetric = args.get("symmetric", False) or direction == "both"

        pocket = sf.AddNewPocket(sketch, depth)

        # AddNewPocket's default cut direction is the sketch's negative normal;
        # when material sits on the positive-normal side, a one-directional cut
        # removes nothing. A symmetric pocket cuts `depth` on both sides, so a
        # through-feature always intersects the solid regardless of pad side.
        if symmetric:
            pocket.IsSymmetric = True
        elif direction == "reverse":
            pocket.DirectionOrientation = 1

        part.UpdateObject(pocket)
        self.conn.refresh_display()
        mode = "symmetric" if symmetric else direction
        return f"Pocket created: {depth} mm deep ({mode}). Feature: '{pocket.Name}'"

    def _shaft(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        sketch = self._get_last_sketch(args.get("sketch_name"))
        angle = args.get("angle", 360)

        shaft = sf.AddNewShaft(sketch)
        set_revolution_angle(shaft, angle)

        part.UpdateObject(shaft)
        self.conn.refresh_display()
        return f"Shaft (revolution) created: {angle}°. Feature: '{shaft.Name}'"

    def _groove(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        sketch = self._get_last_sketch(args.get("sketch_name"))
        angle = args.get("angle", 360)

        groove = sf.AddNewGroove(sketch)
        set_revolution_angle(groove, angle)

        part.UpdateObject(groove)
        self.conn.refresh_display()
        return f"Groove (revolution cut) created: {angle}°. Feature: '{groove.Name}'"

    def _fillet(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        sf = part.ShapeFactory

        radius = args["radius"]

        # AddNewSolidEdgeFilletWithConstantRadius needs an actual edge
        # Reference (TriDimFeatEdge), not a whole feature/body - passing the
        # last shape fails with E_FAIL on this install (verified live
        # 2026-07-14). Resolve a real edge from the `edge` selection spec;
        # tangency propagation (mode 1) still rounds the tangent-connected run.
        edge_spec = args.get("edge")
        if edge_spec is None:
            raise ValueError(
                "catia_fillet requires an `edge` reference (e.g. "
                "{'feature': 'Pad.1', 'kind': 'edge', 'index': 1} or a "
                "nearest_point/brep_name). Filleting a whole feature is not "
                "supported by CATIA's constant-radius fillet."
            )
        edge_ref = self.geo.resolve(edge_spec)

        fillet = sf.AddNewSolidEdgeFilletWithConstantRadius(
            edge_ref,
            1,       # catTangencyFilletEdgePropagation
            radius,
        )

        part.UpdateObject(fillet)
        self.conn.refresh_display()
        return f"Fillet created: R{radius} mm. Feature: '{fillet.Name}'"

    def _document_from_path(self, document_path: str | None) -> Any:
        if not document_path:
            return self.conn.active_document

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

    def _shape_by_name_or_last(self, part: Any, feature_name: str | None = None) -> Any:
        body = part.MainBody
        shapes = body.Shapes
        if feature_name:
            return shapes.Item(feature_name)
        if shapes.Count == 0:
            raise RuntimeError("No features found in the active body.")
        return shapes.Item(shapes.Count)

    def _edge_refs_by_indices(self, doc: Any, shape: Any, edge_indices: list[int]) -> dict[int, Any]:
        part = doc.Part
        selection = doc.Selection
        wanted = set(edge_indices)
        found: dict[int, Any] = {}
        selection.Clear()
        selection.Add(shape)
        try:
            selection.Search("Topology.Edge,sel")
            for index in range(1, selection.Count + 1):
                if index not in wanted:
                    continue
                selected = selection.Item(index)
                try:
                    ref = selected.Reference
                except Exception:
                    ref = part.CreateReferenceFromObject(selected.Value)
                found[index] = ref
        finally:
            selection.Clear()

        missing = sorted(wanted - set(found))
        if missing:
            raise IndexError(
                f"Edge indices not found on '{getattr(shape, 'Name', '<shape>')}': {missing}"
            )
        return found

    def _fillet_edges(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        doc = self._document_from_path(args.get("document_path"))
        try:
            part = doc.Part
        except Exception as exc:
            raise RuntimeError("Target document is not a CATPart.") from exc

        radius = args["radius"]
        edge_indices = [int(value) for value in args["edge_indices"]]
        if len(set(edge_indices)) != len(edge_indices):
            edge_indices = sorted(set(edge_indices))

        part.InWorkObject = part.MainBody
        shape = self._shape_by_name_or_last(part, args.get("feature"))
        refs = self._edge_refs_by_indices(doc, shape, edge_indices)
        ordered_refs = [refs[index] for index in edge_indices]
        propagation = 1 if args.get("propagation", "none") == "tangent" else 0

        sf = part.ShapeFactory
        try:
            fillet = sf.AddNewSolidEdgeFilletWithConstantRadius(
                ordered_refs[0],
                propagation,
                radius,
            )
            creation_method = "AddNewSolidEdgeFilletWithConstantRadius"
        except Exception:
            fillet = sf.AddNewEdgeFilletWithConstantRadius(
                ordered_refs[0],
                propagation,
                radius,
            )
            creation_method = "AddNewEdgeFilletWithConstantRadius"
        if args.get("name"):
            fillet.Name = args["name"]

        add_failures: list[str] = []
        for index, ref in zip(edge_indices[1:], ordered_refs[1:]):
            try:
                fillet.AddObjectToFillet(ref)
            except Exception as exc:
                add_failures.append(f"{index}: {exc}")

        part.UpdateObject(fillet)
        if args.get("save", False):
            doc.Save()
        self.conn.refresh_display()

        return json.dumps(
            {
                "feature": fillet.Name,
                "creation_method": creation_method,
                "propagation": args.get("propagation", "none"),
                "radius": radius,
                "source_feature": getattr(shape, "Name", ""),
                "edge_indices": edge_indices,
                "add_failures": add_failures,
                "saved": bool(args.get("save", False)),
            },
            indent=2,
            ensure_ascii=False,
        )

    def _delete_feature(self, doc: Any, feature: Any) -> None:
        selection = doc.Selection
        selection.Clear()
        try:
            selection.Add(feature)
            selection.Delete()
        finally:
            selection.Clear()

    def _new_edge_fillet(self, part: Any, edge_ref: Any, radius: float, propagation: int) -> tuple[Any, str]:
        sf = part.ShapeFactory
        try:
            return (
                sf.AddNewSolidEdgeFilletWithConstantRadius(edge_ref, propagation, radius),
                "AddNewSolidEdgeFilletWithConstantRadius",
            )
        except Exception:
            return (
                sf.AddNewEdgeFilletWithConstantRadius(edge_ref, propagation, radius),
                "AddNewEdgeFilletWithConstantRadius",
            )

    def _probe_fillet_edges(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        doc = self._document_from_path(args.get("document_path"))
        try:
            part = doc.Part
        except Exception as exc:
            raise RuntimeError("Target document is not a CATPart.") from exc

        part.InWorkObject = part.MainBody
        shape = self._shape_by_name_or_last(part, args.get("feature"))
        edge_indices = [int(value) for value in args["edge_indices"]]
        refs = self._edge_refs_by_indices(doc, shape, edge_indices)
        propagation = 1 if args.get("propagation", "none") == "tangent" else 0
        radius = float(args["radius"])

        results = []
        for index in edge_indices:
            feature = None
            method = "unknown"
            try:
                feature, method = self._new_edge_fillet(part, refs[index], radius, propagation)
                feature.Name = f"Probe_R{radius:g}_{index}"
                part.UpdateObject(feature)
                status = "ok"
                error = None
            except Exception as exc:
                status = "failed"
                error = str(exc)
            finally:
                if feature is not None:
                    try:
                        self._delete_feature(doc, feature)
                        try:
                            part.Update()
                        except Exception:
                            pass
                    except Exception:
                        pass
            results.append(
                {
                    "edge_index": index,
                    "status": status,
                    "method": method,
                    "error": error,
                }
            )

        self.conn.refresh_display()
        return json.dumps(
            {
                "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
                "radius": radius,
                "propagation": args.get("propagation", "none"),
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )

    def _refs_by_topology(
        self, doc: Any, shape: Any, query: str
    ) -> list[tuple[int, Any, Any, str]]:
        selection = doc.Selection
        selection.Clear()
        selection.Add(shape)
        refs: list[tuple[int, Any, Any, str]] = []
        try:
            selection.Search(f"{query},sel")
            for index in range(1, selection.Count + 1):
                selected = selection.Item(index)
                try:
                    ref = selected.Reference
                except Exception:
                    ref = doc.Part.CreateReferenceFromObject(selected.Value)
                try:
                    display_name = ref.DisplayName
                except Exception:
                    display_name = ""
                refs.append((index, selected.Value, ref, display_name))
        finally:
            selection.Clear()
        return refs

    def _face_fillet_from_edges(self, args: dict[str, Any]) -> str:
        import re

        self.conn.ensure_connected()
        doc = self._document_from_path(args.get("document_path"))
        try:
            part = doc.Part
        except Exception as exc:
            raise RuntimeError("Target document is not a CATPart.") from exc

        part.InWorkObject = part.MainBody
        shape = self._shape_by_name_or_last(part, args.get("feature"))
        edge_indices = [int(value) for value in args["edge_indices"]]
        radius = float(args["radius"])
        name_prefix = args.get("name_prefix", "FaceFillet")

        edge_refs = {
            index: display_name
            for index, _obj, _ref, display_name in self._refs_by_topology(
                doc, shape, "Topology.Edge"
            )
        }
        face_refs: dict[str, Any] = {}
        for _index, _obj, ref, display_name in self._refs_by_topology(
            doc, shape, "Topology.Face"
        ):
            match = re.search(r"Brp:\([^;]+;%([0-9]+)\)", display_name)
            if match:
                face_refs[match.group(1)] = ref

        pairs: list[tuple[int, str, str]] = []
        for edge_index in edge_indices:
            display_name = edge_refs.get(edge_index, "")
            face_ids = re.findall(r"Face:\(Brp:\([^;]+;%([0-9]+)\)", display_name)
            if len(face_ids) >= 2:
                pairs.append((edge_index, face_ids[0], face_ids[1]))

        unique_pairs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for _edge_index, face_a, face_b in pairs:
            key = tuple(sorted((face_a, face_b)))
            if key not in seen:
                seen.add(key)
                unique_pairs.append((face_a, face_b))

        results = []
        for pair_index, (face_a, face_b) in enumerate(unique_pairs, start=1):
            feature = None
            try:
                ref_a = face_refs[face_a]
                ref_b = face_refs[face_b]
                try:
                    feature = part.ShapeFactory.AddNewSolidFaceFillet(ref_a, ref_b, radius)
                except Exception:
                    feature = part.ShapeFactory.AddNewSolidFaceFillet(ref_a, ref_b, 1, radius)
                feature.Name = f"{name_prefix}_{pair_index:02d}_{face_a}_{face_b}"
                part.UpdateObject(feature)
                results.append(
                    {
                        "faces": [face_a, face_b],
                        "feature": feature.Name,
                        "status": "ok",
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "faces": [face_a, face_b],
                        "feature": getattr(feature, "Name", None) if feature is not None else None,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

        if args.get("save", False):
            doc.Save()
        self.conn.refresh_display()
        return json.dumps(
            {
                "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
                "radius": radius,
                "edge_indices": edge_indices,
                "face_pairs": pairs,
                "unique_pair_count": len(unique_pairs),
                "results": results,
                "saved": bool(args.get("save", False)),
            },
            indent=2,
            ensure_ascii=False,
        )

    def _chamfer(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        length = args["length"]
        angle = args.get("angle", 45)

        chamfer = sf.AddNewChamfer(
            self._get_last_shape(),
            1,       # catTangencyChamferPropagation
            0,       # catLengthAngleChamfer mode
            length,
            angle,
        )

        part.UpdateObject(chamfer)
        self.conn.refresh_display()
        return f"Chamfer created: {length} mm at {angle}°. Feature: '{chamfer.Name}'"

    def _hole(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        sketch = self._get_last_sketch(args.get("sketch_name"))
        diameter = args["diameter"]
        depth = args["depth"]

        hole = sf.AddNewHole(sketch, depth)
        hole.Diameter = diameter
        hole.BottomType = 0  # catFlatBottom

        if args.get("threaded", False):
            hole.ThreadingMode = 1  # catThreaded

        part.UpdateObject(hole)
        self.conn.refresh_display()
        return f"Hole created: D{diameter} mm, depth {depth} mm. Feature: '{hole.Name}'"

    def _rect_pattern(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        feature = self._get_last_shape(args.get("feature_name"))
        d1_count = args["dir1_count"]
        d1_spacing = args["dir1_spacing"]
        d2_count = args.get("dir2_count", 1)
        d2_spacing = args.get("dir2_spacing", 0)

        pattern = sf.AddNewRectPattern(
            feature,
            d1_count, d2_count,
            d1_spacing, d2_spacing,
            1, 1,  # direction specification
            True,   # keep specification
        )

        part.UpdateObject(pattern)
        self.conn.refresh_display()
        return (
            f"Rectangular pattern created: {d1_count}x{d2_count}, "
            f"spacing {d1_spacing}x{d2_spacing} mm. Feature: '{pattern.Name}'"
        )

    def _circ_pattern(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        feature = self._get_last_shape(args.get("feature_name"))
        count = args["count"]
        angular_spacing = args.get("angular_spacing", 360.0 / count)

        pattern = sf.AddNewCircPattern(
            feature,
            count,
            1,              # rows
            angular_spacing,
            0,              # row spacing
            1, 1,           # direction specification
            True,           # keep specification
        )

        part.UpdateObject(pattern)
        self.conn.refresh_display()
        return (
            f"Circular pattern created: {count} instances, "
            f"{angular_spacing}° spacing. Feature: '{pattern.Name}'"
        )

    def _mirror(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        plane_key = args["plane"].lower()
        planes = self.conn.get_origin_elements()
        if plane_key not in planes:
            raise ValueError(f"Unknown plane '{plane_key}'. Use 'xy', 'yz', or 'zx'.")

        mirror_plane = planes[plane_key]
        ref = part.CreateReferenceFromObject(mirror_plane)

        feature = self._get_last_shape(args.get("feature_name"))
        mirror = sf.AddNewMirror(ref)

        part.UpdateObject(mirror)
        self.conn.refresh_display()
        return f"Mirror created about {plane_key.upper()} plane. Feature: '{mirror.Name}'"

    def _shell(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        thickness = args["thickness"]
        shell = sf.AddNewShell(self._get_last_shape(), 0, thickness, thickness)

        # Remove specified faces if any
        faces_to_remove = args.get("faces_to_remove", [])
        for face_name in faces_to_remove:
            try:
                face = body.Shapes.Item(face_name) if face_name else None
                if face:
                    shell.AddFaceToRemove(part.CreateReferenceFromObject(face))
            except Exception:
                pass

        part.UpdateObject(shell)
        self.conn.refresh_display()
        return f"Shell created: {thickness} mm wall thickness. Feature: '{shell.Name}'"

    def _draft(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        angle = args["angle"]

        plane_key = args.get("pulling_direction", "xy").lower()
        planes = self.conn.get_origin_elements()
        neutral = planes.get(plane_key)
        if not neutral:
            raise ValueError(f"Unknown pulling direction plane: {plane_key}")

        neutral_ref = part.CreateReferenceFromObject(neutral)
        draft = sf.AddNewDraft(self._get_last_shape(), neutral_ref, angle)

        part.UpdateObject(draft)
        self.conn.refresh_display()
        return f"Draft created: {angle}° angle. Feature: '{draft.Name}'"

    def _thickness(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        offset = args["offset"]
        thickness = sf.AddNewThickness(self._get_last_shape(), 0, offset)

        part.UpdateObject(thickness)
        self.conn.refresh_display()
        return f"Thickness added: {offset} mm offset. Feature: '{thickness.Name}'"

    def _list_features(self) -> str:
        self.conn.ensure_connected()
        body = self.conn.get_active_part_body()
        shapes = body.Shapes

        features = []
        for i in range(1, shapes.Count + 1):
            shape = shapes.Item(i)
            features.append({
                "index": i,
                "name": shape.Name,
                "type": shape.Type if hasattr(shape, "Type") else "unknown",
            })

        if not features:
            return "No features in the active body"
        return json.dumps(features, indent=2)

    def _list_edges(self) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()

        # Get edges from the last shape
        last_shape = self._get_last_shape()
        edges = []
        try:
            # Access boundary representation
            sel = self.conn.hso
            sel.Clear()
            sel.Add(last_shape)
            sel.Search("Topology.Edge,sel")

            for i in range(1, sel.Count + 1):
                edges.append({
                    "index": i,
                    "name": sel.Item(i).Value.Name if hasattr(sel.Item(i).Value, "Name") else f"Edge.{i}",
                })
            sel.Clear()
        except Exception as e:
            return f"Could not enumerate edges: {e}. Use CATIA selection to identify edge names."

        if not edges:
            return "No edges found on the last feature"
        return json.dumps(edges, indent=2)
