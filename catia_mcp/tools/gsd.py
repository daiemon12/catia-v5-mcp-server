"""Generative Shape Design (GSD) tools for CATIA V5.

Wireframe and surface creation via Part.HybridShapeFactory:
points, lines, planes, 3D splines, circles, projections, intersections,
multi-sections surface (loft), sweep, extrude, revolve, fill, blend, offset,
join, split, trim, symmetry — plus ThickSurface/CloseSurface to turn
surfaces back into Part Design solids.

All GSD features live in a Geometrical Set (HybridBody). Elements are
addressed by their tree name; most creation tools accept an optional
'name' to rename the result so later tools can reference it.
All dimensions are in millimeters, angles in degrees.
"""

from __future__ import annotations

import json
from typing import Any

from catia_mcp.connection import CATIAConnection

# Origin plane aliases (same convention as sketcher.py)
PLANE_MAP = {
    "xy": "PlaneXY",
    "yz": "PlaneYZ",
    "zx": "PlaneZX",
    "xz": "PlaneZX",  # alias
}

# Schema fragment: an element addressed by tree name, or [x, y, z] coordinates
# (coordinates create a new 3D point on the fly).
POINT_OR_NAME = {
    "oneOf": [
        {"type": "string", "description": "Name of an existing point element"},
        {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 3,
            "maxItems": 3,
            "description": "[x, y, z] coordinates in mm (creates a new point)",
        },
    ],
}


class GSDTools:
    """Tools for Generative Shape Design (wireframe & surface) in CATIA V5."""

    DEFAULT_GEOSET = "GSD_Set"

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self._active_geoset_name: str | None = None

    # ────────────────────────────────────────────────────────────
    # Tool definitions
    # ────────────────────────────────────────────────────────────

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_gsd_create_geoset",
                "description": (
                    "Create a new Geometrical Set (HybridBody) in the active Part and "
                    "make it the active target for subsequent GSD elements."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name for the new geometrical set",
                            "default": "GSD_Set",
                        },
                    },
                },
            },
            {
                "name": "catia_gsd_set_active_geoset",
                "description": (
                    "Select which Geometrical Set receives subsequently created GSD elements."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of an existing geometrical set",
                        },
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "catia_gsd_list_elements",
                "description": (
                    "List all geometrical sets with their wireframe/surface elements and "
                    "sketches, plus sketches in solid bodies. Use this to find element "
                    "names for other GSD tools."
                ),
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "catia_gsd_point",
                "description": "Create a 3D point at (x, y, z). Coordinates in mm.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "X coordinate (mm)"},
                        "y": {"type": "number", "description": "Y coordinate (mm)"},
                        "z": {"type": "number", "description": "Z coordinate (mm)"},
                        "name": {"type": "string", "description": "Optional name for the point"},
                    },
                    "required": ["x", "y", "z"],
                },
            },
            {
                "name": "catia_gsd_line",
                "description": (
                    "Create a 3D line between two points. Each point is an existing "
                    "element name or [x, y, z] coordinates."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "point1": POINT_OR_NAME,
                        "point2": POINT_OR_NAME,
                        "name": {"type": "string", "description": "Optional name for the line"},
                    },
                    "required": ["point1", "point2"],
                },
            },
            {
                "name": "catia_gsd_plane_offset",
                "description": (
                    "Create a plane offset from a reference plane. Reference is 'xy', 'yz', "
                    "'zx', or the name of an existing plane element."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "base_plane": {
                            "type": "string",
                            "description": "Reference plane: 'xy', 'yz', 'zx', or element name",
                        },
                        "offset": {"type": "number", "description": "Offset distance (mm)"},
                        "reverse": {
                            "type": "boolean",
                            "description": "Offset in the opposite direction",
                            "default": False,
                        },
                        "name": {"type": "string", "description": "Optional name for the plane"},
                    },
                    "required": ["base_plane", "offset"],
                },
            },
            {
                "name": "catia_gsd_plane_3points",
                "description": "Create a plane through three points (element names or [x,y,z]).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "point1": POINT_OR_NAME,
                        "point2": POINT_OR_NAME,
                        "point3": POINT_OR_NAME,
                        "name": {"type": "string", "description": "Optional name for the plane"},
                    },
                    "required": ["point1", "point2", "point3"],
                },
            },
            {
                "name": "catia_gsd_spline",
                "description": (
                    "Create a 3D spline through a list of points. Each point is an existing "
                    "element name or [x, y, z] coordinates in mm."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "points": {
                            "type": "array",
                            "items": POINT_OR_NAME,
                            "minItems": 2,
                            "description": "Points the spline passes through, in order",
                        },
                        "closed": {
                            "type": "boolean",
                            "description": "Close the spline into a loop",
                            "default": False,
                        },
                        "name": {"type": "string", "description": "Optional name for the spline"},
                    },
                    "required": ["points"],
                },
            },
            {
                "name": "catia_gsd_circle",
                "description": (
                    "Create a full 3D circle from a center point, a support plane, and a "
                    "radius. Useful as a section for multi-sections surfaces."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "center": POINT_OR_NAME,
                        "support_plane": {
                            "type": "string",
                            "description": "Support plane: 'xy', 'yz', 'zx', or element name",
                        },
                        "radius": {"type": "number", "description": "Radius (mm)"},
                        "name": {"type": "string", "description": "Optional name for the circle"},
                    },
                    "required": ["center", "support_plane", "radius"],
                },
            },
            {
                "name": "catia_gsd_project",
                "description": "Project a curve/point onto a support surface or plane.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "element": {
                            "type": "string",
                            "description": "Name of the element to project",
                        },
                        "support": {
                            "type": "string",
                            "description": "Projection support: 'xy', 'yz', 'zx', or element name",
                        },
                        "name": {"type": "string", "description": "Optional name for the result"},
                    },
                    "required": ["element", "support"],
                },
            },
            {
                "name": "catia_gsd_intersection",
                "description": "Create the intersection of two elements (e.g. surface ∩ plane).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "element1": {"type": "string", "description": "First element name"},
                        "element2": {
                            "type": "string",
                            "description": "Second element: 'xy', 'yz', 'zx', or element name",
                        },
                        "name": {"type": "string", "description": "Optional name for the result"},
                    },
                    "required": ["element1", "element2"],
                },
            },
            {
                "name": "catia_gsd_multi_section_surface",
                "description": (
                    "Create a Multi-sections Surface (loft) through 2+ section curves "
                    "(sketches, circles, splines...), optionally following guide curves. "
                    "Sections should be listed in order along the lofting direction."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sections": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 2,
                            "description": "Section curve element names, in lofting order",
                        },
                        "guides": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional guide curve element names",
                        },
                        "name": {"type": "string", "description": "Optional name for the surface"},
                    },
                    "required": ["sections"],
                },
            },
            {
                "name": "catia_gsd_sweep",
                "description": (
                    "Create a swept surface by sweeping a profile curve along a guide curve "
                    "(explicit sweep)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "profile": {"type": "string", "description": "Profile curve element name"},
                        "guide": {"type": "string", "description": "Guide curve element name"},
                        "name": {"type": "string", "description": "Optional name for the surface"},
                    },
                    "required": ["profile", "guide"],
                },
            },
            {
                "name": "catia_gsd_extrude",
                "description": (
                    "Extrude a profile (curve/sketch) into a surface along a direction "
                    "vector. limit1/limit2 are the extents on each side (mm)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "profile": {"type": "string", "description": "Profile element name"},
                        "direction": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                            "description": "Extrusion direction vector [x, y, z]",
                        },
                        "limit1": {"type": "number", "description": "Length along direction (mm)"},
                        "limit2": {
                            "type": "number",
                            "description": "Length opposite to direction (mm)",
                            "default": 0,
                        },
                        "name": {"type": "string", "description": "Optional name for the surface"},
                    },
                    "required": ["profile", "direction", "limit1"],
                },
            },
            {
                "name": "catia_gsd_revolve",
                "description": (
                    "Revolve a profile curve around an axis line to create a surface of "
                    "revolution. Angles in degrees."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "profile": {"type": "string", "description": "Profile element name"},
                        "axis": {"type": "string", "description": "Axis line element name"},
                        "angle1": {
                            "type": "number",
                            "description": "First angle limit (degrees)",
                            "default": 360,
                        },
                        "angle2": {
                            "type": "number",
                            "description": "Second angle limit (degrees)",
                            "default": 0,
                        },
                        "name": {"type": "string", "description": "Optional name for the surface"},
                    },
                    "required": ["profile", "axis"],
                },
            },
            {
                "name": "catia_gsd_fill",
                "description": (
                    "Create a Fill surface bounded by a closed contour of curves "
                    "(one closed curve or several connected curves)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "boundaries": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "description": "Boundary curve element names, in contour order",
                        },
                        "name": {"type": "string", "description": "Optional name for the surface"},
                    },
                    "required": ["boundaries"],
                },
            },
            {
                "name": "catia_gsd_blend",
                "description": "Create a Blend surface connecting two curves.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "curve1": {"type": "string", "description": "First curve element name"},
                        "curve2": {"type": "string", "description": "Second curve element name"},
                        "name": {"type": "string", "description": "Optional name for the surface"},
                    },
                    "required": ["curve1", "curve2"],
                },
            },
            {
                "name": "catia_gsd_offset_surface",
                "description": "Create a surface offset from an existing surface.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "surface": {"type": "string", "description": "Surface element name"},
                        "offset": {"type": "number", "description": "Offset distance (mm)"},
                        "reverse": {
                            "type": "boolean",
                            "description": "Offset in the opposite direction",
                            "default": False,
                        },
                        "name": {"type": "string", "description": "Optional name for the surface"},
                    },
                    "required": ["surface", "offset"],
                },
            },
            {
                "name": "catia_gsd_join",
                "description": "Join (assemble) two or more curves or surfaces into one element.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "elements": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 2,
                            "description": "Element names to join",
                        },
                        "name": {"type": "string", "description": "Optional name for the result"},
                    },
                    "required": ["elements"],
                },
            },
            {
                "name": "catia_gsd_split",
                "description": (
                    "Split an element by a cutting element, keeping one side. "
                    "Use orientation to flip which side is kept."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "element": {"type": "string", "description": "Element to split"},
                        "cutter": {
                            "type": "string",
                            "description": "Cutting element: 'xy', 'yz', 'zx', or element name",
                        },
                        "reverse": {
                            "type": "boolean",
                            "description": "Keep the other side",
                            "default": False,
                        },
                        "name": {"type": "string", "description": "Optional name for the result"},
                    },
                    "required": ["element", "cutter"],
                },
            },
            {
                "name": "catia_gsd_trim",
                "description": (
                    "Mutually trim two elements, keeping one side of each. "
                    "Use reverse flags to flip which sides are kept."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "element1": {"type": "string", "description": "First element name"},
                        "element2": {"type": "string", "description": "Second element name"},
                        "reverse1": {
                            "type": "boolean",
                            "description": "Keep the other side of element1",
                            "default": False,
                        },
                        "reverse2": {
                            "type": "boolean",
                            "description": "Keep the other side of element2",
                            "default": False,
                        },
                        "name": {"type": "string", "description": "Optional name for the result"},
                    },
                    "required": ["element1", "element2"],
                },
            },
            {
                "name": "catia_gsd_symmetry",
                "description": "Mirror an element about a plane ('xy', 'yz', 'zx', or plane name).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "element": {"type": "string", "description": "Element to mirror"},
                        "plane": {
                            "type": "string",
                            "description": "Mirror plane: 'xy', 'yz', 'zx', or element name",
                        },
                        "name": {"type": "string", "description": "Optional name for the result"},
                    },
                    "required": ["element", "plane"],
                },
            },
            {
                "name": "catia_gsd_thick_surface",
                "description": (
                    "Turn a surface into a SOLID by adding thickness (Part Design "
                    "ThickSurface). The solid is created in the active body."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "surface": {"type": "string", "description": "Surface element name"},
                        "thickness1": {
                            "type": "number",
                            "description": "Thickness on the primary side (mm)",
                        },
                        "thickness2": {
                            "type": "number",
                            "description": "Thickness on the other side (mm)",
                            "default": 0,
                        },
                    },
                    "required": ["surface", "thickness1"],
                },
            },
            {
                "name": "catia_gsd_close_surface",
                "description": (
                    "Turn a closed (watertight) surface into a SOLID (Part Design "
                    "CloseSurface). The solid is created in the active body."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "surface": {"type": "string", "description": "Surface element name"},
                    },
                    "required": ["surface"],
                },
            },
        ]

    # ────────────────────────────────────────────────────────────
    # Dispatch
    # ────────────────────────────────────────────────────────────

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_gsd_create_geoset":
                return self._create_geoset(arguments)
            case "catia_gsd_set_active_geoset":
                return self._set_active_geoset(arguments)
            case "catia_gsd_list_elements":
                return self._list_elements()
            case "catia_gsd_point":
                return self._point(arguments)
            case "catia_gsd_line":
                return self._line(arguments)
            case "catia_gsd_plane_offset":
                return self._plane_offset(arguments)
            case "catia_gsd_plane_3points":
                return self._plane_3points(arguments)
            case "catia_gsd_spline":
                return self._spline(arguments)
            case "catia_gsd_circle":
                return self._circle(arguments)
            case "catia_gsd_project":
                return self._project(arguments)
            case "catia_gsd_intersection":
                return self._intersection(arguments)
            case "catia_gsd_multi_section_surface":
                return self._multi_section_surface(arguments)
            case "catia_gsd_sweep":
                return self._sweep(arguments)
            case "catia_gsd_extrude":
                return self._extrude(arguments)
            case "catia_gsd_revolve":
                return self._revolve(arguments)
            case "catia_gsd_fill":
                return self._fill(arguments)
            case "catia_gsd_blend":
                return self._blend(arguments)
            case "catia_gsd_offset_surface":
                return self._offset_surface(arguments)
            case "catia_gsd_join":
                return self._join(arguments)
            case "catia_gsd_split":
                return self._split(arguments)
            case "catia_gsd_trim":
                return self._trim(arguments)
            case "catia_gsd_symmetry":
                return self._symmetry(arguments)
            case "catia_gsd_thick_surface":
                return self._thick_surface(arguments)
            case "catia_gsd_close_surface":
                return self._close_surface(arguments)
            case _:
                raise ValueError(f"Unknown GSD tool: {tool_name}")

    # ────────────────────────────────────────────────────────────
    # Helpers: geoset management and element resolution
    # ────────────────────────────────────────────────────────────

    def _factory(self) -> Any:
        return self.conn.get_active_part().HybridShapeFactory

    def _iter_geosets(self, hybrid_bodies: Any):
        """Yield all geometrical sets, including nested ones."""
        for i in range(1, hybrid_bodies.Count + 1):
            hb = hybrid_bodies.Item(i)
            yield hb
            try:
                yield from self._iter_geosets(hb.HybridBodies)
            except Exception:
                pass

    def _get_geoset(self) -> Any:
        """Get the active geometrical set, falling back to the first existing
        one, or creating a default one if the part has none."""
        part = self.conn.get_active_part()
        hbs = part.HybridBodies

        if self._active_geoset_name:
            for hb in self._iter_geosets(hbs):
                if hb.Name == self._active_geoset_name:
                    return hb
            # The remembered geoset is gone (document changed) — fall through
            self._active_geoset_name = None

        if hbs.Count > 0:
            hb = hbs.Item(1)
            self._active_geoset_name = hb.Name
            return hb

        hb = hbs.Add()
        hb.Name = self.DEFAULT_GEOSET
        self._active_geoset_name = hb.Name
        return hb

    def _find_element(self, name: str) -> Any:
        """Find a wireframe/surface element or sketch by its tree name.

        Search order: origin planes (xy/yz/zx aliases), hybrid shapes and
        sketches in all geometrical sets (nested included), then sketches
        in solid bodies.
        """
        part = self.conn.get_active_part()

        key = name.lower()
        if key in PLANE_MAP:
            return getattr(part.OriginElements, PLANE_MAP[key])

        for hb in self._iter_geosets(part.HybridBodies):
            for collection in ("HybridShapes", "HybridSketches"):
                try:
                    return getattr(hb, collection).Item(name)
                except Exception:
                    pass

        bodies = part.Bodies
        for i in range(1, bodies.Count + 1):
            try:
                return bodies.Item(i).Sketches.Item(name)
            except Exception:
                pass

        raise RuntimeError(
            f"Element '{name}' not found in geometrical sets or body sketches. "
            "Use catia_gsd_list_elements to see available element names."
        )

    def _ref(self, name: str) -> Any:
        """Get a Reference to a named element."""
        part = self.conn.get_active_part()
        return part.CreateReferenceFromObject(self._find_element(name))

    def _point_ref(self, spec: Any) -> Any:
        """Resolve a point spec (element name or [x, y, z]) to a Reference.

        Coordinates create a new point feature in the active geoset.
        """
        if isinstance(spec, str):
            return self._ref(spec)
        if isinstance(spec, (list, tuple)) and len(spec) == 3:
            part = self.conn.get_active_part()
            point = self._factory().AddNewPointCoord(spec[0], spec[1], spec[2])
            self._get_geoset().AppendHybridShape(point)
            part.UpdateObject(point)
            return part.CreateReferenceFromObject(point)
        raise ValueError(f"Invalid point spec: {spec!r}. Use an element name or [x, y, z].")

    def _finish(self, shape: Any, name: str | None, message: str) -> str:
        """Append a hybrid shape to the active geoset, rename, update, refresh."""
        part = self.conn.get_active_part()
        geoset = self._get_geoset()
        geoset.AppendHybridShape(shape)
        if name:
            shape.Name = name
        part.InWorkObject = shape
        part.UpdateObject(shape)
        self.conn.refresh_display()
        return f"{message} Element: '{shape.Name}' in geometrical set '{geoset.Name}'"

    # ────────────────────────────────────────────────────────────
    # Geoset management
    # ────────────────────────────────────────────────────────────

    def _create_geoset(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        name = args.get("name", self.DEFAULT_GEOSET)

        hb = part.HybridBodies.Add()
        hb.Name = name
        self._active_geoset_name = hb.Name
        try:
            part.Update()
        except Exception:
            pass
        return f"Geometrical set '{hb.Name}' created and set as active."

    def _set_active_geoset(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        name = args["name"]

        for hb in self._iter_geosets(part.HybridBodies):
            if hb.Name == name:
                self._active_geoset_name = name
                return f"Active geometrical set: '{name}'"

        available = [hb.Name for hb in self._iter_geosets(part.HybridBodies)]
        raise RuntimeError(
            f"Geometrical set '{name}' not found. Available: {available or 'none'}"
        )

    def _list_elements(self) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()

        result: dict[str, Any] = {
            "active_geoset": self._active_geoset_name,
            "geometrical_sets": [],
            "body_sketches": [],
        }

        for hb in self._iter_geosets(part.HybridBodies):
            shapes = []
            try:
                hs = hb.HybridShapes
                for i in range(1, hs.Count + 1):
                    shapes.append(hs.Item(i).Name)
            except Exception:
                pass
            sketches = []
            try:
                sk = hb.HybridSketches
                for i in range(1, sk.Count + 1):
                    sketches.append(sk.Item(i).Name)
            except Exception:
                pass
            result["geometrical_sets"].append(
                {"name": hb.Name, "elements": shapes, "sketches": sketches}
            )

        bodies = part.Bodies
        for i in range(1, bodies.Count + 1):
            body = bodies.Item(i)
            try:
                for j in range(1, body.Sketches.Count + 1):
                    result["body_sketches"].append(
                        {"body": body.Name, "sketch": body.Sketches.Item(j).Name}
                    )
            except Exception:
                pass

        return json.dumps(result, indent=2, ensure_ascii=False)

    # ────────────────────────────────────────────────────────────
    # Wireframe
    # ────────────────────────────────────────────────────────────

    def _point(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        x, y, z = args["x"], args["y"], args["z"]
        point = self._factory().AddNewPointCoord(x, y, z)
        return self._finish(point, args.get("name"), f"3D point created at ({x}, {y}, {z}) mm.")

    def _line(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        ref1 = self._point_ref(args["point1"])
        ref2 = self._point_ref(args["point2"])
        line = self._factory().AddNewLinePtPt(ref1, ref2)
        return self._finish(line, args.get("name"), "3D line created between two points.")

    def _plane_offset(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        base_ref = self._ref(args["base_plane"])
        offset = args["offset"]
        reverse = args.get("reverse", False)
        plane = self._factory().AddNewPlaneOffset(base_ref, offset, reverse)
        return self._finish(
            plane, args.get("name"),
            f"Offset plane created: {offset} mm from '{args['base_plane']}'"
            f"{' (reversed)' if reverse else ''}.",
        )

    def _plane_3points(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        ref1 = self._point_ref(args["point1"])
        ref2 = self._point_ref(args["point2"])
        ref3 = self._point_ref(args["point3"])
        plane = self._factory().AddNewPlane3Points(ref1, ref2, ref3)
        return self._finish(plane, args.get("name"), "Plane created through 3 points.")

    def _spline(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        points = args["points"]
        closed = args.get("closed", False)

        refs = [self._point_ref(p) for p in points]
        spline = self._factory().AddNewSpline()
        for ref in refs:
            spline.AddPoint(ref)
        if closed:
            spline.SetClosing(1)

        return self._finish(
            spline, args.get("name"),
            f"3D spline created through {len(points)} points{' (closed)' if closed else ''}.",
        )

    def _circle(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        center_ref = self._point_ref(args["center"])
        support_ref = self._ref(args["support_plane"])
        radius = args["radius"]

        # AddNewCircleCtrRad(center, support, geodesic, radius); limitation 1 = whole circle
        circle = self._factory().AddNewCircleCtrRad(center_ref, support_ref, False, radius)
        circle.SetLimitation(1)

        return self._finish(
            circle, args.get("name"),
            f"3D circle created: radius {radius} mm on '{args['support_plane']}'.",
        )

    def _project(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        elem_ref = self._ref(args["element"])
        support_ref = self._ref(args["support"])
        projection = self._factory().AddNewProject(elem_ref, support_ref)
        return self._finish(
            projection, args.get("name"),
            f"Projection of '{args['element']}' onto '{args['support']}' created.",
        )

    def _intersection(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        ref1 = self._ref(args["element1"])
        ref2 = self._ref(args["element2"])
        inter = self._factory().AddNewIntersection(ref1, ref2)
        return self._finish(
            inter, args.get("name"),
            f"Intersection of '{args['element1']}' and '{args['element2']}' created.",
        )

    # ────────────────────────────────────────────────────────────
    # Surfaces
    # ────────────────────────────────────────────────────────────

    def _multi_section_surface(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        sections = args["sections"]
        guides = args.get("guides", [])

        loft = self._factory().AddNewLoft()
        for section_name in sections:
            ref = self._ref(section_name)
            # (section, orientation, closing point). Nothing/None = automatic.
            try:
                loft.AddSectionToLoft(ref, 1, None)
            except Exception:
                loft.AddSectionToLoft(ref, 1)
        for guide_name in guides:
            loft.AddGuide(self._ref(guide_name))

        guides_msg = f" with {len(guides)} guide(s)" if guides else ""
        return self._finish(
            loft, args.get("name"),
            f"Multi-sections surface created through {len(sections)} sections{guides_msg}.",
        )

    def _sweep(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        profile_ref = self._ref(args["profile"])
        guide_ref = self._ref(args["guide"])
        sweep = self._factory().AddNewSweepExplicit(profile_ref, guide_ref)
        return self._finish(
            sweep, args.get("name"),
            f"Swept surface created: profile '{args['profile']}' along guide '{args['guide']}'.",
        )

    def _extrude(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        factory = self._factory()
        profile_ref = self._ref(args["profile"])
        dx, dy, dz = args["direction"]
        limit1 = args["limit1"]
        limit2 = args.get("limit2", 0)

        direction = factory.AddNewDirectionByCoord(dx, dy, dz)
        extrude = factory.AddNewExtrude(profile_ref, limit1, limit2, direction)
        return self._finish(
            extrude, args.get("name"),
            f"Extruded surface created: {limit1} mm along [{dx}, {dy}, {dz}].",
        )

    def _revolve(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        profile_ref = self._ref(args["profile"])
        axis_ref = self._ref(args["axis"])
        angle1 = args.get("angle1", 360)
        angle2 = args.get("angle2", 0)
        revol = self._factory().AddNewRevol(profile_ref, angle1, angle2, axis_ref)
        return self._finish(
            revol, args.get("name"),
            f"Revolution surface created: {angle1}° around '{args['axis']}'.",
        )

    def _fill(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        boundaries = args["boundaries"]
        fill = self._factory().AddNewFill()
        for boundary_name in boundaries:
            fill.AddBound(self._ref(boundary_name))
        return self._finish(
            fill, args.get("name"),
            f"Fill surface created from {len(boundaries)} boundary curve(s).",
        )

    def _blend(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        blend = self._factory().AddNewBlend()
        blend.SetCurve(1, self._ref(args["curve1"]))
        blend.SetCurve(2, self._ref(args["curve2"]))
        return self._finish(
            blend, args.get("name"),
            f"Blend surface created between '{args['curve1']}' and '{args['curve2']}'.",
        )

    def _offset_surface(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        surface_ref = self._ref(args["surface"])
        offset = args["offset"]
        reverse = args.get("reverse", False)
        # AddNewOffset(surface, value, orientation, repetition)
        offset_surf = self._factory().AddNewOffset(surface_ref, offset, reverse, 0)
        return self._finish(
            offset_surf, args.get("name"),
            f"Offset surface created: {offset} mm from '{args['surface']}'.",
        )

    # ────────────────────────────────────────────────────────────
    # Operations
    # ────────────────────────────────────────────────────────────

    def _join(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        elements = args["elements"]
        refs = [self._ref(name) for name in elements]

        join = self._factory().AddNewJoin(refs[0], refs[1])
        for ref in refs[2:]:
            join.AddElement(ref)

        return self._finish(join, args.get("name"), f"Join created from {len(elements)} elements.")

    def _split(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        elem_ref = self._ref(args["element"])
        cutter_ref = self._ref(args["cutter"])
        orientation = -1 if args.get("reverse", False) else 1
        split = self._factory().AddNewHybridSplit(elem_ref, cutter_ref, orientation)
        return self._finish(
            split, args.get("name"),
            f"Split of '{args['element']}' by '{args['cutter']}' created.",
        )

    def _trim(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        ref1 = self._ref(args["element1"])
        ref2 = self._ref(args["element2"])
        orient1 = -1 if args.get("reverse1", False) else 1
        orient2 = -1 if args.get("reverse2", False) else 1
        trim = self._factory().AddNewHybridTrim(ref1, orient1, ref2, orient2)
        return self._finish(
            trim, args.get("name"),
            f"Trim of '{args['element1']}' with '{args['element2']}' created.",
        )

    def _symmetry(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        elem_ref = self._ref(args["element"])
        plane_ref = self._ref(args["plane"])
        symmetry = self._factory().AddNewSymmetry(elem_ref, plane_ref)
        return self._finish(
            symmetry, args.get("name"),
            f"Symmetry of '{args['element']}' about '{args['plane']}' created.",
        )

    # ────────────────────────────────────────────────────────────
    # Surface → solid bridges (Part Design features on GSD surfaces)
    # ────────────────────────────────────────────────────────────

    def _thick_surface(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()

        surface_ref = self._ref(args["surface"])
        thickness1 = args["thickness1"]
        thickness2 = args.get("thickness2", 0)

        part.InWorkObject = body
        # AddNewThickSurface(surface, isymmetric, top offset, bottom offset)
        thick = part.ShapeFactory.AddNewThickSurface(surface_ref, 0, thickness1, thickness2)
        part.UpdateObject(thick)
        self.conn.refresh_display()
        return (
            f"ThickSurface solid created from '{args['surface']}' "
            f"({thickness1}/{thickness2} mm). Feature: '{thick.Name}'"
        )

    def _close_surface(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()

        surface_ref = self._ref(args["surface"])
        part.InWorkObject = body
        close = part.ShapeFactory.AddNewCloseSurface(surface_ref)
        part.UpdateObject(close)
        self.conn.refresh_display()
        return f"CloseSurface solid created from '{args['surface']}'. Feature: '{close.Name}'"
