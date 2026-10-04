"""Part Design tools for CATIA V5.

3D feature creation: Pad, Pocket, Fillet, Chamfer, Shaft, Groove, Hole,
RectPattern, CircPattern, Mirror, Rib, Slot, Shell, Thickness, Draft.
"""

from __future__ import annotations

import json
import re
from typing import Any

from catia_mcp.connection import CATIAConnection


class PartDesignTools:
    """Tools for 3D Part Design features in CATIA V5."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

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
                            "description": "Cut direction: 'normal' (default), 'reverse'",
                            "enum": ["normal", "reverse"],
                            "default": "normal",
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
                                "Indexed edge to fillet ('Edge.N' from "
                                "catia_list_edges). Omit to fillet all edges "
                                "of the last feature."
                            ),
                        },
                    },
                    "required": ["radius"],
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
                            "description": "Indexed edge to chamfer ('Edge.N' from catia_list_edges). Omit to chamfer all edges of the last feature.",
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
                            "description": (
                                "REQUIRED: indexed faces to remove and open "
                                "('Face.N' from catia_list_faces); the first "
                                "one anchors the shell."
                            ),
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
                            "description": "REQUIRED: indexed face to draft ('Face.N' from catia_list_faces)",
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
                            "description": "REQUIRED: indexed face to thicken ('Face.N' from catia_list_faces)",
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
                "description": (
                    "List the edges of the final solid shape as indexed names "
                    "(Edge.N). These indices feed catia_measure_distance; for "
                    "fillet/chamfer targeting see each tool's own contract."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_list_faces",
                "description": (
                    "List the faces of the final solid shape as indexed names "
                    "(Face.N) for use with catia_measure_distance."
                ),
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
            case "catia_list_faces":
                return self._list_faces()
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

        # Get the last sketch
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

    def _body_volume_mm3(self, part: Any, body: Any) -> float | None:
        """Measure the body's solid volume in mm3, or None if unavailable."""
        try:
            doc = part.Parent
            try:
                spa = doc.GetWorkbench("SPAWorkbench")
            except AttributeError:
                spa = self.conn.app.GetWorkbench("SPAWorkbench")
            ref = part.CreateReferenceFromObject(body)
            return spa.GetMeasurable(ref).Volume * 1e9  # m3 -> mm3
        except Exception:
            return None

    def _pocket(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        sketch = self._get_last_sketch(args.get("sketch_name"))
        depth = args["depth"]
        reverse = args.get("direction") == "reverse"

        before = self._body_volume_mm3(part, body)

        pocket = sf.AddNewPocket(sketch, depth)
        # A pocket cuts on one side of the profile's support plane only, so
        # the orientation is set explicitly in both cases (field-verified:
        # the wrong side produces a tree feature that removes nothing).
        pocket.DirectionOrientation = 1 if reverse else 0
        part.UpdateObject(pocket)

        explicit_direction = "direction" in args
        flipped = False
        after = self._body_volume_mm3(part, body)
        if (
            before is not None
            and after is not None
            and after >= before
            and not explicit_direction
        ):
            # No material removed and the caller did not pin the side: flip
            # and re-verify instead of reporting a false success. An explicit
            # 'direction' is honored as-is and reported honestly below.
            pocket.DirectionOrientation = 0 if reverse else 1
            part.UpdateObject(pocket)
            new_after = self._body_volume_mm3(part, body)
            if new_after is not None and new_after < before:
                after = new_after
                flipped = True
            else:
                # The flip did not help either: restore the requested
                # orientation so the tree reflects the original intent.
                pocket.DirectionOrientation = 1 if reverse else 0
                part.UpdateObject(pocket)
                after = self._body_volume_mm3(part, body)

        self.conn.refresh_display()

        if before is not None and after is not None:
            removed = before - after
            if removed <= 0:
                return (
                    f"FEATURE_NO_EFFECT: pocket '{pocket.Name}' was created in "
                    f"the tree but removed no material"
                    + (" in the requested direction" if explicit_direction
                       else " in either direction")
                    + f" (volume stayed {before:.1f} mm3). Check that the "
                    "profile intersects the solid."
                )
            flip_note = " (direction auto-flipped to reach material)" if flipped else ""
            return (
                f"Pocket '{pocket.Name}' created: {depth} mm deep{flip_note}. "
                f"Removed {removed:.1f} mm3 ({before:.1f} -> {after:.1f})."
            )
        return (
            f"Pocket created: {depth} mm deep. Feature: '{pocket.Name}' "
            "(volume verification unavailable on this installation)."
        )

    def _shaft(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        sketch = self._get_last_sketch(args.get("sketch_name"))
        angle = args.get("angle", 360)

        shaft = sf.AddNewShaft(sketch)
        shaft.FirstAngle = angle

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
        groove.FirstAngle = angle

        part.UpdateObject(groove)
        self.conn.refresh_display()
        return f"Groove (revolution cut) created: {angle}°. Feature: '{groove.Name}'"

    def _topo_reference(self, kind: str, index: int) -> Any:
        """Resolve Face.N / Edge.N on the body's final shape to a Reference.

        References come from the selection's Reference property because
        CreateReferenceFromObject rejects HSO-resolved topology cells
        (field-verified E_INVALIDARG). Indices match catia_list_faces /
        catia_list_edges.
        """
        body = self.conn.get_active_part_body()
        if body.Shapes.Count == 0:
            raise RuntimeError("The active body has no solid shape yet.")
        last_shape = body.Shapes.Item(body.Shapes.Count)
        sel = self.conn.hso
        try:
            sel.Clear()
            sel.Add(last_shape)
            sel.Search(f"Topology.{kind},sel")
            count = sel.Count
            if index < 1 or index > count:
                raise RuntimeError(
                    f"{kind}.{index} is out of range: the final shape exposes "
                    f"{count} {kind.lower()}(s). Use catia_list_faces / "
                    "catia_list_edges to enumerate valid indices."
                )
            return sel.Item(index).Reference
        finally:
            try:
                sel.Clear()
            except Exception:
                pass

    @staticmethod
    def _topo_index(name: str, kind: str) -> int:
        m = re.match(rf"^{kind}\.(\d+)$", name or "")
        if not m:
            raise ValueError(
                f"Expected an indexed name like '{kind}.1' (from "
                f"catia_list_faces / catia_list_edges), got '{name}'."
            )
        return int(m.group(1))

    def _fillet(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        radius = args["radius"]
        edge_name = args.get("edge_name")
        if edge_name:
            target = self._topo_reference("Edge", self._topo_index(edge_name, "Edge"))
            scope = edge_name
        else:
            # Whole-feature fallback: a Reference to the feature fillets its
            # edges with tangency propagation.
            target = part.CreateReferenceFromObject(self._get_last_shape())
            scope = "all edges of the last feature"

        fillet = sf.AddNewSolidEdgeFilletWithConstantRadius(
            target,
            1,       # catTangencyFilletEdgePropagation
            radius,
        )

        part.UpdateObject(fillet)
        self.conn.refresh_display()
        return f"Fillet created: R{radius} mm on {scope}. Feature: '{fillet.Name}'"

    def _chamfer(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        length = args["length"]
        angle = args.get("angle", 45)
        edge_name = args.get("edge_name")
        if edge_name:
            target = self._topo_reference("Edge", self._topo_index(edge_name, "Edge"))
            scope = edge_name
        else:
            target = part.CreateReferenceFromObject(self._get_last_shape())
            scope = "all edges of the last feature"

        # AddNewChamfer(iObjectToChamfer, iPropagation, iMode, iOrientation,
        #               iLength1, iLength2OrAngle) - 6 parameters.
        chamfer = sf.AddNewChamfer(
            target,
            1,       # catTangencyChamferPropagation
            0,       # catLengthAngleChamfer mode
            0,       # catNoReverseChamfer orientation
            length,
            angle,
        )

        part.UpdateObject(chamfer)
        self.conn.refresh_display()
        return f"Chamfer created: {length} mm at {angle} deg on {scope}. Feature: '{chamfer.Name}'"

    def _hole(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        sketch = self._get_last_sketch(args.get("sketch_name"))
        diameter = args["diameter"]
        depth = args["depth"]

        # AddNewHole takes a support FACE reference; the sketch-positioned
        # form is AddNewHoleFromSketch. Diameter is a read-only Length
        # parameter object whose .Value is assigned.
        hole = sf.AddNewHoleFromSketch(sketch, depth)
        hole.Diameter.Value = diameter
        hole.BottomType = 0  # catFlatBottom

        hole_type = args.get("type", "simple")
        type_map = {"simple": 0, "tapered": 1, "counterbored": 2, "countersunk": 3}
        type_note = ""
        if hole_type in type_map and hole_type != "simple":
            try:
                hole.Type = type_map[hole_type]
                type_note = (
                    f" Type: {hole_type} (head dimensions keep CATIA "
                    "defaults; adjust in the tree if needed)."
                )
            except Exception:
                type_note = f" Type '{hole_type}' not applied (API rejected it); simple hole created."

        if args.get("threaded", False):
            hole.ThreadingMode = 1  # catThreaded

        part.UpdateObject(hole)
        self.conn.refresh_display()
        return f"Hole created: D{diameter} mm, depth {depth} mm. Feature: '{hole.Name}'.{type_note}"

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

        # AddNewRectPattern takes 12 parameters; empty-name references let
        # CATIA pick the default directions (recorded-macro pattern).
        ref1 = part.CreateReferenceFromName("")
        ref2 = part.CreateReferenceFromName("")
        pattern = sf.AddNewRectPattern(
            feature,
            d1_count, d2_count,
            d1_spacing, d2_spacing,
            1, 1,          # position of the original along dir1/dir2
            ref1, ref2,    # direction references (defaults)
            False, False,  # reversed dir1/dir2
            0.0,           # rotation angle
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

        # AddNewCircPattern takes 12 parameters; instances around the axis
        # belong in the ANGULAR slot (3rd), radial count stays 1.
        refc = part.CreateReferenceFromName("")
        refa = part.CreateReferenceFromName("")
        pattern = sf.AddNewCircPattern(
            feature,
            1, count,              # radial copies, angular copies
            0.0, angular_spacing,  # radial step, angular step (deg)
            1, 1,                  # position of the original
            refc, refa,            # rotation center / axis (defaults)
            True,                  # reversed rotation axis
            0.0,                   # rotation angle
            True,                  # radius aligned
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

        # AddNewMirror takes only the plane reference and mirrors the
        # body's existing shapes; per-feature mirroring is not expressible
        # through this API.
        mirror = sf.AddNewMirror(ref)

        part.UpdateObject(mirror)
        self.conn.refresh_display()
        return (
            f"Mirror created about {plane_key.upper()} plane (mirrors the "
            f"body's shapes). Feature: '{mirror.Name}'"
        )

    def _shell(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        thickness = args["thickness"]
        faces = args.get("faces_to_remove") or []
        if not faces:
            raise ValueError(
                "catia_shell requires 'faces_to_remove' with at least one "
                "indexed face name ('Face.N' from catia_list_faces): "
                "AddNewShell's first parameter is the face to remove."
            )
        refs = [
            self._topo_reference("Face", self._topo_index(f, "Face"))
            for f in faces
        ]
        # AddNewShell(iFaceToRemove, iInternalThickness, iExternalThickness)
        shell = sf.AddNewShell(refs[0], thickness, 0)
        skipped = []
        for extra, ref in zip(faces[1:], refs[1:]):
            try:
                shell.AddFaceToRemove(ref)
            except Exception:
                skipped.append(extra)

        part.UpdateObject(shell)
        self.conn.refresh_display()
        note = f" (could not add: {', '.join(skipped)})" if skipped else ""
        return (
            f"Shell created: {thickness} mm wall, removed "
            f"{len(faces) - len(skipped)} face(s){note}. Feature: '{shell.Name}'"
        )

    def _draft(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        angle = args["angle"]
        face_name = args.get("face_name")
        if not face_name:
            raise ValueError(
                "catia_draft requires 'face_name' ('Face.N' from "
                "catia_list_faces): the face to draft."
            )
        face_ref = self._topo_reference("Face", self._topo_index(face_name, "Face"))

        plane_key = args.get("pulling_direction", "xy").lower()
        planes = self.conn.get_origin_elements()
        neutral = planes.get(plane_key)
        if not neutral:
            raise ValueError(f"Unknown pulling direction plane: {plane_key}")
        neutral_ref = part.CreateReferenceFromObject(neutral)

        # Pulling direction = the selected plane's normal.
        direction = {"xy": (0, 0, 1), "yz": (1, 0, 0), "zx": (0, 1, 0)}[plane_key]
        parting_ref = part.CreateReferenceFromName("")

        # AddNewDraft(iFaceToDraft, iNeutral, iNeutralMode, iParting,
        #             iDirX, iDirY, iDirZ, iMode, iAngle, iMultiselectionMode)
        draft = sf.AddNewDraft(
            face_ref, neutral_ref, 0, parting_ref,
            direction[0], direction[1], direction[2],
            0, angle, 0,
        )

        part.UpdateObject(draft)
        self.conn.refresh_display()
        return f"Draft created: {angle} deg on {face_name}. Feature: '{draft.Name}'"

    def _thickness(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        sf = part.ShapeFactory

        offset = args["offset"]
        face_name = args.get("face_name")
        if not face_name:
            raise ValueError(
                "catia_thickness requires 'face_name' ('Face.N' from "
                "catia_list_faces): the face to thicken."
            )
        face_ref = self._topo_reference("Face", self._topo_index(face_name, "Face"))

        # AddNewThickness(iFaceToThicken, iOffset) - 2 parameters.
        thickness = sf.AddNewThickness(face_ref, offset)

        part.UpdateObject(thickness)
        self.conn.refresh_display()
        return f"Thickness added: {offset} mm on {face_name}. Feature: '{thickness.Name}'"

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

    def _list_faces(self) -> str:
        self.conn.ensure_connected()
        body = self.conn.get_active_part_body()

        faces = []
        try:
            if body.Shapes.Count == 0:
                return "No solid shape in the active body yet"
            last_shape = body.Shapes.Item(body.Shapes.Count)
            sel = self.conn.hso
            try:
                sel.Clear()
                sel.Add(last_shape)
                sel.Search("Topology.Face,sel")
                for i in range(1, sel.Count + 1):
                    faces.append({"index": i, "name": f"Face.{i}"})
            finally:
                try:
                    sel.Clear()
                except Exception:
                    pass
        except Exception as e:
            return f"Could not enumerate faces: {e}"

        if not faces:
            return "No faces found on the final shape"
        return json.dumps(faces, indent=2)

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
            try:
                sel.Clear()
                sel.Add(last_shape)
                sel.Search("Topology.Edge,sel")
                for i in range(1, sel.Count + 1):
                    # Canonical indexed name accepted by catia_measure_distance,
                    # catia_fillet and catia_chamfer. Raw HSO names are long
                    # and unusable in searches.
                    edges.append({"index": i, "name": f"Edge.{i}"})
            finally:
                try:
                    sel.Clear()
                except Exception:
                    pass
        except Exception as e:
            return f"Could not enumerate edges: {e}. Use CATIA selection to identify edge names."

        if not edges:
            return "No edges found on the last feature"
        return json.dumps(edges, indent=2)
