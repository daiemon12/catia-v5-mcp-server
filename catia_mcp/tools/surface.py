"""Generative Shape Design surface creation tools."""

from __future__ import annotations

from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools._geometry import GeometryContext, REF_SCHEMA, object_schema, result


class SurfaceTools:
    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self.geo = GeometryContext(connection)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        common = {"name": {"type": "string"}, "geoset": {"type": "string"}}
        refs = {"type": "array", "items": REF_SCHEMA, "minItems": 1}
        direction_schema = {
            "oneOf": [
                {"type": "string", "enum": ["xy", "yz", "zx"]},
                {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "z": {"type": "number"},
                    },
                    "required": ["x", "y", "z"],
                    "additionalProperties": False,
                },
            ]
        }
        return [
            self._d(
                "catia_extrude_surface",
                "Extrude a curve into a surface.",
                {
                    **common,
                    "profile": REF_SCHEMA,
                    "direction": direction_schema,
                    "limit1": {"type": "number"},
                    "limit2": {"type": "number", "default": 0},
                },
                ["profile", "direction", "limit1"],
            ),
            self._d(
                "catia_revolve_surface",
                "Revolve a profile around an axis.",
                {
                    **common,
                    "profile": REF_SCHEMA,
                    "axis": REF_SCHEMA,
                    "angle1": {"type": "number", "default": 0},
                    "angle2": {"type": "number", "default": 360},
                },
                ["profile", "axis"],
            ),
            self._d(
                "catia_sweep",
                "Sweep an explicit profile along a guide.",
                {**common, "profile": REF_SCHEMA, "guide": REF_SCHEMA},
                ["profile", "guide"],
            ),
            self._d(
                "catia_loft",
                "Create a multi-section surface with optional guides.",
                {
                    **common,
                    "sections": {"type": "array", "items": REF_SCHEMA, "minItems": 2},
                    "guides": refs,
                    "closing_points": {"type": "array", "items": REF_SCHEMA},
                    "continuity": {
                        "type": "string",
                        "enum": ["point", "tangent", "curvature"],
                        "default": "tangent",
                    },
                },
                ["sections"],
            ),
            self._d(
                "catia_fill",
                "Fill a closed set of boundary curves.",
                {
                    **common,
                    "boundaries": refs,
                    "continuity": {
                        "type": "string",
                        "enum": ["point", "tangent"],
                        "default": "point",
                    },
                },
                ["boundaries"],
            ),
            self._d(
                "catia_blend",
                "Create a blend between two curves on supports.",
                {
                    **common,
                    "curve1": REF_SCHEMA,
                    "support1": REF_SCHEMA,
                    "curve2": REF_SCHEMA,
                    "support2": REF_SCHEMA,
                    "continuity": {
                        "type": "string",
                        "enum": ["point", "tangent", "curvature"],
                        "default": "tangent",
                    },
                },
                ["curve1", "support1", "curve2", "support2"],
            ),
            self._d(
                "catia_join",
                "Join surfaces/curves with a connection tolerance.",
                {
                    **common,
                    "elements": {"type": "array", "items": REF_SCHEMA, "minItems": 2},
                    "tolerance": {"type": "number", "exclusiveMinimum": 0, "default": 0.001},
                    "check_connexity": {"type": "boolean", "default": True},
                },
                ["elements"],
            ),
            self._d(
                "catia_split_surface",
                "Split geometry using a cutting element.",
                {
                    **common,
                    "element": REF_SCHEMA,
                    "cutting": REF_SCHEMA,
                    "side": {"type": "string", "enum": ["normal", "reverse"], "default": "normal"},
                },
                ["element", "cutting"],
            ),
            self._d(
                "catia_trim",
                "Mutually trim two surfaces.",
                {
                    **common,
                    "element1": REF_SCHEMA,
                    "element2": REF_SCHEMA,
                    "side1": {"type": "string", "enum": ["normal", "reverse"], "default": "normal"},
                    "side2": {"type": "string", "enum": ["normal", "reverse"], "default": "normal"},
                },
                ["element1", "element2"],
            ),
            self._d(
                "catia_offset_surface",
                "Offset a surface by a constant distance.",
                {
                    **common,
                    "surface": REF_SCHEMA,
                    "offset": {"type": "number"},
                    "reverse": {"type": "boolean", "default": False},
                    "tolerance": {"type": "number", "exclusiveMinimum": 0, "default": 0.001},
                },
                ["surface", "offset"],
            ),
            self._d(
                "catia_extrapolate",
                "Extrapolate a surface from a boundary.",
                {
                    **common,
                    "boundary": REF_SCHEMA,
                    "support": REF_SCHEMA,
                    "length": {"type": "number", "exclusiveMinimum": 0},
                    "continuity": {
                        "type": "string",
                        "enum": ["point", "tangent", "curvature"],
                        "default": "tangent",
                    },
                },
                ["boundary", "support", "length"],
            ),
        ]

    def _d(
        self, name: str, description: str, props: dict[str, Any], required: list[str]
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "inputSchema": object_schema(props, required),
        }

    def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        hsf = self.geo.hsf
        r = self.geo.resolve
        if tool_name == "catia_extrude_surface":
            shape = hsf.AddNewExtrude(
                r(args["profile"]),
                args["limit1"],
                args.get("limit2", 0),
                self.geo.direction(args["direction"]),
            )
        elif tool_name == "catia_revolve_surface":
            shape = hsf.AddNewRevol(
                r(args["profile"]), args.get("angle1", 0), args.get("angle2", 360), r(args["axis"])
            )
        elif tool_name == "catia_sweep":
            shape = hsf.AddNewSweepExplicit(r(args["profile"]), r(args["guide"]))
        elif tool_name == "catia_loft":
            shape = hsf.AddNewLoft()
            continuity = {"point": 0, "tangent": 1, "curvature": 2}[
                args.get("continuity", "tangent")
            ]
            closing = args.get("closing_points", [])
            for index, section in enumerate(args["sections"]):
                close_ref = r(closing[index]) if index < len(closing) else None
                shape.AddSectionToLoft(r(section), continuity, close_ref)
            for guide in args.get("guides", []):
                shape.AddGuide(r(guide))
        elif tool_name == "catia_fill":
            shape = hsf.AddNewFill()
            continuity = 0 if args.get("continuity", "point") == "point" else 1
            for boundary in args["boundaries"]:
                shape.AddBound(r(boundary))
                try:
                    shape.SetContinuity(len(args["boundaries"]), continuity)
                except Exception:
                    pass
        elif tool_name == "catia_blend":
            shape = hsf.AddNewBlend()
            shape.SetCurve(1, r(args["curve1"]))
            shape.SetSupport(1, r(args["support1"]))
            shape.SetCurve(2, r(args["curve2"]))
            shape.SetSupport(2, r(args["support2"]))
            continuity = {"point": 0, "tangent": 1, "curvature": 2}[
                args.get("continuity", "tangent")
            ]
            shape.SetContinuity(1, continuity)
            shape.SetContinuity(2, continuity)
        elif tool_name == "catia_join":
            elements = args["elements"]
            shape = hsf.AddNewJoin(r(elements[0]), r(elements[1]))
            for element in elements[2:]:
                shape.AddElement(r(element))
            shape.SetConnex(args.get("check_connexity", True))
            shape.SetManifold(1)
            shape.SetSimplify(0)
            shape.SetSuppressMode(0)
            shape.SetDeviation(args.get("tolerance", 0.001))
            shape.SetAngularToleranceMode(0)
        elif tool_name == "catia_split_surface":
            side = 1 if args.get("side", "normal") == "normal" else -1
            shape = hsf.AddNewHybridSplit(r(args["element"]), r(args["cutting"]), side)
        elif tool_name == "catia_trim":
            side1 = 1 if args.get("side1", "normal") == "normal" else -1
            side2 = 1 if args.get("side2", "normal") == "normal" else -1
            shape = hsf.AddNewHybridTrim(r(args["element1"]), side1, r(args["element2"]), side2)
        elif tool_name == "catia_offset_surface":
            shape = hsf.AddNewOffset(
                r(args["surface"]),
                args["offset"],
                args.get("reverse", False),
                args.get("tolerance", 0.001),
            )
        elif tool_name == "catia_extrapolate":
            shape = hsf.AddNewExtrapolLength(
                r(args["boundary"]), r(args["support"]), args["length"]
            )
            shape.Continuity = {"point": 0, "tangent": 1, "curvature": 2}[
                args.get("continuity", "tangent")
            ]
        else:
            raise ValueError(f"Unknown surface tool: {tool_name}")
        handle = self.geo.append(shape, args.get("name"), args.get("geoset"))
        return result(feature=handle, tool=tool_name)
