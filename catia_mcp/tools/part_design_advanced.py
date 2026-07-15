"""Surface-to-solid and advanced manufacturability features."""

from __future__ import annotations

from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools._geometry import GeometryContext, REF_SCHEMA, object_schema, result


class AdvancedPartDesignTools:
    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self.geo = GeometryContext(connection)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            self._d(
                "catia_close_surface",
                "Convert a watertight surface into a solid.",
                {"surface": REF_SCHEMA, "name": {"type": "string"}},
                ["surface"],
            ),
            self._d(
                "catia_build_slinky_from_points",
                "Build a solid slinky spring from explicit guide points and a circular wire profile.",
                {
                    "points": {
                        "type": "array",
                        "minItems": 3,
                        "items": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                    },
                    "wire_radius": {"type": "number", "exclusiveMinimum": 0},
                    "geoset": {"type": "string", "default": "Solution_10_Construction"},
                    "guide_name": {"type": "string", "default": "Solution_10_Guide"},
                    "profile_name": {"type": "string", "default": "Solution_10_WireProfile"},
                    "surface_name": {"type": "string", "default": "Solution_10_SweepSurface"},
                    "solid_name": {"type": "string", "default": "Solution_10_Slinky"},
                },
                ["points", "wire_radius"],
            ),
            self._d(
                "catia_thick_surface",
                "Thicken a surface into a solid.",
                {
                    "surface": REF_SCHEMA,
                    "offset1": {"type": "number"},
                    "offset2": {"type": "number", "default": 0},
                    "name": {"type": "string"},
                },
                ["surface", "offset1"],
            ),
            self._d(
                "catia_split_solid",
                "Split the current solid with a surface.",
                {
                    "surface": REF_SCHEMA,
                    "side": {"type": "string", "enum": ["normal", "reverse"], "default": "normal"},
                    "name": {"type": "string"},
                },
                ["surface"],
            ),
            self._d(
                "catia_sew_surface",
                "Sew a surface into the current solid.",
                {
                    "surface": REF_SCHEMA,
                    "side": {"type": "string", "enum": ["add", "remove"], "default": "add"},
                    "name": {"type": "string"},
                },
                ["surface"],
            ),
            self._d(
                "catia_variable_fillet",
                "Apply a variable-radius edge fillet.",
                {
                    "edge": REF_SCHEMA,
                    "radius": {"type": "number", "exclusiveMinimum": 0},
                    "variations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "vertex": REF_SCHEMA,
                                "radius": {"type": "number", "exclusiveMinimum": 0},
                            },
                            "required": ["vertex", "radius"],
                        },
                    },
                    "name": {"type": "string"},
                },
                ["edge", "radius"],
            ),
            self._d(
                "catia_face_fillet",
                "Create a fillet between two faces.",
                {
                    "face1": REF_SCHEMA,
                    "face2": REF_SCHEMA,
                    "radius": {"type": "number", "exclusiveMinimum": 0},
                    "name": {"type": "string"},
                },
                ["face1", "face2", "radius"],
            ),
            self._d(
                "catia_tritangent_fillet",
                "Create a tritangent fillet and remove a face.",
                {
                    "face1": REF_SCHEMA,
                    "face2": REF_SCHEMA,
                    "removed_face": REF_SCHEMA,
                    "radius": {"type": "number", "exclusiveMinimum": 0},
                    "name": {"type": "string"},
                },
                ["face1", "face2", "removed_face", "radius"],
            ),
            self._d(
                "catia_advanced_draft",
                "Apply casting draft to a face, keeping a neutral reference face fixed.",
                {
                    "faces": {"type": "array", "items": REF_SCHEMA, "minItems": 1},
                    "neutral": REF_SCHEMA,
                    "parting": REF_SCHEMA,
                    "pull_direction": {
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
                    },
                    "angle": {"type": "number", "minimum": -89, "maximum": 89},
                    "propagation": {
                        "type": "string",
                        "enum": ["none", "smooth"],
                        "default": "none",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["standard", "reflect_line"],
                        "default": "standard",
                    },
                    "name": {"type": "string"},
                },
                ["faces", "neutral", "pull_direction", "angle"],
            ),
        ]

    # Plane-normal shorthand for the draft pull (mold-extraction) direction.
    _PULL_NORMALS = {"xy": (0.0, 0.0, 1.0), "yz": (1.0, 0.0, 0.0), "zx": (0.0, 1.0, 0.0)}

    @classmethod
    def _pull_vector(cls, spec: Any) -> tuple[float, float, float]:
        """Resolve a draft pull direction into raw (x, y, z) doubles."""
        if isinstance(spec, dict) and {"x", "y", "z"} <= spec.keys():
            return float(spec["x"]), float(spec["y"]), float(spec["z"])
        if isinstance(spec, str) and spec.lower() in cls._PULL_NORMALS:
            return cls._PULL_NORMALS[spec.lower()]
        raise ValueError("pull_direction must be 'xy'/'yz'/'zx' or {'x':, 'y':, 'z':}")

    def _d(
        self, name: str, description: str, props: dict[str, Any], required: list[str]
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "inputSchema": object_schema(props, required),
        }

    def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        part = self.geo.part
        part.InWorkObject = self.conn.get_active_part_body()
        sf, r = self.conn.shape_factory, self.geo.resolve
        if tool_name == "catia_close_surface":
            feature = sf.AddNewCloseSurface(r(args["surface"]))
        elif tool_name == "catia_build_slinky_from_points":
            return self._build_slinky_from_points(args)
        elif tool_name == "catia_thick_surface":
            feature = sf.AddNewThickSurface(
                r(args["surface"]), 0, args["offset1"], args.get("offset2", 0)
            )
        elif tool_name == "catia_split_solid":
            feature = sf.AddNewSplit(
                r(args["surface"]), 1 if args.get("side", "normal") == "normal" else -1
            )
        elif tool_name == "catia_sew_surface":
            feature = sf.AddNewSewSurface(
                r(args["surface"]), 0 if args.get("side", "add") == "add" else 1
            )
        elif tool_name == "catia_variable_fillet":
            # CATIA's method is AddNewSolidEdgeFilletWithVaryingRadius (not
            # "...VariableRadius") and takes 4 args: edge, propagation mode,
            # variation mode, default radius. The 3-arg "...VariableRadius" name
            # does not resolve on this install (verified live 2026-07-14). Per-
            # vertex radii are set with AddImposedVertex, not
            # AddRadiusVariationAtVertex. 1 = catTangencyFilletEdgePropagation,
            # 1 = catCubicFilletVariation.
            feature = sf.AddNewSolidEdgeFilletWithVaryingRadius(
                r(args["edge"]), 1, 1, args["radius"]
            )
            for variation in args.get("variations", []):
                feature.AddImposedVertex(r(variation["vertex"]), variation["radius"])
        elif tool_name == "catia_face_fillet":
            feature = sf.AddNewSolidFaceFillet(
                r(args["face1"]), r(args["face2"]), 1, args["radius"]
            )
        elif tool_name == "catia_tritangent_fillet":
            feature = sf.AddNewSolidTritangentFillet(
                r(args["face1"]), r(args["face2"]), r(args["removed_face"]), args["radius"]
            )
        elif tool_name == "catia_advanced_draft":
            # AddNewDraft's real signature is 10 args:
            #   (face, neutral, neutralMode, parting, dirX, dirY, dirZ,
            #    mode, angle, multiselectionMode)
            # The pull direction is a vector (three doubles), NOT a reference -
            # passing a reference is why the old 6-arg call failed with
            # "Member not found" (verified live 2026-07-14). Enum values:
            # neutralMode 0=None/1=Smooth, mode 0=Standard/1=ReflectKeepFace,
            # multiselection 0=None.
            faces = args["faces"]
            dir_x, dir_y, dir_z = self._pull_vector(args["pull_direction"])
            neutral_mode = 1 if args.get("propagation") == "smooth" else 0
            draft_mode = 1 if args.get("mode") == "reflect_line" else 0
            parting = args.get("parting", args["neutral"])
            feature = sf.AddNewDraft(
                r(faces[0]),
                r(args["neutral"]),
                neutral_mode,
                r(parting),
                dir_x,
                dir_y,
                dir_z,
                draft_mode,
                args["angle"],
                0,
            )
        else:
            raise ValueError(f"Unknown advanced Part Design tool: {tool_name}")
        if args.get("name"):
            feature.Name = args["name"]
        self.geo.update(feature)
        return result(feature={"name": feature.Name, "kind": "feature"}, tool=tool_name)

    def _build_slinky_from_points(self, args: dict[str, Any]) -> str:
        points = [[float(v) for v in point] for point in args["points"]]
        wire_radius = float(args["wire_radius"])
        geoset_name = args.get("geoset") or "Solution_10_Construction"
        guide_name = args.get("guide_name") or "Solution_10_Guide"
        profile_name = args.get("profile_name") or "Solution_10_WireProfile"
        surface_name = args.get("surface_name") or "Solution_10_SweepSurface"
        solid_name = args.get("solid_name") or "Solution_10_Slinky"

        part = self.geo.part
        hsf = self.geo.hsf
        container = self.geo.geoset(geoset_name, create=True)

        guide = hsf.AddNewSpline()
        guide.Name = guide_name
        guide.SetClosing(False)
        point_refs = []
        for index, xyz in enumerate(points, start=1):
            point = hsf.AddNewPointCoord(xyz[0], xyz[1], xyz[2])
            point.Name = f"{guide_name}_Point_{index:03d}"
            container.AppendHybridShape(point)
            point_refs.append(part.CreateReferenceFromObject(point))
            guide.AddPoint(point_refs[-1])
        container.AppendHybridShape(guide)
        part.InWorkObject = guide
        part.UpdateObject(guide)

        p0 = points[0]
        p1 = points[1]
        tangent = [p1[i] - p0[i] for i in range(3)]
        tangent_len = sum(v * v for v in tangent) ** 0.5 or 1.0
        tangent = [v / tangent_len for v in tangent]
        radial = [p0[0], p0[1], 0.0]
        radial_len = (radial[0] ** 2 + radial[1] ** 2) ** 0.5 or 1.0
        n1 = [radial[0] / radial_len, radial[1] / radial_len, 0.0]
        n2 = [
            tangent[1] * n1[2] - tangent[2] * n1[1],
            tangent[2] * n1[0] - tangent[0] * n1[2],
            tangent[0] * n1[1] - tangent[1] * n1[0],
        ]
        n2_len = sum(v * v for v in n2) ** 0.5 or 1.0
        n2 = [v / n2_len for v in n2]

        start = hsf.AddNewPointCoord(p0[0], p0[1], p0[2])
        start.Name = f"{profile_name}_Center"
        pa = hsf.AddNewPointCoord(p0[0] + n1[0], p0[1] + n1[1], p0[2] + n1[2])
        pa.Name = f"{profile_name}_PlaneA"
        pb = hsf.AddNewPointCoord(p0[0] + n2[0], p0[1] + n2[1], p0[2] + n2[2])
        pb.Name = f"{profile_name}_PlaneB"
        for point in (start, pa, pb):
            container.AppendHybridShape(point)

        plane = hsf.AddNewPlane3Points(
            part.CreateReferenceFromObject(start),
            part.CreateReferenceFromObject(pa),
            part.CreateReferenceFromObject(pb),
        )
        plane.Name = f"{profile_name}_Plane"
        container.AppendHybridShape(plane)
        part.UpdateObject(plane)

        circle = hsf.AddNewCircleCtrRad(
            part.CreateReferenceFromObject(start),
            part.CreateReferenceFromObject(plane),
            False,
            wire_radius,
        )
        circle.Name = profile_name
        container.AppendHybridShape(circle)
        part.UpdateObject(circle)

        sweep = hsf.AddNewSweepExplicit(
            part.CreateReferenceFromObject(circle),
            part.CreateReferenceFromObject(guide),
        )
        sweep.Name = surface_name
        container.AppendHybridShape(sweep)
        part.UpdateObject(sweep)

        part.InWorkObject = self.conn.get_active_part_body()
        solid = self.conn.shape_factory.AddNewCloseSurface(part.CreateReferenceFromObject(sweep))
        solid.Name = solid_name
        part.UpdateObject(solid)
        self.conn.refresh_display()
        return result(
            feature={"name": solid.Name, "kind": "feature"},
            guide={"name": guide.Name, "kind": "feature"},
            surface={"name": sweep.Name, "kind": "feature"},
            points=len(points),
            wire_radius=wire_radius,
            tool="catia_build_slinky_from_points",
        )
