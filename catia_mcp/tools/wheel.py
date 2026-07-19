"""Validated high-level wheel design orchestration."""

from __future__ import annotations

import json
import math
import os
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.paths import normalize_catia_path
from catia_mcp.tools._geometry import GeometryContext, object_schema, set_revolution_angle
from catia_mcp.tools.knowledge import KnowledgeTools


DEFAULTS = {
    "hub_thickness": 28.0,
    "flange_height": 12.0,
    "flange_lip_width": 8.0,
    "bead_seat_width": 20.0,
    "safety_hump_width": 10.0,
    "safety_hump_height": 5.0,
    "drop_center_depth": 14.0,
    "rim_thickness": 8.0,
    "spoke_thickness": 16.0,
    "draft_angle": 2.0,
    "fillet_radius": 4.0,
    "valve_hole_diameter": 11.3,
    "lug_hole_diameter": 14.0,
    "material_density": 2700.0,
    "export_step": True,
    "apply_spoke_fillets": True,
    "fork_fraction": 0.42,
}


class WheelTools:
    # y_fork spoke geometry ratios (of spoke_thickness), fixed rather than
    # user-tunable to keep the schema small. The branch-root width/lateral
    # combination is chosen so a branch's root cross-section stays nested
    # inside the trunk's fork cross-section at the same radius, guaranteeing
    # the 3D overlap Part Design needs to implicitly fuse them (the same
    # trick _spoke_sections already uses to fuse the spoke onto the rim).
    _Y_TRUNK_FORK_WIDTH_RATIO = 0.80
    _Y_BRANCH_ROOT_WIDTH_RATIO = 0.55
    _Y_BRANCH_TIP_WIDTH_RATIO = 0.34
    _Y_BRANCH_ROOT_LATERAL_RATIO = 0.12

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        positive = {"type": "number", "exclusiveMinimum": 0}
        props: dict[str, Any] = {
            "rim_diameter": positive,
            "rim_width": positive,
            "offset": {"type": "number"},
            "pcd": positive,
            "bolt_count": {"type": "integer", "minimum": 3, "maximum": 10},
            "center_bore": positive,
            "spoke_count": {"type": "integer", "minimum": 3, "maximum": 30},
            "spoke_style": {"type": "string", "enum": ["simple_lofted", "y_fork"]},
            "fork_fraction": {
                "type": "number",
                "minimum": 0.2,
                "maximum": 0.7,
                "default": DEFAULTS["fork_fraction"],
            },
            "fork_spread": {"type": "number", "exclusiveMinimum": 0},
            "hub_thickness": positive,
            "flange_height": positive,
            "flange_lip_width": {**positive, "default": DEFAULTS["flange_lip_width"]},
            "bead_seat_width": {**positive, "default": DEFAULTS["bead_seat_width"]},
            "safety_hump_width": {**positive, "default": DEFAULTS["safety_hump_width"]},
            "safety_hump_height": {**positive, "default": DEFAULTS["safety_hump_height"]},
            "drop_center_depth": {**positive, "default": DEFAULTS["drop_center_depth"]},
            "rim_thickness": positive,
            "spoke_thickness": positive,
            "draft_angle": {"type": "number", "minimum": 0, "maximum": 10},
            "fillet_radius": positive,
            "valve_hole_diameter": {
                **positive,
                "default": DEFAULTS["valve_hole_diameter"],
            },
            "lug_hole_diameter": positive,
            "material_density": positive,
            "output_path": {"type": "string"},
            "export_step": {"type": "boolean", "default": True},
            "apply_spoke_fillets": {"type": "boolean", "default": True},
            "part_name": {"type": "string", "default": "MCP_Wheel"},
        }
        required = [
            "rim_diameter",
            "rim_width",
            "offset",
            "pcd",
            "bolt_count",
            "center_bore",
            "spoke_count",
            "spoke_style",
        ]
        return [
            {
                "name": "catia_design_wheel",
                "description": "Create a validated parametric cast-style wheel using the simple_lofted (single straight spoke) or y_fork (each spoke forks into two branches near the rim, mesh/BBS-style) spoke family. Requires Part Design and GSD licenses.",
                "inputSchema": object_schema(props, required),
            }
        ]

    @staticmethod
    def validate(arguments: dict[str, Any]) -> dict[str, Any]:
        values = {**DEFAULTS, **arguments}
        if values.get("spoke_style") not in ("simple_lofted", "y_fork"):
            raise ValueError("spoke_style must be 'simple_lofted' or 'y_fork'")
        for name in (
            "rim_diameter",
            "rim_width",
            "pcd",
            "center_bore",
            "hub_thickness",
            "flange_height",
            "flange_lip_width",
            "bead_seat_width",
            "safety_hump_width",
            "safety_hump_height",
            "drop_center_depth",
            "rim_thickness",
            "spoke_thickness",
            "fillet_radius",
            "valve_hole_diameter",
            "lug_hole_diameter",
            "material_density",
        ):
            if not isinstance(values.get(name), (int, float)) or values[name] <= 0:
                raise ValueError(f"{name} must be greater than zero")
        if not 3 <= values["bolt_count"] <= 10:
            raise ValueError("bolt_count must be between 3 and 10")
        if not 3 <= values["spoke_count"] <= 30:
            raise ValueError("spoke_count must be between 3 and 30")
        if values["safety_hump_height"] >= values["flange_height"]:
            raise ValueError("safety_hump_height must be less than flange_height")
        profile_end_width = (
            values["flange_lip_width"] + values["bead_seat_width"] + values["safety_hump_width"]
        )
        if values["rim_width"] <= 2 * profile_end_width:
            raise ValueError(
                "rim_width must be greater than twice the combined flange lip, "
                "bead seat and safety hump widths"
            )
        outer_radius = values["rim_diameter"] / 2
        bead_seat_radius = outer_radius - values["flange_height"]
        drop_center_radius = bead_seat_radius - values["drop_center_depth"]
        inner_radius = drop_center_radius - values["rim_thickness"]
        if inner_radius <= 0:
            raise ValueError(
                "rim_diameter, flange_height, drop_center_depth and rim_thickness "
                "leave no positive inner radius"
            )
        hub_radius = max(
            values["pcd"] / 2 + values["lug_hole_diameter"], values["center_bore"] / 2 + 15
        )
        if inner_radius <= hub_radius + values["fillet_radius"] * 2:
            raise ValueError("Rim/PCD/bore dimensions leave no radial room for spokes and fillets")
        if values["pcd"] <= values["center_bore"] + 2 * values["lug_hole_diameter"]:
            raise ValueError("PCD is too small for the center bore and lug holes")
        if abs(values["offset"]) > values["rim_width"] / 2:
            raise ValueError("offset must lie within half the rim width")
        pitch_at_hub = 2 * math.pi * hub_radius / values["spoke_count"]
        if values["spoke_thickness"] >= pitch_at_hub * 0.8:
            raise ValueError("spoke_thickness/spoke_count would cause spoke self-intersection")
        if values["spoke_style"] == "y_fork":
            if not 0.2 <= values["fork_fraction"] <= 0.7:
                raise ValueError("fork_fraction must be between 0.2 and 0.7")
            root_overlap = min(2.0, values["fillet_radius"] / 2)
            rim_overlap = values["rim_thickness"] / 2
            fork_root_radius = hub_radius - root_overlap
            fork_rim_radius = inner_radius + rim_overlap
            fork_radius = fork_root_radius + (fork_rim_radius - fork_root_radius) * values[
                "fork_fraction"
            ]
            branch_tip_width = values["spoke_thickness"] * WheelTools._Y_BRANCH_TIP_WIDTH_RATIO
            pitch_at_rim = 2 * math.pi * fork_rim_radius / values["spoke_count"]
            clearance = 2.0
            max_spread = pitch_at_rim / 2 - branch_tip_width / 2 - clearance
            if max_spread <= 0:
                raise ValueError(
                    "spoke_count/spoke_thickness leave no room for y_fork branch tips "
                    "at the rim"
                )
            fork_spread = values.get("fork_spread")
            if fork_spread is None:
                fork_spread = max_spread * 0.6
            elif fork_spread > max_spread:
                raise ValueError(
                    "fork_spread is too large for spoke_count/rim_diameter; branch tips "
                    "would intersect the neighboring spoke"
                )
            values["fork_radius"] = fork_radius
            values["fork_spread"] = fork_spread
        values["inner_radius"] = inner_radius
        values["bead_seat_radius"] = bead_seat_radius
        values["drop_center_radius"] = drop_center_radius
        values["hub_radius"] = hub_radius
        values.update(WheelTools._valve_hole_geometry(values))
        return values

    @staticmethod
    def _rim_profile_points(values: dict[str, Any]) -> list[tuple[float, float]]:
        """Return a closed (radius, axial-position) polygon for the rim shaft."""
        half_width = values["rim_width"] / 2
        lip = values["flange_lip_width"]
        seat = values["bead_seat_width"]
        hump = values["safety_hump_width"]
        outer = values["rim_diameter"] / 2
        bead = values["bead_seat_radius"]
        well = values["drop_center_radius"]
        thickness = values["rim_thickness"]

        left_hump_end = -half_width + lip + seat + hump
        right_hump_start = half_width - lip - seat - hump
        center_span = right_hump_start - left_hump_end
        transition = center_span / 3

        outer_profile = [
            (outer, -half_width),
            (bead, -half_width + lip),
            (bead, -half_width + lip + seat),
            (bead + values["safety_hump_height"], -half_width + lip + seat + hump / 2),
            (bead, left_hump_end),
            (well, left_hump_end + transition),
            (well, right_hump_start - transition),
            (bead, right_hump_start),
            (bead + values["safety_hump_height"], right_hump_start + hump / 2),
            (bead, half_width - lip - seat),
            (bead, half_width - lip),
            (outer, half_width),
        ]
        inner_profile = [(radius - thickness, axial) for radius, axial in reversed(outer_profile)]
        return outer_profile + inner_profile

    @staticmethod
    def _valve_hole_geometry(values: dict[str, Any]) -> dict[str, float]:
        """Return a radial valve drilling position clear of humps and the +X spoke."""
        half_width = values["rim_width"] / 2
        end_width = (
            values["flange_lip_width"] + values["bead_seat_width"] + values["safety_hump_width"]
        )
        center_span = values["rim_width"] - 2 * end_width
        transition = center_span / 3
        flat_left = -half_width + end_width + transition
        flat_right = half_width - end_width - transition
        hole_radius = values["valve_hole_diameter"] / 2
        clearance = 2.0
        allowed_left = flat_left + hole_radius + clearance
        allowed_right = flat_right - hole_radius - clearance
        if allowed_left > allowed_right:
            raise ValueError(
                "valve_hole_diameter does not fit on the flat drop-center wall "
                "with 2 mm clearance from its transitions"
            )

        rim_section = WheelTools._spoke_sections(values)[-1]
        spoke_low = rim_section["crown"] - rim_section["depth"] / 2
        spoke_high = rim_section["crown"] + rim_section["depth"] / 2
        candidates = (allowed_left, allowed_right)

        def axial_gap(position: float) -> float:
            hole_low = position - hole_radius
            hole_high = position + hole_radius
            if hole_high < spoke_low:
                return spoke_low - hole_high
            if spoke_high < hole_low:
                return hole_low - spoke_high
            return -min(hole_high, spoke_high) + max(hole_low, spoke_low)

        axial_position = max(candidates, key=axial_gap)
        if axial_gap(axial_position) < clearance:
            raise ValueError(
                "rim_width leaves no valve-hole position clear of the drop-center "
                "transitions and the nearest spoke"
            )

        return {
            "valve_axial_position": axial_position,
            "valve_plane_radius": values["drop_center_radius"] - values["rim_thickness"] / 2,
            "valve_pocket_depth": values["rim_thickness"] * 2,
        }

    @staticmethod
    def _spoke_sections(values: dict[str, Any]) -> list[dict[str, float]]:
        """Return radial stations and closed-section dimensions for one +X spoke."""
        root_overlap = min(2.0, values["fillet_radius"] / 2)
        rim_overlap = values["rim_thickness"] / 2
        root_radius = values["hub_radius"] - root_overlap
        rim_radius = values["inner_radius"] + rim_overlap
        crown = max(
            -values["hub_thickness"] / 3, min(values["offset"] * 0.35, values["hub_thickness"] / 3)
        )
        return [
            {
                "radius": root_radius,
                "width": values["spoke_thickness"],
                "depth": values["hub_thickness"] * 0.72,
                "crown": 0.0,
            },
            {
                "radius": root_radius + (rim_radius - root_radius) * 0.55,
                "width": values["spoke_thickness"] * 0.72,
                "depth": values["hub_thickness"] * 0.52,
                "crown": crown,
            },
            {
                "radius": rim_radius,
                "width": values["spoke_thickness"] * 0.62,
                "depth": values["hub_thickness"] * 0.42,
                "crown": crown * 0.45,
            },
        ]

    @staticmethod
    def _y_fork_sections(
        values: dict[str, Any],
    ) -> tuple[list[dict[str, float]], list[dict[str, float]], list[dict[str, float]]]:
        """Return (trunk, branch_left, branch_right) section lists for the y_fork
        spoke style: a single trunk from the hub to the fork point, then two
        branches from the fork point to their own point on the rim, offset
        tangentially ("lateral") so they splay into a Y. The branch-root
        sections are sized/offset to sit nested inside the trunk's fork-end
        cross-section (same radius, narrower width) so the three lofted
        solids overlap in 3D and Part Design fuses them into one lump, the
        same overlap trick _spoke_sections uses to fuse the spoke onto the
        hub/rim.
        """
        root_overlap = min(2.0, values["fillet_radius"] / 2)
        rim_overlap = values["rim_thickness"] / 2
        root_radius = values["hub_radius"] - root_overlap
        rim_radius = values["inner_radius"] + rim_overlap
        fork_radius = values["fork_radius"]
        crown = max(
            -values["hub_thickness"] / 3, min(values["offset"] * 0.35, values["hub_thickness"] / 3)
        )
        t = values["spoke_thickness"]
        trunk = [
            {
                "radius": root_radius,
                "width": t,
                "depth": values["hub_thickness"] * 0.72,
                "crown": 0.0,
                "lateral": 0.0,
            },
            {
                "radius": fork_radius,
                "width": t * WheelTools._Y_TRUNK_FORK_WIDTH_RATIO,
                "depth": values["hub_thickness"] * 0.5,
                "crown": crown * 0.5,
                "lateral": 0.0,
            },
        ]
        branches = []
        for side in (-1.0, 1.0):
            branches.append(
                [
                    {
                        "radius": fork_radius,
                        "width": t * WheelTools._Y_BRANCH_ROOT_WIDTH_RATIO,
                        "depth": values["hub_thickness"] * 0.5,
                        "crown": crown * 0.5,
                        "lateral": side * t * WheelTools._Y_BRANCH_ROOT_LATERAL_RATIO,
                    },
                    {
                        "radius": rim_radius,
                        "width": t * WheelTools._Y_BRANCH_TIP_WIDTH_RATIO,
                        "depth": values["hub_thickness"] * 0.38,
                        "crown": crown * 0.2,
                        "lateral": side * values["fork_spread"],
                    },
                ]
            )
        return trunk, branches[0], branches[1]

    @staticmethod
    def _spoke_guide_points(
        sections: list[dict[str, float]], side: float
    ) -> list[tuple[float, float, float]]:
        """Return global XYZ points along one upper corner of the spoke sections."""
        return [
            (
                section["radius"],
                section.get("lateral", 0.0) + side * section["width"] / 2,
                section["crown"] + section["depth"] / 2,
            )
            for section in sections
        ]

    @staticmethod
    def _spoke_section_points(section: dict[str, float]) -> list[tuple[float, float, float]]:
        """Return global XYZ corner points for a closed rounded spline section."""
        half_width = section["width"] / 2
        lateral = section.get("lateral", 0.0)
        z1 = section["crown"] - section["depth"] / 2
        z2 = section["crown"] + section["depth"] / 2
        radius = section["radius"]
        return [
            (radius, lateral - half_width, z1),
            (radius, lateral + half_width, z1),
            (radius, lateral + half_width, z2),
            (radius, lateral - half_width, z2),
        ]

    def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name != "catia_design_wheel":
            raise ValueError(f"Unknown wheel tool: {tool_name}")
        values = self.validate(args)
        report: dict[str, Any] = {
            "status": "in_progress",
            "parameters": values,
            "phases": [],
            "warnings": [
                "Engineering sign-off, Class-A surfacing, GD&T, DFM and FEA are outside this tool."
            ],
        }
        try:
            self.conn.ensure_connected()
            doc = self.conn.documents.Add("Part")
            try:
                # Part.Name is read-only on some CATIA configurations (it mirrors
                # the document name); a failed rename shouldn't abort the build.
                doc.Part.Name = values.get("part_name", "MCP_Wheel")
            except Exception:
                pass
            report["phases"].append(
                {"name": "document", "status": "complete", "feature": doc.Part.Name}
            )
            knowledge = KnowledgeTools(self.conn)
            for name, kind in (
                ("rim_diameter", "length"),
                ("rim_width", "length"),
                ("offset", "length"),
                ("pcd", "length"),
                ("bolt_count", "integer"),
                ("center_bore", "length"),
                ("spoke_count", "integer"),
                ("hub_thickness", "length"),
                ("spoke_thickness", "length"),
                ("valve_hole_diameter", "length"),
            ):
                knowledge.execute(
                    "catia_create_parameter",
                    {"name": f"Wheel_{name}", "type": kind, "value": values[name]},
                )
            report["phases"].append({"name": "parameters", "status": "complete"})
            features = self._build_geometry(values, report)
            report["features"] = features
            part_path, step_path = self._save_and_export(values, report)
            report["catpart_path"] = part_path
            report["step_path"] = step_path
            try:
                # Mass/volume/bounding-box are a bonus report, not the deliverable -
                # a built and saved solid must not be reported as "failed" just
                # because SPAWorkbench.GetMeasurable couldn't be reached.
                report["measurements"] = self._measure(values["material_density"])
            except Exception as exc:
                report["warnings"].append(
                    f"Measurement step failed (geometry was built and saved): {exc}"
                )
            report["status"] = "complete"
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = str(exc)
            report["warnings"].append("The partial CATIA document was left open for diagnosis.")
        return json.dumps(report, indent=2, ensure_ascii=False)

    @staticmethod
    def _try_rename(obj: Any, name: str) -> None:
        """Best-effort rename. Not all CATIA object types accept a written
        .Name on every configuration; a failed cosmetic rename must not abort
        the build, since nothing downstream looks features up by this name."""
        try:
            obj.Name = name
        except Exception:
            pass

    def _set_visibility(self, obj: Any, show: bool) -> bool:
        """Put a CATIA object in Show or No Show mode through the selection."""
        selection = self.conn.hso
        try:
            selection.Clear()
            selection.Add(obj)
            selection.VisProperties.SetShow(1 if show else 0)
            return True
        except Exception:
            return False
        finally:
            try:
                selection.Clear()
            except Exception:
                pass

    def _build_spoke_solid(
        self,
        part: Any,
        hsf: Any,
        construction: Any,
        body: Any,
        sections: list[dict[str, float]],
        label: str,
    ) -> Any:
        """Build one capped, closed tube solid from a 2+-station section list
        and fuse it onto the active body. Part Design implicitly unions a new
        solid feature with a body's existing material wherever the two
        overlap in 3D, which is what turns two or three of these tubes (e.g.
        a y_fork trunk plus its two branches) into one connected lump."""
        section_refs = []
        guide_point_refs: dict[str, list[Any]] = {"Left": [], "Right": []}
        for index, section in enumerate(sections, start=1):
            point_refs = []
            for point_index, xyz in enumerate(self._spoke_section_points(section), start=1):
                point = hsf.AddNewPointCoord(*xyz)
                self._try_rename(point, f"{label}_Section_{index}_Point_{point_index}")
                construction.AppendHybridShape(point)
                part.UpdateObject(point)
                point_refs.append(part.CreateReferenceFromObject(point))

            section_curve = hsf.AddNewSpline()
            for point_ref in point_refs:
                section_curve.AddPoint(point_ref)
            section_curve.SetClosing(True)
            self._try_rename(section_curve, f"{label}_Section_{index}")
            construction.AppendHybridShape(section_curve)
            part.UpdateObject(section_curve)
            section_refs.append(part.CreateReferenceFromObject(section_curve))
            guide_point_refs["Left"].append(point_refs[3])
            guide_point_refs["Right"].append(point_refs[2])

        guide_refs = []
        for side_label in ("Left", "Right"):
            spline = hsf.AddNewSpline()
            for point_ref in guide_point_refs[side_label]:
                spline.AddPoint(point_ref)
            self._try_rename(spline, f"{label}_{side_label}_Guide")
            construction.AppendHybridShape(spline)
            part.UpdateObject(spline)
            guide_refs.append(part.CreateReferenceFromObject(spline))

        loft = hsf.AddNewLoft()
        loft.SectionCoupling = 4
        for section_ref in section_refs:
            loft.AddSectionToLoft(section_ref, 1, None)
        for guide_ref in guide_refs:
            loft.AddGuide(guide_ref)
        self._try_rename(loft, f"{label}_Loft")
        construction.AppendHybridShape(loft)
        part.UpdateObject(loft)

        caps = []
        for section_ref, cap_name in (
            (section_refs[0], f"{label}_Root_Cap"),
            (section_refs[-1], f"{label}_Tip_Cap"),
        ):
            cap = hsf.AddNewFill()
            cap.AddBound(section_ref)
            self._try_rename(cap, cap_name)
            construction.AppendHybridShape(cap)
            part.UpdateObject(cap)
            caps.append(cap)

        skin = hsf.AddNewJoin(
            part.CreateReferenceFromObject(loft), part.CreateReferenceFromObject(caps[0])
        )
        skin.AddElement(part.CreateReferenceFromObject(caps[1]))
        skin.SetConnex(True)
        skin.SetManifold(1)
        skin.SetSimplify(0)
        skin.SetSuppressMode(0)
        skin.SetDeviation(0.001)
        skin.SetAngularToleranceMode(0)
        self._try_rename(skin, f"{label}_Skin")
        construction.AppendHybridShape(skin)
        part.UpdateObject(skin)

        part.InWorkObject = body
        solid = part.ShapeFactory.AddNewCloseSurface(part.CreateReferenceFromObject(skin))
        self._try_rename(solid, label)
        part.UpdateObject(solid)
        return solid

    def _build_geometry(self, v: dict[str, Any], report: dict[str, Any]) -> list[str]:
        """Build a conservative wheel solid; each phase updates before continuing."""
        part = self.conn.get_active_part()
        body = self.conn.get_active_part_body()
        origin = part.OriginElements
        names: list[str] = []
        # Revolve the complete tire-side cross-section around the wheel's Z axis.
        # On CATIA's principal YZ sketch, the vertical sketch axis maps to Z.
        sketch = body.Sketches.Add(part.CreateReferenceFromObject(origin.PlaneYZ))
        self._try_rename(sketch, "Rim_Profile")
        f = sketch.OpenEdition()
        points = self._rim_profile_points(v)
        for p1, p2 in zip(points, points[1:] + points[:1]):
            f.CreateLine(*p1, *p2)
        centerline = f.CreateLine(0, -v["rim_width"], 0, v["rim_width"])
        centerline.Construction = True
        sketch.CenterLine = centerline
        sketch.CloseEdition()
        rim = part.ShapeFactory.AddNewShaft(sketch)
        self._try_rename(rim, "Rim_Barrel")
        set_revolution_angle(rim, 360)
        part.UpdateObject(rim)
        names.append(rim.Name)
        report["phases"].append(
            {
                "name": "rim",
                "status": "complete",
                "feature": rim.Name,
                "note": "Revolved flange, bead-seat, safety-hump and drop-center profile.",
            }
        )
        # The first loft overlaps the existing rim. The hub is deliberately added
        # after the spoke pattern so every Part Design feature stays a connected solid.
        hsf = part.HybridShapeFactory
        construction = part.HybridBodies.Add()
        self._try_rename(construction, "Spoke_Construction")

        if v["spoke_style"] == "y_fork":
            trunk_sections, branch_left_sections, branch_right_sections = self._y_fork_sections(v)
            solids = [
                self._build_spoke_solid(
                    part, hsf, construction, body, trunk_sections, "Y_Spoke_Trunk"
                ),
                self._build_spoke_solid(
                    part, hsf, construction, body, branch_left_sections, "Y_Spoke_Branch_Left"
                ),
                self._build_spoke_solid(
                    part, hsf, construction, body, branch_right_sections, "Y_Spoke_Branch_Right"
                ),
            ]
            spoke_note = (
                "Trunk lofted hub-to-fork, two branches lofted fork-to-rim and fused onto "
                "the trunk by cross-section overlap, all three circularly patterned."
            )
        else:
            sections = self._spoke_sections(v)
            solids = [
                self._build_spoke_solid(part, hsf, construction, body, sections, "Lofted_Spoke")
            ]
            spoke_note = "Three-section guided crown loft closed to a solid and circularly patterned."

        center = hsf.AddNewPointCoord(0, 0, 0)
        axis_start = hsf.AddNewPointCoord(0, 0, -1)
        axis_end = hsf.AddNewPointCoord(0, 0, 1)
        for shape, name in (
            (center, "Spoke_Pattern_Center"),
            (axis_start, "Spoke_Pattern_Axis_Start"),
            (axis_end, "Spoke_Pattern_Axis_End"),
        ):
            self._try_rename(shape, name)
            construction.AppendHybridShape(shape)
        axis = hsf.AddNewLinePtPt(
            part.CreateReferenceFromObject(axis_start), part.CreateReferenceFromObject(axis_end)
        )
        self._try_rename(axis, "Spoke_Pattern_Axis")
        construction.AppendHybridShape(axis)
        part.UpdateObject(axis)

        patterns = []
        for solid in solids:
            part.InWorkObject = body
            pattern = part.ShapeFactory.AddNewCircPattern(
                solid,
                1,
                v["spoke_count"],
                0,
                360.0 / v["spoke_count"],
                1,
                1,
                part.CreateReferenceFromObject(center),
                part.CreateReferenceFromObject(axis),
                False,
                0,
                True,
            )
            self._try_rename(pattern, f"{solid.Name}_Pattern")
            part.UpdateObject(pattern)
            patterns.append(pattern)

        sketch = body.Sketches.Add(part.CreateReferenceFromObject(origin.PlaneXY))
        self._try_rename(sketch, "Hub_Profile")
        f = sketch.OpenEdition()
        f.CreateClosedCircle(0, 0, v["hub_radius"])
        sketch.CloseEdition()
        hub = part.ShapeFactory.AddNewPad(sketch, v["hub_thickness"])
        self._try_rename(hub, "Wheel_Hub")
        hub.IsSymmetric = True
        part.UpdateObject(hub)
        names.extend(solid.Name for solid in solids)
        names.extend(pattern.Name for pattern in patterns)
        names.append(hub.Name)
        report["phases"].append(
            {
                "name": "hub_and_spokes",
                "status": "complete",
                "feature": patterns[-1].Name,
                "note": spoke_note,
            }
        )
        # Spoke-root styling fillets. Best-effort and non-fatal: a dress-up
        # failure (or a wrong-edge pick from geometric selection) must never
        # discard the built, valid solid - same policy as measurement/export.
        if v.get("apply_spoke_fillets", True):
            try:
                pattern_names = [pattern.Name for pattern in patterns]
                filleted, radius, errors = self._apply_spoke_fillets(part, v, pattern_names)
                if filleted:
                    report["phases"].append(
                        {
                            "name": "spoke_fillets",
                            "status": "complete",
                            "note": f"{filleted}/{v['spoke_count']} spoke/hub-junction "
                            f"fillets at R{radius:g} mm (tangency propagation).",
                        }
                    )
                else:
                    report["phases"].append(
                        {"name": "spoke_fillets", "status": "skipped"}
                    )
                    report["warnings"].append(
                        "Spoke-root fillets could not be applied to any junction "
                        f"(solid is intact, unfilleted). First errors: {errors[:2]}"
                    )
            except Exception as exc:
                report["warnings"].append(
                    f"Spoke-root fillet phase failed (solid is intact): {exc}"
                )
        # Bore and lug holes in one through pocket.
        sketch = body.Sketches.Add(part.CreateReferenceFromObject(origin.PlaneXY))
        self._try_rename(sketch, "Bore_Lugs_Profile")
        f = sketch.OpenEdition()
        f.CreateClosedCircle(0, 0, v["center_bore"] / 2)
        for i in range(v["bolt_count"]):
            a = 2 * math.pi * i / v["bolt_count"]
            f.CreateClosedCircle(
                math.cos(a) * v["pcd"] / 2, math.sin(a) * v["pcd"] / 2, v["lug_hole_diameter"] / 2
            )
        sketch.CloseEdition()
        pocket = part.ShapeFactory.AddNewPocket(sketch, v["rim_width"] * 2)
        self._try_rename(pocket, "Center_Bore_And_Lugs")
        pocket.IsSymmetric = True
        part.UpdateObject(pocket)
        names.append(pocket.Name)
        report["phases"].append(
            {"name": "mounting_features", "status": "complete", "feature": pocket.Name}
        )

        valve_plane = hsf.AddNewPlaneOffset(
            part.CreateReferenceFromObject(origin.PlaneYZ),
            v["valve_plane_radius"],
            False,
        )
        self._try_rename(valve_plane, "Valve_Hole_Plane")
        construction.AppendHybridShape(valve_plane)
        part.UpdateObject(valve_plane)

        part.InWorkObject = body
        sketch = body.Sketches.Add(part.CreateReferenceFromObject(valve_plane))
        self._try_rename(sketch, "Valve_Hole_Profile")
        f = sketch.OpenEdition()
        f.CreateClosedCircle(
            0,
            v["valve_axial_position"],
            v["valve_hole_diameter"] / 2,
        )
        sketch.CloseEdition()
        valve_hole = part.ShapeFactory.AddNewPocket(sketch, v["valve_pocket_depth"])
        self._try_rename(valve_hole, "Valve_Hole")
        valve_hole.IsSymmetric = True
        part.UpdateObject(valve_hole)
        names.append(valve_hole.Name)
        report["phases"].append(
            {
                "name": "valve_hole",
                "status": "complete",
                "feature": valve_hole.Name,
                "note": "Radial through-hole in the flat drop-center wall.",
            }
        )
        part.Update()
        if self._set_visibility(construction, show=False):
            report["phases"].append(
                {
                    "name": "construction_visibility",
                    "status": "complete",
                    "feature": construction.Name,
                    "note": "Spoke construction geometry is hidden by default.",
                }
            )
        else:
            report["warnings"].append(
                "Spoke construction geometry could not be hidden; it remains visible."
            )
        self.conn.refresh_display()
        report["warnings"].append(
            "Back-cavity optimization, casting draft and final fillet selection require live topology qualification for the target CATIA release."
        )
        return names

    def _apply_spoke_fillets(
        self, part: Any, v: dict[str, Any], pattern_names: list[str]
    ) -> tuple[int, float, list[str]]:
        """Round each spoke/hub junction with a constant-radius edge fillet.

        Selects one junction edge per spoke by proximity to that spoke's
        centerline at the hub radius, then lets CATIA's tangency propagation
        carry the fillet around the connected junction run. Returns
        (fillet_count, radius, errors); the caller treats any shortfall as a
        non-fatal styling warning. Only the hub/root junction is filleted -
        for y_fork this means the trunk root, not the branch/rim junctions.
        """
        geo = GeometryContext(self.conn)
        sf = part.ShapeFactory
        radius = min(
            v["fillet_radius"], v["rim_thickness"] * 0.5, v["spoke_thickness"] * 0.4
        )
        hub_radius = v["hub_radius"]
        # The junction edges may be owned by either the hub pad or one of the
        # spoke pattern(s) depending on how CATIA assigned the shared boundary;
        # try all of them.
        candidate_features = ("Wheel_Hub", *pattern_names)
        filleted = 0
        errors: list[str] = []
        for i in range(v["spoke_count"]):
            theta = 2 * math.pi * i / v["spoke_count"]
            point = [hub_radius * math.cos(theta), hub_radius * math.sin(theta), 0.0]
            for feature_name in candidate_features:
                try:
                    edge = geo.resolve(
                        {"feature": feature_name, "kind": "edge", "nearest_point": point}
                    )
                    fillet = sf.AddNewSolidEdgeFilletWithConstantRadius(edge, 1, radius)
                    part.UpdateObject(fillet)
                    filleted += 1
                    break
                except Exception as exc:  # noqa: BLE001 - collected, non-fatal
                    errors.append(f"spoke {i} via {feature_name}: {exc}")
        self.conn.refresh_display()
        return filleted, radius, errors

    def _save_and_export(
        self, values: dict[str, Any], report: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        output = values.get("output_path")
        if not output:
            return None, None
        root, ext = os.path.splitext(os.path.abspath(output))
        part_path = output if ext.lower() == ".catpart" else root + ".CATPart"
        part_path = normalize_catia_path(part_path)
        self._ensure_output_path_is_not_already_open(part_path)
        self.conn.active_document.SaveAs(part_path)
        step_path = None
        if values.get("export_step", True):
            # STEP export can fail independently of the CATPart save - commonly
            # because the CATIA seat lacks an interoperability/STEP license.
            # The built and saved solid is the valuable result; a missing
            # export format must not discard it.
            try:
                candidate = root + ".stp"
                self.conn.active_document.ExportData(candidate, "stp")
                step_path = candidate
            except Exception as exc:
                report["warnings"].append(
                    f"STEP export failed (CATPart was saved successfully): {exc}"
                )
        return part_path, step_path

    def _ensure_output_path_is_not_already_open(self, part_path: str) -> None:
        """Fail fast before CATIA can raise a blocking SaveAs modal dialog."""
        active = self.conn.active_document
        target = os.path.normcase(os.path.abspath(part_path))
        for index in range(1, self.conn.documents.Count + 1):
            doc = self.conn.documents.Item(index)
            if doc is active:
                continue
            full_name = getattr(doc, "FullName", "") or ""
            if full_name and os.path.normcase(os.path.abspath(full_name)) == target:
                raise ValueError(
                    f"Output path is already open in CATIA: {part_path}. "
                    "Close that document or choose a different output_path."
                )

    def _measure(self, density: float) -> dict[str, Any]:
        part = self.conn.get_active_part()
        ref = part.CreateReferenceFromObject(self.conn.get_active_part_body())
        m = self.conn.active_document.GetWorkbench("SPAWorkbench").GetMeasurable(ref)
        data: dict[str, Any] = {}
        try:
            # Measurable returns Volume in m3 (CATIA's base SI unit), not mm3.
            volume_m3 = m.Volume
            data["volume_mm3"] = volume_m3 * 1e9
            data["mass_kg"] = volume_m3 * density  # density is kg/m3
        except Exception:
            pass
        # CATIA's Automation API has no bounding-box method on Measurable at
        # all (confirmed against pycatia's source, not a marshaling bug - see
        # measurement.py's _get_bounding_box and docs/PLAN.md); bounding_box_mm
        # is intentionally omitted rather than attempting a call that cannot
        # succeed.
        return data
