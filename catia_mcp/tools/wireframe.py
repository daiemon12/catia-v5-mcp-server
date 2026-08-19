"""GSD wireframe tools used to construct surface skeletons."""

from __future__ import annotations

from typing import Any, Callable

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools._geometry import GeometryContext, REF_SCHEMA, object_schema, result


def _p(name: str) -> dict[str, Any]:
    return {"name": name, "type": "number", "description": f"{name} in mm"}


class WireframeTools:
    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self.geo = GeometryContext(connection)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        common = {"name": {"type": "string"}, "geoset": {"type": "string"}}
        return [
            self._def(
                "catia_point_coord",
                "Create a 3D coordinate point.",
                {**common, "x": _p("x"), "y": _p("y"), "z": _p("z")},
                ["x", "y", "z"],
            ),
            self._def(
                "catia_point_on_curve",
                "Create a point at a percentage along a curve.",
                {
                    **common,
                    "curve": REF_SCHEMA,
                    "percent": {"type": "number", "minimum": 0, "maximum": 1},
                    "reverse": {"type": "boolean", "default": False},
                },
                ["curve", "percent"],
            ),
            self._def(
                "catia_line_pt_pt",
                "Create a line between two points.",
                {**common, "point1": REF_SCHEMA, "point2": REF_SCHEMA},
                ["point1", "point2"],
            ),
            self._def(
                "catia_plane_offset",
                "Create an offset plane.",
                {
                    **common,
                    "plane": REF_SCHEMA,
                    "offset": _p("offset"),
                    "reverse": {"type": "boolean", "default": False},
                },
                ["plane", "offset"],
            ),
            self._def(
                "catia_plane_normal",
                "Create a plane normal to a curve at a point.",
                {**common, "curve": REF_SCHEMA, "point": REF_SCHEMA},
                ["curve", "point"],
            ),
            self._def(
                "catia_plane_three_points",
                "Create a plane through three points.",
                {**common, "point1": REF_SCHEMA, "point2": REF_SCHEMA, "point3": REF_SCHEMA},
                ["point1", "point2", "point3"],
            ),
            self._def(
                "catia_spline_3d",
                "Create a 3D spline through points or XYZ triples.",
                {
                    **common,
                    "points": {
                        "type": "array",
                        "minItems": 2,
                        "items": {
                            "oneOf": [
                                REF_SCHEMA,
                                {
                                    "type": "array",
                                    "items": {"type": "number"},
                                    "minItems": 3,
                                    "maxItems": 3,
                                },
                            ]
                        },
                    },
                    "closed": {"type": "boolean", "default": False},
                },
                ["points"],
            ),
            self._def(
                "catia_circle_3d",
                "Create a full circle from center, support, and radius.",
                {
                    **common,
                    "center": REF_SCHEMA,
                    "support": REF_SCHEMA,
                    "radius": {"type": "number", "exclusiveMinimum": 0},
                },
                ["center", "support", "radius"],
            ),
            self._def(
                "catia_helix",
                "Create a helix from an axis, start point, pitch, and height.",
                {
                    **common,
                    "axis": REF_SCHEMA,
                    "start": REF_SCHEMA,
                    "pitch": {"type": "number", "exclusiveMinimum": 0},
                    "height": {"type": "number", "exclusiveMinimum": 0},
                    "taper_angle": {"type": "number", "default": 0},
                    "clockwise": {"type": "boolean", "default": False},
                },
                ["axis", "start", "pitch", "height"],
            ),
            self._def(
                "catia_project",
                "Project geometry onto a support.",
                {
                    **common,
                    "element": REF_SCHEMA,
                    "support": REF_SCHEMA,
                    "direction": {
                        "type": "string",
                        "enum": ["normal", "along"],
                        "default": "normal",
                    },
                },
                ["element", "support"],
            ),
            self._def(
                "catia_intersect",
                "Intersect two geometry elements.",
                {**common, "element1": REF_SCHEMA, "element2": REF_SCHEMA},
                ["element1", "element2"],
            ),
            self._def(
                "catia_corner",
                "Create a constant-radius corner between curves.",
                {
                    **common,
                    "curve1": REF_SCHEMA,
                    "curve2": REF_SCHEMA,
                    "support": REF_SCHEMA,
                    "radius": {"type": "number", "exclusiveMinimum": 0},
                },
                ["curve1", "curve2", "support", "radius"],
            ),
            self._def(
                "catia_connect_curve",
                "Connect curves with point/tangent/curvature continuity.",
                {
                    **common,
                    "curve1": REF_SCHEMA,
                    "curve2": REF_SCHEMA,
                    "continuity": {
                        "type": "string",
                        "enum": ["point", "tangent", "curvature"],
                        "default": "tangent",
                    },
                },
                ["curve1", "curve2"],
            ),
        ]

    def _def(
        self, name: str, description: str, properties: dict[str, Any], required: list[str]
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "inputSchema": object_schema(properties, required),
        }

    def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        hsf = self.geo.hsf
        methods: dict[str, Callable[[], Any]] = {
            "catia_point_coord": lambda: hsf.AddNewPointCoord(args["x"], args["y"], args["z"]),
            "catia_point_on_curve": lambda: hsf.AddNewPointOnCurveFromPercent(
                self.geo.resolve(args["curve"]), args["percent"], args.get("reverse", False)
            ),
            "catia_line_pt_pt": lambda: hsf.AddNewLinePtPt(
                self.geo.resolve(args["point1"]), self.geo.resolve(args["point2"])
            ),
            "catia_plane_offset": lambda: hsf.AddNewPlaneOffset(
                self.geo.resolve(args["plane"]), args["offset"], args.get("reverse", False)
            ),
            "catia_plane_normal": lambda: hsf.AddNewPlaneNormal(
                self.geo.resolve(args["curve"]), self.geo.resolve(args["point"])
            ),
            "catia_plane_three_points": lambda: hsf.AddNewPlane3Points(
                *(self.geo.resolve(args[key]) for key in ("point1", "point2", "point3"))
            ),
            "catia_circle_3d": lambda: hsf.AddNewCircleCtrRad(
                self.geo.resolve(args["center"]),
                self.geo.resolve(args["support"]),
                False,
                args["radius"],
            ),
            "catia_helix": lambda: hsf.AddNewHelix(
                self.geo.resolve(args["axis"]),
                False,
                self.geo.resolve(args["start"]),
                args["pitch"],
                args["height"],
                args.get("taper_angle", 0),
                0,
                args.get("clockwise", False),
                0,
                0,
                False,
            ),
            "catia_project": lambda: hsf.AddNewProject(
                self.geo.resolve(args["element"]), self.geo.resolve(args["support"])
            ),
            "catia_intersect": lambda: hsf.AddNewIntersection(
                self.geo.resolve(args["element1"]), self.geo.resolve(args["element2"])
            ),
            "catia_corner": lambda: hsf.AddNewCorner(
                self.geo.resolve(args["curve1"]),
                self.geo.resolve(args["curve2"]),
                self.geo.resolve(args["support"]),
                args["radius"],
                1,
                1,
                False,
            ),
            "catia_connect_curve": lambda: hsf.AddNewConnect(
                self.geo.resolve(args["curve1"]),
                self.geo.resolve(args["curve2"]),
                int({"point": 0, "tangent": 1, "curvature": 2}[args.get("continuity", "tangent")]),
                1.0,
                1.0,
                False,
            ),
        }
        if tool_name == "catia_spline_3d":
            shape = hsf.AddNewSpline()
            for point in args["points"]:
                ref = (
                    self.geo.resolve(self._coordinate_point(point, args.get("geoset")))
                    if isinstance(point, list)
                    else self.geo.resolve(point)
                )
                shape.AddPoint(ref)
            shape.SetClosing(args.get("closed", False))
        else:
            if tool_name not in methods:
                raise ValueError(f"Unknown wireframe tool: {tool_name}")
            shape = methods[tool_name]()
            if tool_name == "catia_project":
                shape.SolutionType = 0 if args.get("direction", "normal") == "normal" else 1
        handle = self.geo.append(shape, args.get("name"), args.get("geoset"))
        return result(feature=handle, tool=tool_name)

    def _coordinate_point(self, xyz: list[float], geoset: str | None) -> Any:
        point = self.geo.hsf.AddNewPointCoord(*xyz)
        self.geo.append(point, geoset=geoset)
        return point
