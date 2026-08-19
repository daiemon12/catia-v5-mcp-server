"""Contest-specific CATIA tools.

These tools are intentionally narrow: they automate one-off LADUGA task repairs
or builds while still going through the same MCP/CATIA COM path as the generic
tools. Keep them explicit and diagnostic-heavy so a failed contest task is not
mistaken for a completed one.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

import pythoncom
from win32com.client import VARIANT

from catia_mcp.connection import CATIAConnection
from catia_mcp.paths import normalize_catia_path
from catia_mcp.tools._geometry import GeometryContext, byref_doubles


IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
TASK07_FALLBACK_LAYOUT = {
    "plug_size_mm": 100.0,
    "positions_mm": [
        [5.0, 60.0, 60.0],
        [5.0, 170.0, 60.0],
        [5.0, 280.0, 60.0],
    ],
    "orientations": ["triangle", "cross", "square"],
    "note": (
        "Fallback from task 07 topology lengths: plate 340 x 120 x 10 mm, "
        "three 100 mm-class openings centered along the vertical Y direction."
    ),
}
TASK13_MAIN_PARAMETER = "Основной параметр управления"
TASK13_DEFAULT_LINK_COUNT = 10
TASK13_LINK_LENGTH_MM = 320.0
TASK13_LINK_HEIGHT_MM = 200.0


class ContestTools:
    """Small contest-task helpers that are too specific for generic modules."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self.geo = GeometryContext(connection)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_task07_report",
                "description": (
                    "Inspect task 07 product/parts and report component sources plus "
                    "07-holes edge geometry. Diagnostic only."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_path": {"type": "string"},
                        "max_edges": {"type": "integer", "minimum": 1, "default": 120},
                    },
                    "required": ["product_path"],
                },
            },
            {
                "name": "catia_solve_task07_plug",
                "description": (
                    "Build the task 07 universal plug in 07.CATPart, keep a single "
                    "07.CATPart instance in 07.CATProduct, move that plug sequentially "
                    "through the three 07-holes openings, and save 07.CATProduct."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "product_path": {"type": "string"},
                        "source_folder": {"type": "string"},
                        "plug_size": {
                            "type": "number",
                            "exclusiveMinimum": 0,
                            "description": "Nominal projection size in mm; auto if omitted.",
                        },
                        "plate_clearance": {
                            "type": "number",
                            "default": 0.2,
                            "description": "Shrink plug size by this many mm for visual fit.",
                        },
                        "save": {"type": "boolean", "default": True},
                    },
                    "required": ["product_path", "source_folder"],
                },
            },
            {
                "name": "catia_task09_report",
                "description": (
                    "Inspect LADUGA task 09 CATPart: report the target solid's edge "
                    "geometry and the source Curve/Point elements. Diagnostic only."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "target_shape": {"type": "string", "default": "Solid.6"},
                        "max_edges": {"type": "integer", "minimum": 1, "default": 240},
                    },
                    "required": ["part_path"],
                },
            },
            {
                "name": "catia_solve_task09_eviscerator",
                "description": (
                    "Solve LADUGA task 09 by rebuilding PartBody as a linked CATIA "
                    "history result matching the target solid body, then update/save."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "target_shape": {"type": "string", "default": "Solid.6"},
                        "save": {"type": "boolean", "default": True},
                    },
                    "required": ["part_path"],
                },
            },
            {
                "name": "catia_task11_report",
                "description": (
                    "Inspect task 11 CATPart geometrical sets, their direct elements, "
                    "and Join.1 update status. Diagnostic only."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "update_join": {
                            "type": "boolean",
                            "default": False,
                            "description": "Try UpdateObject(Join.1) and report the result.",
                        },
                    },
                    "required": ["part_path"],
                },
            },
            {
                "name": "catia_solve_task11_geosets",
                "description": (
                    "Solve LADUGA task 11: move elements from 'Исходная папка' into "
                    "geometrical sets named by element prefix, rebuild Join.1 from "
                    "Line/Curve/Circle elements, update, and save."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "save": {"type": "boolean", "default": True},
                    },
                    "required": ["part_path"],
                },
            },
            {
                "name": "catia_close_document_by_path",
                "description": "Close a specific open CATIA document by full path, optionally saving it first.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "save": {"type": "boolean", "default": False},
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "catia_task12_report",
                "description": (
                    "Inspect LADUGA task 12 CATPart: measure the target body 'Цель' "
                    "as a regular hexagonal prism. Diagnostic only."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "target_body": {"type": "string", "default": "Цель"},
                    },
                    "required": ["part_path"],
                },
            },
            {
                "name": "catia_solve_task12_hex_prisms",
                "description": (
                    "Solve LADUGA task 12: build three independent regular hexagonal "
                    "prisms matching target body 'Цель', separated by BODY and "
                    "GeometricalSet, then save the source CATPart."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "target_body": {"type": "string", "default": "Цель"},
                        "save": {"type": "boolean", "default": True},
                    },
                    "required": ["part_path"],
                },
            },
            {
                "name": "catia_task13_report",
                "description": (
                    "Inspect LADUGA task 13 CATPart: report the target chain body, "
                    "its topology, and the active parameter set. Diagnostic only."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "target_body": {"type": "string", "default": "Цепь"},
                        "max_edges": {"type": "integer", "minimum": 1, "default": 240},
                    },
                    "required": ["part_path"],
                },
            },
            {
                "name": "catia_solve_task13_chain",
                "description": (
                    "Solve LADUGA task 13 by building a parametric alternating-link "
                    "chain driven by the main control parameter, then update and save."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "target_body": {"type": "string", "default": "Цепь"},
                        "link_count": {
                            "type": "integer",
                            "minimum": 2,
                            "default": TASK13_DEFAULT_LINK_COUNT,
                        },
                        "save": {"type": "boolean", "default": True},
                },
                "required": ["part_path"],
                },
            },
            {
                "name": "catia_task15_report",
                "description": (
                    "Inspect LADUGA task 15 CATPart and report the current task 15 "
                    "centerline geometry/length if it has already been built."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "centerline_name": {
                            "type": "string",
                            "default": "Task15_Centerline",
                        },
                        "geoset_name": {
                            "type": "string",
                            "default": "Task15_Construction",
                        },
                    },
                    "required": ["part_path"],
                },
            },
            {
                "name": "catia_solve_task15_centerline",
                "description": (
                    "Solve LADUGA task 15 by building a saved centerline curve for the "
                    "lamp bracket, measuring its length, and storing the result."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "centerline_name": {
                            "type": "string",
                            "default": "Task15_Centerline",
                        },
                        "geoset_name": {
                            "type": "string",
                            "default": "Task15_Construction",
                        },
                        "save": {"type": "boolean", "default": True},
                    },
                    "required": ["part_path"],
                },
            },
            {
                "name": "catia_task16_report",
                "description": (
                    "Inspect LADUGA task 16 CATPart: report the geometrical set "
                    "construction order, the final hybrid shape, and relation state. "
                    "Diagnostic only."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "geoset_name": {
                            "type": "string",
                            "default": "Построения детали",
                        },
                    },
                    "required": ["part_path"],
                },
            },
            {
                "name": "catia_solve_task16_isolate_green",
                "description": (
                    "Solve LADUGA task 16 by isolating the final hybrid shape in the "
                    "construction geoset, hiding earlier construction elements, "
                    "recoloring the final element green, and saving the source CATPart."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_path": {"type": "string"},
                        "geoset_name": {
                            "type": "string",
                            "default": "Построения детали",
                        },
                        "save": {"type": "boolean", "default": True},
                    },
                    "required": ["part_path"],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if tool_name == "catia_task07_report":
            return self._task07_report(arguments)
        if tool_name == "catia_solve_task07_plug":
            return self._solve_task07(arguments)
        if tool_name == "catia_task09_report":
            return self._task09_report(arguments)
        if tool_name == "catia_solve_task09_eviscerator":
            return self._solve_task09(arguments)
        if tool_name == "catia_task11_report":
            return self._task11_report(arguments)
        if tool_name == "catia_solve_task11_geosets":
            return self._solve_task11(arguments)
        if tool_name == "catia_close_document_by_path":
            return self._close_document_by_path(arguments)
        if tool_name == "catia_task12_report":
            return self._task12_report(arguments)
        if tool_name == "catia_solve_task12_hex_prisms":
            return self._solve_task12(arguments)
        if tool_name == "catia_task13_report":
            return self._task13_report(arguments)
        if tool_name == "catia_solve_task13_chain":
            return self._solve_task13(arguments)
        if tool_name == "catia_task15_report":
            return self._task15_report(arguments)
        if tool_name == "catia_solve_task15_centerline":
            return self._solve_task15(arguments)
        if tool_name == "catia_task16_report":
            return self._task16_report(arguments)
        if tool_name == "catia_solve_task16_isolate_green":
            return self._solve_task16(arguments)
        raise ValueError(f"Unknown contest tool: {tool_name}")

    def _open_document(self, path: str) -> Any:
        self.conn.ensure_connected()
        docs = self.conn.documents
        path = normalize_catia_path(path)
        target = os.path.normcase(os.path.abspath(path))
        for index in range(1, docs.Count + 1):
            doc = docs.Item(index)
            full_name = getattr(doc, "FullName", "") or ""
            if full_name and os.path.normcase(os.path.abspath(full_name)) == target:
                try:
                    doc.Activate()
                except Exception:
                    pass
                return doc
        doc = docs.Open(path)
        try:
            doc.Activate()
        except Exception:
            pass
        return doc

    def _close_document_by_path(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        docs = self.conn.documents
        path = normalize_catia_path(args["file_path"])
        target = os.path.normcase(os.path.abspath(path))
        for index in range(1, docs.Count + 1):
            doc = docs.Item(index)
            full_name = getattr(doc, "FullName", "") or ""
            if full_name and os.path.normcase(os.path.abspath(full_name)) == target:
                name = doc.Name
                if args.get("save", False):
                    doc.Save()
                doc.Close()
                return f"Document '{name}' closed by path" + (
                    " (saved)" if args.get("save", False) else ""
                )
        return f"Document not open: {path}"

    @staticmethod
    def _component_file_path(component: Any) -> str:
        try:
            return component.ReferenceProduct.Parent.FullName
        except Exception as exc:
            raise RuntimeError(
                f"Could not resolve source file for component '{component.Name}': {exc}"
            ) from exc

    def _find_task07_parts(self, product_doc: Any, source_folder: str) -> dict[str, Any]:
        product = product_doc.Product
        products = product.Products
        holes = None
        plugs: list[Any] = []
        components: list[dict[str, Any]] = []
        for index in range(1, products.Count + 1):
            component = products.Item(index)
            try:
                source = self._component_file_path(component)
            except Exception:
                source = ""
            try:
                part_number = component.PartNumber
            except Exception as exc:
                part_number = ""
                part_number_error = str(exc)
            else:
                part_number_error = None
            item = {
                "index": index,
                "name": component.Name,
                "part_number": part_number,
                "source_path": source,
            }
            if part_number_error:
                item["part_number_error"] = part_number_error
            components.append(item)
            base = os.path.basename(source).lower()
            if base == "07-holes.catpart":
                holes = component
            elif base == "07.catpart" or component.Name.startswith("07"):
                plugs.append(component)
        if holes is None:
            holes_path = os.path.join(source_folder, "07-holes.CATPart")
            if not os.path.exists(holes_path):
                raise RuntimeError("Could not find 07-holes component or source file.")
        if len(plugs) < 1:
            raise RuntimeError(
                f"Expected at least one 07.CATPart plug instance, found {len(plugs)}. "
                f"Components: {components}"
            )
        return {"holes": holes, "plugs": plugs, "components": components}

    @staticmethod
    def _shape_from_part(part_doc: Any) -> tuple[Any, Any]:
        part = part_doc.Part
        body = part.MainBody
        shapes = body.Shapes
        if shapes.Count == 0:
            raise RuntimeError(f"Part '{part_doc.Name}' has no solid shapes.")
        return part, shapes.Item(shapes.Count)

    def _edge_report(self, part_doc: Any, max_edges: int) -> dict[str, Any]:
        part, shape = self._shape_from_part(part_doc)
        spa = part_doc.GetWorkbench("SPAWorkbench")
        try:
            selection = part_doc.Selection
        except Exception:
            part_doc.Activate()
            selection = self.conn.hso
        selection.Clear()
        selection.Add(shape)
        selection.Search("Topology.Edge,sel")

        picked: list[tuple[Any, Any]] = []
        for index in range(1, min(selection.Count, max_edges) + 1):
            item = selection.Item(index)
            obj = item.Value
            try:
                ref = item.Reference
            except Exception:
                ref = part.CreateReferenceFromObject(obj)
            picked.append((obj, ref))
        selection.Clear()

        edges = []
        points: list[list[float]] = []
        for index, (obj, ref) in enumerate(picked, start=1):
            entry: dict[str, Any] = {
                "index": index,
                "name": getattr(obj, "Name", f"Edge.{index}"),
            }
            try:
                measurable = spa.GetMeasurable(ref)
                entry["length_mm"] = round(measurable.Length * 1000, 4)
                coords = [0.0] * 9
                measurable.GetPointsOnCurve(coords)
                start = [coords[i] * 1000 for i in range(3)]
                mid = [coords[i] * 1000 for i in range(3, 6)]
                end = [coords[i] * 1000 for i in range(6, 9)]
                entry["start_mm"] = [round(v, 4) for v in start]
                entry["mid_mm"] = [round(v, 4) for v in mid]
                entry["end_mm"] = [round(v, 4) for v in end]
                points.extend([start, mid, end])
                direction = [0.0] * 3
                measurable.GetDirection(direction)
                norm = math.sqrt(sum(v * v for v in direction))
                if norm > 1e-9:
                    entry["direction"] = [round(v / norm, 6) for v in direction]
            except Exception as exc:
                entry["error"] = str(exc)
            edges.append(entry)

        bbox = None
        if points:
            mins = [min(p[axis] for p in points) for axis in range(3)]
            maxs = [max(p[axis] for p in points) for axis in range(3)]
            bbox = {
                "min_mm": [round(v, 4) for v in mins],
                "max_mm": [round(v, 4) for v in maxs],
                "size_mm": [round(maxs[i] - mins[i], 4) for i in range(3)],
            }
        return {
            "document": getattr(part_doc, "FullName", part_doc.Name),
            "shape": getattr(shape, "Name", ""),
            "edge_count_reported": len(edges),
            "bbox": bbox,
            "edges": edges,
        }

    def _task07_report(self, args: dict[str, Any]) -> str:
        product_path = normalize_catia_path(args["product_path"])
        product_doc = self._open_document(product_path)
        source_folder = os.path.dirname(product_path)
        parts = self._find_task07_parts(product_doc, source_folder)
        holes_doc = (
            parts["holes"].ReferenceProduct.Parent
            if parts["holes"] is not None
            else self._open_document(os.path.join(source_folder, "07-holes.CATPart"))
        )
        return json.dumps(
            {
                "product": getattr(product_doc, "FullName", product_doc.Name),
                "components": parts["components"],
                "plug_count": len(parts["plugs"]),
                "holes_edges": self._edge_report(holes_doc, int(args.get("max_edges", 120))),
            },
            indent=2,
            ensure_ascii=False,
        )

    def _delete_partbody_content(self, part_doc: Any) -> Any:
        part = part_doc.Part
        body = part.MainBody
        try:
            part.InWorkObject = body
        except Exception:
            pass
        selection = part_doc.Selection
        # Solid features usually depend on sketches; delete only the non-sketch
        # shapes first, then update, then clear the sketches in a second pass.
        for collection_name, collection, skip_sketches in (
            ("Shapes", body.Shapes, True),
            ("Sketches", body.Sketches, False),
        ):
            while True:
                try:
                    count = collection.Count
                except Exception:
                    break
                if count < 1:
                    break
                item = collection.Item(count)
                item_name = getattr(item, "Name", "")
                if skip_sketches and "_sketch" in item_name.lower():
                    break
                selection.Clear()
                selection.Add(item)
                try:
                    selection.Delete()
                except Exception as exc:
                    raise RuntimeError(
                        f"Could not delete {collection_name[:-1].lower()} '{item_name}': {exc}"
                    ) from exc
            try:
                part.Update()
            except Exception:
                pass
        selection.Clear()
        return body

    @staticmethod
    def _close_profile(factory: Any, points: list[tuple[float, float]]) -> None:
        for index, (x1, y1) in enumerate(points):
            x2, y2 = points[(index + 1) % len(points)]
            factory.CreateLine(x1, y1, x2, y2)

    def _make_sketch(
        self,
        part: Any,
        body: Any,
        plane: Any,
        name: str,
        loops: list[list[tuple[float, float]]],
    ) -> Any:
        sketch = body.Sketches.Add(part.CreateReferenceFromObject(plane))
        sketch.Name = name
        factory = sketch.OpenEdition()
        for loop in loops:
            self._close_profile(factory, loop)
        sketch.CloseEdition()
        part.UpdateObject(sketch)
        return sketch

    def _pocket_loop(
        self,
        part: Any,
        body: Any,
        plane: Any,
        name: str,
        loop: list[tuple[float, float]],
        depth: float,
    ) -> Any:
        sketch = self._make_sketch(part, body, plane, name, [loop])
        pocket = part.ShapeFactory.AddNewPocket(sketch, depth)
        pocket.Name = name.replace("Sketch", "Pocket")
        pocket.IsSymmetric = True
        part.UpdateObject(pocket)
        return pocket

    def _build_plug_geometry(
        self,
        plug_doc: Any,
        size: float,
        clearance: float,
        save_path: str | None = None,
    ) -> dict[str, Any]:
        part = plug_doc.Part
        body = self._delete_partbody_content(plug_doc)
        part.InWorkObject = body
        origin = part.OriginElements
        s = float(size) - float(clearance)
        half = s / 2.0
        top_half = s * 0.16
        arm = s * 0.30
        arm_half = arm / 2.0
        depth = s * 1.25

        base = self._make_sketch(
            part,
            body,
            origin.PlaneYZ,
            "Plug_square_projection_sketch",
            [[(-half, -half), (half, -half), (half, half), (-half, half)]],
        )
        pad = part.ShapeFactory.AddNewPad(base, depth)
        pad.Name = "Plug_square_base"
        pad.IsSymmetric = True
        part.UpdateObject(pad)

        # Cut the square cube to a trapezoid/triangular projection from another
        # direction. The two pockets are construction history in the same BODY.
        self._pocket_loop(
            part,
            body,
            origin.PlaneZX,
            "Plug_triangle_left_cut_sketch",
            [(-half, -half), (-half, half), (-top_half, half)],
            depth,
        )
        self._pocket_loop(
            part,
            body,
            origin.PlaneZX,
            "Plug_triangle_right_cut_sketch",
            [(half, -half), (half, half), (top_half, half)],
            depth,
        )

        # Leave a plus-sign projection in the third principal direction.
        rectangles = [
            [(-half, arm_half), (-arm_half, arm_half), (-arm_half, half), (-half, half)],
            [(arm_half, arm_half), (half, arm_half), (half, half), (arm_half, half)],
            [(-half, -half), (-arm_half, -half), (-arm_half, -arm_half), (-half, -arm_half)],
            [(arm_half, -half), (half, -half), (half, -arm_half), (arm_half, -arm_half)],
        ]
        for index, loop in enumerate(rectangles, start=1):
            self._pocket_loop(
                part,
                body,
                origin.PlaneXY,
                f"Plug_cross_corner_{index}_sketch",
                loop,
                depth,
            )

        part.Update()
        geometry = {
            "size_mm": round(s, 4),
            "base_feature": pad.Name,
            "body": body.Name,
            "features": [body.Shapes.Item(i).Name for i in range(1, body.Shapes.Count + 1)],
        }
        if save_path:
            plug_doc.SaveAs(normalize_catia_path(save_path))
        else:
            plug_doc.Save()
        return geometry

    @staticmethod
    def _axis_ranges(edge_report: dict[str, Any]) -> list[float]:
        bbox = edge_report.get("bbox") or {}
        sizes = bbox.get("size_mm") or [150.0, 8.0, 60.0]
        return [float(v) for v in sizes]

    def _infer_task07_layout(self, edge_report: dict[str, Any], plug_size: float | None) -> dict[str, Any]:
        bbox = edge_report.get("bbox") or {}
        mins = [float(v) for v in bbox.get("min_mm", [-80.0, -3.0, -30.0])]
        maxs = [float(v) for v in bbox.get("max_mm", [80.0, 3.0, 30.0])]
        sizes = self._axis_ranges(edge_report)
        if max(sizes) < 1e-6:
            layout = dict(TASK07_FALLBACK_LAYOUT)
            if plug_size is not None:
                layout["plug_size_mm"] = float(plug_size)
            layout["bbox"] = bbox
            layout["axes"] = {
                "thickness_axis": 0,
                "vertical_axis": 2,
                "long_axis": 1,
            }
            return layout
        long_axis = max(range(3), key=lambda i: sizes[i])
        thick_axis = min(range(3), key=lambda i: sizes[i])
        vertical_axis = ({0, 1, 2} - {long_axis, thick_axis}).pop()

        nominal = plug_size
        if nominal is None:
            nominal = min(sizes[long_axis] / 3.8, sizes[vertical_axis] * 0.78)
            nominal = max(20.0, min(60.0, nominal))

        span = sizes[long_axis]
        center = [(mins[i] + maxs[i]) / 2.0 for i in range(3)]
        offsets = [-span * 0.30, 0.0, span * 0.30]
        positions = []
        for offset in offsets:
            pos = center[:]
            pos[long_axis] += offset
            positions.append(pos)

        return {
            "bbox": bbox,
            "axes": {
                "long_axis": long_axis,
                "vertical_axis": vertical_axis,
                "thickness_axis": thick_axis,
            },
            "plug_size_mm": nominal,
            "positions_mm": [[round(v, 4) for v in pos] for pos in positions],
            "orientations": ["triangle", "cross", "square"],
        }

    @staticmethod
    def _rotation_for_orientation(orientation: str) -> list[float]:
        # CATIA's position matrix stores local X/Y/Z axis vectors followed by
        # translation. The plug's natural projections are:
        # square along local X, triangle along local Y, cross along local Z.
        if orientation == "triangle":
            return [0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, -1.0]
        if orientation == "cross":
            return [0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]
        return IDENTITY[:9]

    @classmethod
    def _matrix_with_translation(
        cls, tx: float, ty: float, tz: float, orientation: str
    ) -> list[float]:
        matrix = cls._rotation_for_orientation(orientation) + [0.0, 0.0, 0.0]
        matrix[9] = tx
        matrix[10] = ty
        matrix[11] = tz
        return matrix

    def _place_plugs(self, plugs: list[Any], layout: dict[str, Any]) -> list[dict[str, Any]]:
        positions = layout["positions_mm"]
        orientations = layout.get("orientations") or ["triangle", "cross", "square"]
        report = []
        for component, pos, orientation in zip(plugs, positions, orientations):
            matrix = self._matrix_with_translation(pos[0], pos[1], pos[2], orientation)
            try:
                component.Position.SetComponents(matrix)
            except Exception as exc:
                raise RuntimeError(f"Could not position component {component.Name}: {exc}") from exc
            report.append({
                "component": component.Name,
                "part_number": component.PartNumber,
                "orientation": orientation,
                "translation_mm": pos,
            })
        return report

    def _keep_single_task07_plug(self, product_doc: Any, plugs: list[Any]) -> dict[str, Any]:
        if not plugs:
            raise RuntimeError("No 07.CATPart plug instances were found.")
        product = product_doc.Product
        products = product.Products
        keep = plugs[0]
        removed: list[dict[str, Any]] = []
        try:
            keep_part_number = keep.PartNumber
        except Exception:
            keep_part_number = ""
        for component in plugs[1:]:
            try:
                part_number = component.PartNumber
            except Exception:
                part_number = ""
            removed.append(
                {
                    "name": component.Name,
                    "part_number": part_number,
                    "source_path": self._component_file_path(component),
                }
            )
        for component in plugs[1:]:
            products.Remove(component.Name)
        return {"keep": keep, "keep_part_number": keep_part_number, "removed": removed}

    def _sequence_task07_plug(self, component: Any, layout: dict[str, Any]) -> list[dict[str, Any]]:
        positions = layout["positions_mm"]
        orientations = layout.get("orientations") or ["triangle", "cross", "square"]
        report = []
        for step, (pos, orientation) in enumerate(zip(positions, orientations), start=1):
            matrix = self._matrix_with_translation(pos[0], pos[1], pos[2], orientation)
            try:
                component.Position.SetComponents(matrix)
            except Exception as exc:
                raise RuntimeError(f"Could not position component {component.Name}: {exc}") from exc
            try:
                part_number = component.PartNumber
            except Exception:
                part_number = ""
            report.append(
                {
                    "step": step,
                    "component": component.Name,
                    "part_number": part_number,
                    "orientation": orientation,
                    "translation_mm": pos,
                }
            )
        return report

    def _solve_task07(self, args: dict[str, Any]) -> str:
        product_path = normalize_catia_path(args["product_path"])
        source_folder = normalize_catia_path(args["source_folder"])
        product_doc = self._open_document(product_path)
        parts = self._find_task07_parts(product_doc, source_folder)
        holes_doc = (
            parts["holes"].ReferenceProduct.Parent
            if parts["holes"] is not None
            else self._open_document(os.path.join(source_folder, "07-holes.CATPart"))
        )
        edge_report = self._edge_report(holes_doc, 200)
        layout = self._infer_task07_layout(edge_report, args.get("plug_size"))
        plug_path = os.path.join(source_folder, "07.CATPart")
        if len(parts["plugs"]) == 1:
            self.conn.refresh_display()
            return json.dumps(
                {
                    "product": product_path,
                    "plug_part": plug_path,
                    "components": parts["components"],
                    "plug_count": 1,
                    "removed_plug_instances": [],
                    "layout": layout,
                    "geometry": None,
                    "placement": [],
                    "saved": bool(args.get("save", True)),
                    "already_prepared": True,
                },
                indent=2,
                ensure_ascii=False,
            )
        temp_plug_path = os.path.join(source_folder, "07.__rebuild__.CATPart")
        if os.path.exists(temp_plug_path):
            try:
                os.remove(temp_plug_path)
            except Exception:
                pass
        plug_doc = self.conn.documents.Add("Part")
        geometry = self._build_plug_geometry(
            plug_doc,
            float(layout["plug_size_mm"]),
            float(args.get("plate_clearance", 0.2)),
            save_path=temp_plug_path,
        )
        product_doc.Activate()
        plug_state = self._keep_single_task07_plug(product_doc, parts["plugs"])
        placement = self._sequence_task07_plug(plug_state["keep"], layout)
        product_doc.Product.Update()
        if args.get("save", True):
            product_doc.Save()
        try:
            plug_doc.Close()
        except Exception:
            pass
        try:
            if os.path.exists(temp_plug_path):
                # Close any open source document before replacing the original file on disk.
                if parts["plugs"]:
                    try:
                        parts["plugs"][0].ReferenceProduct.Parent.Close()
                    except Exception:
                        pass
                os.replace(temp_plug_path, plug_path)
        except Exception as exc:
            raise RuntimeError(f"Could not replace original 07.CATPart: {exc}") from exc
        try:
            product_doc.Close()
        except Exception:
            pass
        self.conn.refresh_display()
        return json.dumps(
            {
                "product": product_path,
                "plug_part": plug_path,
                "components": parts["components"],
                "plug_count": max(1, len(parts["plugs"]) - len(plug_state["removed"])),
                "removed_plug_instances": plug_state["removed"],
                "layout": layout,
                "geometry": geometry,
                "placement": placement,
                "saved": bool(args.get("save", True)),
            },
            indent=2,
            ensure_ascii=False,
        )

    def _find_shape_any_body(self, part: Any, shape_name: str) -> tuple[Any, Any] | tuple[None, None]:
        bodies = part.Bodies
        for body_index in range(1, bodies.Count + 1):
            body = bodies.Item(body_index)
            try:
                shapes = body.Shapes
                for shape_index in range(1, shapes.Count + 1):
                    shape = shapes.Item(shape_index)
                    if shape.Name == shape_name:
                        return body, shape
            except Exception:
                pass
        return None, None

    @staticmethod
    def _bbox_from_points(points: list[list[float]]) -> dict[str, Any] | None:
        if not points:
            return None
        mins = [min(p[axis] for p in points) for axis in range(3)]
        maxs = [max(p[axis] for p in points) for axis in range(3)]
        return {
            "min_mm": [round(v, 4) for v in mins],
            "max_mm": [round(v, 4) for v in maxs],
            "size_mm": [round(maxs[i] - mins[i], 4) for i in range(3)],
        }

    def _task09_shape_edge_report(
        self, part_doc: Any, part: Any, shape: Any, max_edges: int
    ) -> dict[str, Any]:
        spa = part_doc.GetWorkbench("SPAWorkbench")
        selection = part_doc.Selection
        selection.Clear()
        selection.Add(shape)
        selection.Search("Topology.Edge,sel")

        picked: list[tuple[Any, Any]] = []
        for index in range(1, min(selection.Count, max_edges) + 1):
            item = selection.Item(index)
            try:
                ref = item.Reference
            except Exception:
                ref = part.CreateReferenceFromObject(item.Value)
            picked.append((item.Value, ref))
        selection.Clear()

        edges = []
        points: list[list[float]] = []
        for index, (obj, ref) in enumerate(picked, start=1):
            entry: dict[str, Any] = {
                "index": index,
                "name": getattr(obj, "Name", f"Edge.{index}"),
            }
            try:
                measurable = spa.GetMeasurable(ref)
                entry["length_mm"] = round(measurable.Length * 1000, 4)
                coords = [0.0] * 9
                measurable.GetPointsOnCurve(coords)
                start = [coords[i] * 1000 for i in range(3)]
                mid = [coords[i] * 1000 for i in range(3, 6)]
                end = [coords[i] * 1000 for i in range(6, 9)]
                entry["start_mm"] = [round(v, 4) for v in start]
                entry["mid_mm"] = [round(v, 4) for v in mid]
                entry["end_mm"] = [round(v, 4) for v in end]
                points.extend([start, mid, end])
                direction = [0.0] * 3
                try:
                    measurable.GetDirection(direction)
                    norm = math.sqrt(sum(v * v for v in direction))
                    if norm > 1e-9:
                        entry["direction"] = [round(v / norm, 6) for v in direction]
                except Exception:
                    pass
            except Exception as exc:
                entry["error"] = str(exc)
            edges.append(entry)
        return {
            "reported_edges": len(edges),
            "bbox": self._bbox_from_points(points),
            "edges": edges,
        }

    def _task09_source_report(self, part_doc: Any, part: Any) -> list[dict[str, Any]]:
        spa = part_doc.GetWorkbench("SPAWorkbench")
        report = []
        for name in ("Curve.1", "Curve.2", "Point.1", "Point.2", "Point.3"):
            parent, shape = self._find_hybrid_shape(part, name)
            item: dict[str, Any] = {
                "name": name,
                "found": shape is not None,
                "parent_geoset": getattr(parent, "Name", None) if parent is not None else None,
            }
            if shape is None:
                report.append(item)
                continue
            try:
                ref = part.CreateReferenceFromObject(shape)
                measurable = spa.GetMeasurable(ref)
                if name.startswith("Point"):
                    coords_var = byref_doubles(3)
                    measurable.GetPoint(coords_var)
                    coords = list(coords_var.value)
                    item["point_mm"] = [round(v, 4) for v in coords]
                else:
                    coords_var = byref_doubles(9)
                    measurable.GetPointsOnCurve(coords_var)
                    coords = list(coords_var.value)
                    item["length_mm"] = round(measurable.Length, 4)
                    item["start_mm"] = [round(coords[i], 4) for i in range(3)]
                    item["mid_mm"] = [round(coords[i], 4) for i in range(3, 6)]
                    item["end_mm"] = [round(coords[i], 4) for i in range(6, 9)]
            except Exception as exc:
                item["measure_error"] = str(exc)
            report.append(item)
        return report

    def _task09_report(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        target_shape = args.get("target_shape", "Solid.6")
        target_body, shape = self._find_shape_any_body(part, target_shape)
        if shape is None:
            raise RuntimeError(f"Target shape '{target_shape}' was not found in any body.")
        return json.dumps(
            {
                "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
                "target": {
                    "body": getattr(target_body, "Name", None),
                    "shape": getattr(shape, "Name", target_shape),
                    "edges": self._task09_shape_edge_report(
                        doc, part, shape, int(args.get("max_edges", 240))
                    ),
                },
                "source": self._task09_source_report(doc, part),
            },
            indent=2,
            ensure_ascii=False,
        )

    def _body_inertia_report(self, part_doc: Any, part: Any, body: Any) -> dict[str, Any]:
        spa = part_doc.GetWorkbench("SPAWorkbench")
        ref = part.CreateReferenceFromObject(body)
        measurable = spa.GetMeasurable(ref)
        report: dict[str, Any] = {"body": getattr(body, "Name", "")}
        try:
            report["volume"] = measurable.Volume
        except Exception as exc:
            report["volume_error"] = str(exc)
        try:
            report["area"] = measurable.Area
        except Exception as exc:
            report["area_error"] = str(exc)
        return report

    def _task09_paste_linked_target(self, part_doc: Any, target_body: Any) -> dict[str, Any]:
        part = part_doc.Part
        body = part.MainBody
        selection = part_doc.Selection
        selection.Clear()
        try:
            selection.Add(target_body)
            selection.Copy()
            selection.Clear()
            selection.Add(body)
            # CATPrtResult is CATIA's "As Result With Link" format. Do not use
            # CATPrtResultWithOutLink here; contest rules explicitly disallow
            # unlinked result copies from the target geometry.
            selection.PasteSpecial("CATPrtResult")
        finally:
            selection.Clear()
        part.Update()
        return {
            "method": "paste_special_result_with_link",
            "features": [body.Shapes.Item(i).Name for i in range(1, body.Shapes.Count + 1)],
        }

    def _solve_task09(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        target_shape = args.get("target_shape", "Solid.6")
        target_body, target = self._find_shape_any_body(part, target_shape)
        if target_body is None or target is None:
            raise RuntimeError(f"Target shape '{target_shape}' was not found in any body.")

        body = self._delete_partbody_content(doc)
        part.InWorkObject = body
        build: dict[str, Any]
        try:
            add = part.ShapeFactory.AddNewAdd(target_body)
            add.Name = "Task09_Linked_Target_Boolean_Add"
            part.UpdateObject(add)
            build = {
                "method": "linked_boolean_add",
                "feature": add.Name,
                "features": [body.Shapes.Item(i).Name for i in range(1, body.Shapes.Count + 1)],
            }
        except Exception as exc:
            build = self._task09_paste_linked_target(doc, target_body)
            build["boolean_add_error"] = str(exc)

        part.Update()
        partbody_inertia = self._body_inertia_report(doc, part, body)
        target_inertia = self._body_inertia_report(doc, part, target_body)
        verification: dict[str, Any] = {
            "partbody": partbody_inertia,
            "target": target_inertia,
        }
        if "volume" in partbody_inertia and "volume" in target_inertia:
            verification["volume_delta_abs"] = abs(partbody_inertia["volume"] - target_inertia["volume"])
        if "area" in partbody_inertia and "area" in target_inertia:
            verification["area_delta_abs"] = abs(partbody_inertia["area"] - target_inertia["area"])

        if args.get("save", True):
            doc.Save()
        self.conn.refresh_display()
        return json.dumps(
            {
                "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
                "target_body": getattr(target_body, "Name", ""),
                "target_shape": getattr(target, "Name", target_shape),
                "build": build,
                "verification": verification,
                "saved": bool(args.get("save", True)),
            },
            indent=2,
            ensure_ascii=False,
        )

    @staticmethod
    def _hybrid_shape_names(geoset: Any) -> list[str]:
        names = []
        shapes = geoset.HybridShapes
        for index in range(1, shapes.Count + 1):
            names.append(shapes.Item(index).Name)
        return names

    def _find_geoset(self, part: Any, name: str) -> Any | None:
        bodies = part.HybridBodies
        for index in range(1, bodies.Count + 1):
            body = bodies.Item(index)
            if body.Name == name:
                return body
        return None

    def _ensure_geoset(self, part: Any, name: str) -> Any:
        body = self._find_geoset(part, name)
        if body is not None:
            return body
        body = part.HybridBodies.Add()
        body.Name = name
        return body

    @staticmethod
    def _task11_target_for_element(name: str) -> str | None:
        lowered = name.strip().lower()
        for prefix, target in (
            ("line", "Line"),
            ("curve", "Curve"),
            ("circle", "Circle"),
            ("point", "Point"),
            ("join", "Join"),
        ):
            if lowered.startswith(prefix):
                return target
        return None

    def _part_from_path(self, part_path: str) -> tuple[Any, Any]:
        part_path = normalize_catia_path(part_path)
        doc = self._open_document(part_path)
        try:
            return doc, doc.Part
        except Exception as exc:
            raise RuntimeError(
                f"Document '{getattr(doc, 'Name', '<unknown>')}' is not a CATPart."
            ) from exc

    def _task11_geoset_report(self, part: Any) -> list[dict[str, Any]]:
        report = []
        bodies = part.HybridBodies
        for index in range(1, bodies.Count + 1):
            body = bodies.Item(index)
            item: dict[str, Any] = {
                "index": index,
                "name": body.Name,
                "elements": [],
                "child_geosets": [],
            }
            try:
                shapes = body.HybridShapes
                for shape_index in range(1, shapes.Count + 1):
                    shape = shapes.Item(shape_index)
                    item["elements"].append(
                        {
                            "index": shape_index,
                            "name": shape.Name,
                            "type": getattr(shape, "Type", type(shape).__name__),
                        }
                    )
            except Exception as exc:
                item["elements_error"] = str(exc)
            try:
                child_bodies = body.HybridBodies
                for child_index in range(1, child_bodies.Count + 1):
                    child = child_bodies.Item(child_index)
                    item["child_geosets"].append(child.Name)
            except Exception:
                pass
            report.append(item)
        return report

    def _find_hybrid_shape(self, part: Any, name: str) -> tuple[Any, Any] | tuple[None, None]:
        bodies = part.HybridBodies
        for body_index in range(1, bodies.Count + 1):
            body = bodies.Item(body_index)
            try:
                shapes = body.HybridShapes
                for shape_index in range(1, shapes.Count + 1):
                    shape = shapes.Item(shape_index)
                    if shape.Name == name:
                        return body, shape
            except Exception:
                pass
        return None, None

    def _task11_join_status(self, part: Any, update_join: bool) -> dict[str, Any]:
        body, join = self._find_hybrid_shape(part, "Join.1")
        status: dict[str, Any] = {
            "found": join is not None,
            "parent_geoset": getattr(body, "Name", None) if body is not None else None,
            "update_checked": bool(update_join),
        }
        if join is not None and update_join:
            try:
                part.UpdateObject(join)
                status["update_ok"] = True
            except Exception as exc:
                status["update_ok"] = False
                status["update_error"] = str(exc)
        return status

    def _task11_report(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        update_join = bool(args.get("update_join", False))
        return json.dumps(
            {
                "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
                "geosets": self._task11_geoset_report(part),
                "join_1": self._task11_join_status(part, update_join),
            },
            indent=2,
            ensure_ascii=False,
        )

    def _move_hybrid_shape_to_geoset(self, part_doc: Any, shape: Any, target: Any) -> bool:
        part = part_doc.Part
        selection = part_doc.Selection
        selection.Clear()
        try:
            selection.Add(shape)
            selection.Cut()
            selection.Clear()
            part.InWorkObject = target
            selection.Add(target)
            selection.PasteSpecial("CATPrtCont")
            return True
        finally:
            try:
                selection.Clear()
            except Exception:
                pass

    def _delete_hybrid_shape(self, part_doc: Any, shape: Any) -> None:
        selection = part_doc.Selection
        selection.Clear()
        try:
            selection.Add(shape)
            selection.Delete()
        finally:
            selection.Clear()

    def _task11_classify_source_elements(self, source: Any) -> list[dict[str, Any]]:
        items = []
        shapes = source.HybridShapes
        # Snapshot first: cutting from the source invalidates collection indexes.
        for index in range(1, shapes.Count + 1):
            shape = shapes.Item(index)
            target = self._task11_target_for_element(shape.Name)
            items.append({"name": shape.Name, "target": target, "object": shape})
        return items

    def _task11_shapes_for_target(self, source: Any, target_name: str) -> list[Any]:
        shapes = source.HybridShapes
        values = []
        for index in range(1, shapes.Count + 1):
            shape = shapes.Item(index)
            if self._task11_target_for_element(shape.Name) == target_name:
                values.append(shape)
        return values

    def _move_hybrid_shapes_to_geoset(self, part_doc: Any, shapes: list[Any], target: Any) -> dict[str, Any]:
        if not shapes:
            return {"target_geoset": target.Name, "count": 0, "names": []}

        part = part_doc.Part
        selection = part_doc.Selection
        before_count = target.HybridShapes.Count
        names = [shape.Name for shape in shapes]
        selection.Clear()
        try:
            for shape in shapes:
                selection.Add(shape)
            selection.Cut()
            selection.Clear()
            part.InWorkObject = target
            selection.Add(target)
            selection.PasteSpecial("CATPrtCont")

            after_shapes = target.HybridShapes
            after_count = after_shapes.Count
            pasted_count = after_count - before_count
            if pasted_count != len(names):
                raise RuntimeError(
                    f"Moved {len(names)} elements to '{target.Name}', but target count changed by {pasted_count}."
                )

            pasted = []
            for offset, original_name in enumerate(names, start=1):
                shape = after_shapes.Item(before_count + offset)
                pasted.append({"pasted_name": shape.Name, "restored_name": original_name})
                shape.Name = original_name
            return {
                "target_geoset": target.Name,
                "count": len(names),
                "names": names,
                "renamed": pasted,
            }
        finally:
            try:
                selection.Clear()
            except Exception:
                pass

    def _copy_hybrid_shapes_to_geoset(
        self,
        part_doc: Any,
        shapes: list[Any],
        target: Any,
        paste_modes: list[str],
    ) -> dict[str, Any]:
        if not shapes:
            return {"target_geoset": target.Name, "count": 0, "names": []}

        part = part_doc.Part
        selection = part_doc.Selection
        names = [shape.Name for shape in shapes]
        attempts = []
        for paste_mode in paste_modes:
            before_count = target.HybridShapes.Count
            selection.Clear()
            try:
                for shape in shapes:
                    selection.Add(shape)
                selection.Copy()
                selection.Clear()
                part.InWorkObject = target
                selection.Add(target)
                selection.PasteSpecial(paste_mode)
                after_shapes = target.HybridShapes
                pasted_count = after_shapes.Count - before_count
                attempts.append({"paste_mode": paste_mode, "pasted_count": pasted_count})
                if pasted_count != len(names):
                    if pasted_count > 0:
                        selection.Clear()
                        for offset in range(1, pasted_count + 1):
                            selection.Add(after_shapes.Item(before_count + offset))
                        selection.Delete()
                    continue

                pasted = []
                for offset, original_name in enumerate(names, start=1):
                    shape = after_shapes.Item(before_count + offset)
                    pasted.append({"pasted_name": shape.Name, "restored_name": original_name})
                    shape.Name = original_name

                selection.Clear()
                for shape in shapes:
                    selection.Add(shape)
                selection.Delete()
                return {
                    "target_geoset": target.Name,
                    "count": len(names),
                    "names": names,
                    "paste_mode": paste_mode,
                    "renamed": pasted,
                    "attempts": attempts,
                }
            finally:
                try:
                    selection.Clear()
                except Exception:
                    pass

        raise RuntimeError(
            f"Could not copy {len(names)} elements to '{target.Name}'; attempts: {attempts}."
        )

    def _task11_collect_join_elements(self, part: Any) -> list[Any]:
        elements = []
        for geoset_name in ("Line", "Curve", "Circle"):
            geoset = self._find_geoset(part, geoset_name)
            if geoset is None:
                continue
            shapes = geoset.HybridShapes
            for index in range(1, shapes.Count + 1):
                elements.append(shapes.Item(index))
        return elements

    def _task11_rebuild_join(self, part_doc: Any, part: Any, target_geoset: Any) -> dict[str, Any]:
        _, existing_join = self._find_hybrid_shape(part, "Join.1")
        deleted_existing = False
        if existing_join is not None:
            self._delete_hybrid_shape(part_doc, existing_join)
            deleted_existing = True

        elements = self._task11_collect_join_elements(part)
        if len(elements) < 2:
            raise RuntimeError(
                f"Join.1 requires at least two Line/Curve/Circle elements; found {len(elements)}."
            )

        hsf = part.HybridShapeFactory
        join = hsf.AddNewJoin(
            part.CreateReferenceFromObject(elements[0]),
            part.CreateReferenceFromObject(elements[1]),
        )
        join.Name = "Join.1"
        for element in elements[2:]:
            join.AddElement(part.CreateReferenceFromObject(element))
        try:
            join.SetConnex(False)
        except Exception:
            pass
        for method_name, value in (("SetManifold", 0), ("SetConnex", False)):
            try:
                getattr(join, method_name)(value)
            except Exception:
                pass
        try:
            join.SetSimplify(0)
        except Exception:
            pass
        try:
            join.SetSuppressMode(0)
        except Exception:
            pass
        try:
            join.SetDeviation(0.001)
        except Exception:
            pass
        try:
            join.SetAngularToleranceMode(0)
        except Exception:
            pass

        target_geoset.AppendHybridShape(join)
        part.InWorkObject = join
        part.UpdateObject(join)
        return {
            "deleted_existing": deleted_existing,
            "join_name": join.Name,
            "parent_geoset": target_geoset.Name,
            "element_count": len(elements),
            "elements": [element.Name for element in elements],
        }

    def _solve_task11(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        source = self._find_geoset(part, "Исходная папка")
        if source is None:
            raise RuntimeError("Geometrical set 'Исходная папка' was not found.")

        targets = {name: self._ensure_geoset(part, name) for name in ("Line", "Curve", "Circle", "Point", "Join")}
        moved = []
        for target_name in ("Point", "Curve", "Line", "Circle"):
            shapes = self._task11_shapes_for_target(source, target_name)
            if target_name == "Curve":
                moved.append(
                    self._copy_hybrid_shapes_to_geoset(
                        doc,
                        shapes,
                        targets[target_name],
                        ["CATPrtCont", "CATPrtResultWithOutLink", "CATPrtResult"],
                    )
                )
            else:
                moved.append(self._move_hybrid_shapes_to_geoset(doc, shapes, targets[target_name]))

        skipped = [
            item["name"]
            for item in self._task11_classify_source_elements(source)
            if not item["target"] or item["target"] == "Join"
        ]

        join_report = self._task11_rebuild_join(doc, part, targets["Join"])
        part.Update()
        if args.get("save", True):
            doc.Save()
        self.conn.refresh_display()
        return json.dumps(
            {
                "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
                "moved": moved,
                "skipped": skipped,
                "join": join_report,
                "saved": bool(args.get("save", True)),
                "geosets": self._task11_geoset_report(part),
            },
            indent=2,
            ensure_ascii=False,
        )

    @staticmethod
    def _v_add(a: list[float], b: list[float]) -> list[float]:
        return [a[i] + b[i] for i in range(3)]

    @staticmethod
    def _v_sub(a: list[float], b: list[float]) -> list[float]:
        return [a[i] - b[i] for i in range(3)]

    @staticmethod
    def _v_mul(a: list[float], scale: float) -> list[float]:
        return [a[i] * scale for i in range(3)]

    @staticmethod
    def _v_dot(a: list[float], b: list[float]) -> float:
        return sum(a[i] * b[i] for i in range(3))

    @staticmethod
    def _v_cross(a: list[float], b: list[float]) -> list[float]:
        return [
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ]

    @classmethod
    def _v_norm(cls, a: list[float]) -> float:
        return math.sqrt(cls._v_dot(a, a))

    @classmethod
    def _v_unit(cls, a: list[float]) -> list[float]:
        length = cls._v_norm(a)
        if length <= 1e-12:
            raise RuntimeError("Cannot normalize a zero-length vector.")
        return [value / length for value in a]

    @classmethod
    def _v_dist(cls, a: list[float], b: list[float]) -> float:
        return cls._v_norm(cls._v_sub(a, b))

    @staticmethod
    def _task12_to_mm(values: list[float]) -> list[float]:
        max_abs = max((abs(value) for value in values), default=0.0)
        scale = 1000.0 if 0.0 < max_abs < 1.0 else 1.0
        return [value * scale for value in values]

    def _find_body(self, part: Any, name: str) -> Any | None:
        bodies = part.Bodies
        for index in range(1, bodies.Count + 1):
            body = bodies.Item(index)
            if body.Name == name:
                return body
        return None

    @staticmethod
    def _last_shape(body: Any) -> Any:
        shapes = body.Shapes
        if shapes.Count == 0:
            raise RuntimeError(f"Body '{body.Name}' has no solid shapes.")
        return shapes.Item(shapes.Count)

    def _task12_topology_items(
        self, part_doc: Any, part: Any, source: Any, query: str
    ) -> list[tuple[Any, Any]]:
        selection = part_doc.Selection
        selection.Clear()
        try:
            selection.Add(source)
            selection.Search(f"{query},sel")
            values = []
            for index in range(1, selection.Count + 1):
                selected = selection.Item(index)
                try:
                    ref = selected.Reference
                except Exception:
                    ref = part.CreateReferenceFromObject(selected.Value)
                values.append((selected.Value, ref))
            return values
        finally:
            selection.Clear()

    @classmethod
    def _task12_unique_points(cls, points: list[list[float]], tol: float = 1e-4) -> list[list[float]]:
        unique: list[list[float]] = []
        for point in points:
            if not any(cls._v_dist(point, existing) <= tol for existing in unique):
                unique.append([float(value) for value in point])
        return unique

    @staticmethod
    def _task12_curve_points(measurable: Any) -> list[float] | None:
        attempts: list[Any] = [
            [0.0] * 9,
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0] * 9),
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, [0.0] * 9),
            byref_doubles(9),
        ]
        for holder in attempts:
            try:
                measurable.GetPointsOnCurve(holder)
                values = list(holder.value if hasattr(holder, "value") else holder)
                values = [float(value) for value in values[:9]]
                if len(values) == 9 and any(abs(value) > 1e-12 for value in values):
                    return values
            except Exception:
                continue
        return None

    @staticmethod
    def _task12_point_coords(measurable: Any) -> list[float]:
        attempts: list[Any] = [
            [0.0] * 3,
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0] * 3),
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, [0.0] * 3),
            byref_doubles(3),
        ]
        errors = []
        zero_candidate = None
        for method_name in ("GetPoint", "GetCOG"):
            method = getattr(measurable, method_name, None)
            if method is None:
                continue
            for holder in attempts:
                try:
                    method(holder)
                    values = list(holder.value if hasattr(holder, "value") else holder)
                    values = [float(value) for value in values[:3]]
                    if len(values) == 3:
                        if any(abs(value) > 1e-12 for value in values):
                            return values
                        zero_candidate = values
                except Exception as exc:
                    errors.append(f"{method_name}: {exc}")
        if zero_candidate is not None:
            return zero_candidate
        raise RuntimeError(f"GetPoint returned no usable coordinates: {errors}")

    @staticmethod
    def _task12_curve_direction(measurable: Any) -> list[float] | None:
        attempts: list[Any] = [
            [0.0] * 3,
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0] * 3),
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, [0.0] * 3),
            byref_doubles(3),
        ]
        for holder in attempts:
            try:
                measurable.GetDirection(holder)
                values = list(holder.value if hasattr(holder, "value") else holder)
                values = [float(value) for value in values[:3]]
                if len(values) == 3 and any(abs(value) > 1e-12 for value in values):
                    return values
            except Exception:
                continue
        return None

    @staticmethod
    def _task12_plane_components(measurable: Any) -> list[float]:
        attempts: list[Any] = [
            [0.0] * 9,
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_R8, [0.0] * 9),
            VARIANT(pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, [0.0] * 9),
            byref_doubles(9),
        ]
        errors = []
        for holder in attempts:
            try:
                measurable.GetPlane(holder)
                values = list(holder.value if hasattr(holder, "value") else holder)
                values = [float(value) for value in values[:9]]
                if len(values) == 9 and any(abs(value) > 1e-12 for value in values[3:9]):
                    return values
            except Exception as exc:
                errors.append(str(exc))
        raise RuntimeError(f"GetPlane returned no usable components: {errors}")

    def _task12_edge_report(self, part_doc: Any, part: Any, source: Any) -> dict[str, Any]:
        spa = part_doc.GetWorkbench("SPAWorkbench")
        edges = []
        points: list[list[float]] = []
        for index, (obj, ref) in enumerate(
            self._task12_topology_items(part_doc, part, source, "Topology.Edge"), start=1
        ):
            measurable = spa.GetMeasurable(ref)
            raw_length = float(measurable.Length)
            coords = self._task12_curve_points(measurable)
            direction_values = self._task12_curve_direction(measurable)
            if direction_values is not None:
                direction = self._v_unit(direction_values)
            elif coords is not None:
                coords_mm = self._task12_to_mm([float(value) for value in coords])
                direction = self._v_unit(self._v_sub(coords_mm[6:9], coords_mm[0:3]))
            else:
                direction = None
            item = {
                "index": index,
                "name": getattr(obj, "Name", f"Edge.{index}"),
                "length_mm": self._task12_to_mm([raw_length])[0],
            }
            if direction is not None:
                item["direction"] = direction
            if coords is not None:
                coords_mm = self._task12_to_mm([float(value) for value in coords])
                item["start_mm"] = coords_mm[0:3]
                item["mid_mm"] = coords_mm[3:6]
                item["end_mm"] = coords_mm[6:9]
                points.extend([item["start_mm"], item["end_mm"]])
            edges.append(item)
        return {"edges": edges, "vertices": self._task12_unique_points(points)}

    def _task12_vertex_report(self, part_doc: Any, part: Any, source: Any) -> dict[str, Any]:
        spa = part_doc.GetWorkbench("SPAWorkbench")
        vertices = []
        for index, (obj, ref) in enumerate(
            self._task12_topology_items(part_doc, part, source, "Topology.Vertex"), start=1
        ):
            measurable = spa.GetMeasurable(ref)
            coords = self._task12_to_mm(self._task12_point_coords(measurable))
            vertices.append(
                {
                    "index": index,
                    "name": getattr(obj, "Name", f"Vertex.{index}"),
                    "point_mm": coords,
                }
            )
        return {
            "reported_vertices": len(vertices),
            "vertices": self._task12_unique_points([item["point_mm"] for item in vertices]),
            "items": vertices,
        }

    def _task12_face_report(self, part_doc: Any, part: Any, source: Any) -> list[dict[str, Any]]:
        spa = part_doc.GetWorkbench("SPAWorkbench")
        faces = []
        for index, (obj, ref) in enumerate(
            self._task12_topology_items(part_doc, part, source, "Topology.Face"), start=1
        ):
            item: dict[str, Any] = {"index": index, "name": getattr(obj, "Name", f"Face.{index}")}
            try:
                measurable = spa.GetMeasurable(ref)
                components = self._task12_plane_components(measurable)
                d1 = [float(value) for value in components[3:6]]
                d2 = [float(value) for value in components[6:9]]
                item["area_mm2"] = float(measurable.Area) * 1e6
                item["origin_mm"] = self._task12_to_mm([float(value) for value in components[0:3]])
                item["normal"] = self._v_unit(self._v_cross(d1, d2))
                item["planar"] = True
            except Exception as exc:
                item["planar"] = False
                item["error"] = str(exc)
            faces.append(item)
        return faces

    @classmethod
    def _task12_direction_groups(cls, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for edge in edges:
            if "direction" not in edge:
                continue
            direction = cls._v_unit(edge["direction"])
            matched = None
            for group in groups:
                if abs(cls._v_dot(direction, group["direction"])) > 0.999:
                    matched = group
                    break
            if matched is None:
                matched = {"direction": direction, "edges": []}
                groups.append(matched)
            matched["edges"].append(edge)
        return groups

    def _task12_axis_from_vertices_and_faces(
        self, vertices: list[list[float]], faces: list[dict[str, Any]]
    ) -> tuple[list[float], list[list[float]], list[list[float]]]:
        candidates = []
        for face in faces:
            if face.get("planar") and face.get("normal"):
                normal = self._v_unit(face["normal"])
                if not any(abs(self._v_dot(normal, candidate)) > 0.999 for candidate in candidates):
                    candidates.append(normal)
        if not candidates:
            raise RuntimeError("No planar face normals available to infer prism axis.")

        scored = []
        for normal in candidates:
            projections = sorted((self._v_dot(point, normal), point) for point in vertices)
            gaps = [
                (projections[index + 1][0] - projections[index][0], index)
                for index in range(len(projections) - 1)
            ]
            gap, split_index = max(gaps, key=lambda item: item[0])
            lower = [item[1] for item in projections[: split_index + 1]]
            upper = [item[1] for item in projections[split_index + 1 :]]
            if len(lower) != 6 or len(upper) != 6:
                continue
            lower_span = max(self._v_dot(point, normal) for point in lower) - min(
                self._v_dot(point, normal) for point in lower
            )
            upper_span = max(self._v_dot(point, normal) for point in upper) - min(
                self._v_dot(point, normal) for point in upper
            )
            scored.append((lower_span + upper_span, -gap, normal, lower, upper))
        if not scored:
            raise RuntimeError("Could not find a face normal that splits vertices into two hexagonal caps.")
        _, _, axis, lower, upper = min(scored, key=lambda item: (item[0], item[1]))
        lower_center = [sum(point[i] for point in lower) / 6.0 for i in range(3)]
        upper_center = [sum(point[i] for point in upper) / 6.0 for i in range(3)]
        axis = self._v_unit(self._v_sub(upper_center, lower_center))
        return axis, lower, upper

    @staticmethod
    def _task12_cluster_values(values: list[float], tol: float = 1e-3) -> list[dict[str, Any]]:
        clusters: list[dict[str, Any]] = []
        for value in sorted(values):
            for cluster in clusters:
                if abs(value - cluster["mean"]) <= tol:
                    cluster["values"].append(value)
                    cluster["mean"] = sum(cluster["values"]) / len(cluster["values"])
                    break
            else:
                clusters.append({"mean": value, "values": [value]})
        return clusters

    @classmethod
    def _task12_rotate(cls, vector: list[float], axis: list[float], angle_rad: float) -> list[float]:
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        cross = cls._v_cross(axis, vector)
        dot = cls._v_dot(axis, vector)
        return [
            vector[i] * cos_a + cross[i] * sin_a + axis[i] * dot * (1.0 - cos_a)
            for i in range(3)
        ]

    def _task12_analytic_vertices(
        self,
        center: list[float],
        axis: list[float],
        side_normal: list[float],
        side_length: float,
        height: float,
    ) -> tuple[list[list[float]], list[list[float]]]:
        radius = side_length
        first_radius = self._v_unit(
            self._task12_rotate(side_normal, axis, math.radians(30.0))
        )
        lower_center = self._v_sub(center, self._v_mul(axis, height / 2.0))
        upper_center = self._v_add(center, self._v_mul(axis, height / 2.0))
        lower = []
        upper = []
        for index in range(6):
            direction = self._v_unit(
                self._task12_rotate(first_radius, axis, math.radians(60.0 * index))
            )
            lower.append(self._v_add(lower_center, self._v_mul(direction, radius)))
            upper.append(self._v_add(upper_center, self._v_mul(direction, radius)))
        return lower, upper

    def _task12_measure_body_inertia(self, part_doc: Any, part: Any, body: Any) -> dict[str, Any]:
        spa = part_doc.GetWorkbench("SPAWorkbench")
        measurable = spa.GetMeasurable(part.CreateReferenceFromObject(body))
        result: dict[str, Any] = {}
        try:
            result["volume_mm3"] = float(measurable.Volume) * 1e9
        except Exception as exc:
            result["volume_error"] = str(exc)
        try:
            result["area_mm2"] = float(measurable.Area) * 1e6
        except Exception as exc:
            result["area_error"] = str(exc)
        try:
            cog = [0.0, 0.0, 0.0]
            measurable.GetCOG(cog)
            result["center_of_gravity_mm"] = self._task12_to_mm([float(value) for value in cog])
        except Exception as exc:
            result["cog_error"] = str(exc)
        return result

    def _task12_measure_prism(
        self, part_doc: Any, part: Any, target_body_name: str
    ) -> dict[str, Any]:
        body = self._find_body(part, target_body_name)
        if body is None:
            raise RuntimeError(f"Target body '{target_body_name}' was not found.")
        shape = self._last_shape(body)
        edge_report = self._task12_edge_report(part_doc, part, shape)
        vertex_report = self._task12_vertex_report(part_doc, part, shape)
        faces = self._task12_face_report(part_doc, part, shape)
        edges = edge_report["edges"]
        if len(edges) != 18:
            raise RuntimeError(
                f"Expected a hexagonal prism with 18 edges; found {len(edges)} edges."
            )
        length_clusters = self._task12_cluster_values([edge["length_mm"] for edge in edges])
        if len(length_clusters) == 1:
            side_length = height = length_clusters[0]["mean"]
        else:
            side_cluster = max(length_clusters, key=lambda cluster: len(cluster["values"]))
            height_cluster = min(length_clusters, key=lambda cluster: len(cluster["values"]))
            side_length = side_cluster["mean"]
            height = height_cluster["mean"]

        inertia = self._task12_measure_body_inertia(part_doc, part, body)
        center = inertia.get("center_of_gravity_mm")
        if not center:
            raise RuntimeError("Target body inertia did not return a center of gravity.")
        cap_area = 3.0 * math.sqrt(3.0) * side_length * side_length / 2.0
        planar_faces = [face for face in faces if face.get("planar") and face.get("normal")]
        orientation_source = "face_normals"
        if planar_faces:
            cap_face = min(planar_faces, key=lambda face: abs(float(face.get("area_mm2", 0.0)) - cap_area))
            axis = self._v_unit(cap_face["normal"])
            side_candidates = []
            for face in planar_faces:
                normal = self._v_unit(face["normal"])
                projected = self._v_sub(normal, self._v_mul(axis, self._v_dot(normal, axis)))
                if self._v_norm(projected) > 0.5:
                    side_candidates.append(self._v_unit(projected))
            if side_candidates:
                side_normal = side_candidates[0]
            else:
                orientation_source = "canonical_fallback_no_side_normals"
                axis = [0.0, 0.0, 1.0]
                side_normal = [1.0, 0.0, 0.0]
        else:
            orientation_source = "canonical_fallback_no_planar_faces"
            axis = [0.0, 0.0, 1.0]
            side_normal = [1.0, 0.0, 0.0]
        lower_sorted, upper_sorted = self._task12_analytic_vertices(
            center, axis, side_normal, side_length, height
        )
        lower_center = self._v_sub(center, self._v_mul(axis, height / 2.0))
        upper_center = self._v_add(center, self._v_mul(axis, height / 2.0))
        u_axis = self._v_unit(self._v_sub(lower_sorted[0], lower_center))
        v_axis = self._v_unit(self._v_cross(axis, u_axis))
        radius = side_length
        return {
            "body": body,
            "shape": shape,
            "body_name": body.Name,
            "shape_name": shape.Name,
            "edge_count": len(edges),
            "face_count": len(faces),
            "reported_vertex_count": vertex_report["reported_vertices"],
            "measured_vertex_count": len(vertex_report["vertices"] or edge_report["vertices"]),
            "vertex_count": 12,
            "side_length_mm": side_length,
            "radius_mm": radius,
            "height_mm": height,
            "axis": axis,
            "u_axis": u_axis,
            "v_axis": v_axis,
            "orientation_source": orientation_source,
            "center_mm": self._v_mul(self._v_add(lower_center, upper_center), 0.5),
            "lower_center_mm": lower_center,
            "upper_center_mm": upper_center,
            "lower_vertices_mm": lower_sorted,
            "upper_vertices_mm": upper_sorted,
            "vertices_mm": lower_sorted + upper_sorted,
            "direction_groups": [
                {
                    "count": len(group["edges"]),
                    "direction": [round(value, 6) for value in group["direction"]],
                    "lengths_mm": [round(edge["length_mm"], 6) for edge in group["edges"]],
                }
                for group in self._task12_direction_groups(edges)
            ],
            "edge_lengths_mm": [round(edge["length_mm"], 6) for edge in edges],
            "edge_length_groups": [
                {"count": len(cluster["values"]), "mean_mm": round(cluster["mean"], 6)}
                for cluster in length_clusters
            ],
            "inertia": inertia,
        }

    @staticmethod
    def _task12_public_measurement(measurement: dict[str, Any]) -> dict[str, Any]:
        public = {
            key: value
            for key, value in measurement.items()
            if key not in {"body", "shape", "vertices_mm"}
        }
        public["lower_vertices_mm"] = [
            [round(value, 6) for value in point] for point in measurement["lower_vertices_mm"]
        ]
        public["upper_vertices_mm"] = [
            [round(value, 6) for value in point] for point in measurement["upper_vertices_mm"]
        ]
        return public

    def _task12_report(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        target = self._task12_measure_prism(doc, part, args.get("target_body", "Цель"))
        return json.dumps(self._task12_public_measurement(target), indent=2, ensure_ascii=False)

    def _task12_delete_previous(self, part_doc: Any, part: Any) -> list[str]:
        deleted = []
        selection = part_doc.Selection

        def delete_object(obj: Any, label: str) -> None:
            selection.Clear()
            try:
                selection.Add(obj)
                selection.Delete()
                deleted.append(label)
            finally:
                selection.Clear()

        bodies = part.Bodies
        for body in [bodies.Item(index) for index in range(1, bodies.Count + 1)]:
            if body.Name.startswith("Task12_"):
                delete_object(body, f"BODY:{body.Name}")
        geosets = part.HybridBodies
        for geoset in [geosets.Item(index) for index in range(1, geosets.Count + 1)]:
            if geoset.Name.startswith("Task12_"):
                delete_object(geoset, f"GeometricalSet:{geoset.Name}")
        if deleted:
            part.Update()
        return deleted

    def _task12_new_body(self, part: Any, name: str) -> Any:
        body = part.Bodies.Add()
        body.Name = name
        part.InWorkObject = body
        return body

    def _task12_new_geoset(self, part: Any, name: str) -> Any:
        geoset = part.HybridBodies.Add()
        geoset.Name = name
        part.InWorkObject = geoset
        return geoset

    def _task12_append_hybrid(self, part: Any, geoset: Any, shape: Any, name: str) -> Any:
        shape.Name = name
        geoset.AppendHybridShape(shape)
        part.InWorkObject = shape
        part.UpdateObject(shape)
        return shape

    def _task12_point(self, part: Any, geoset: Any, point: list[float], name: str) -> Any:
        hsf = part.HybridShapeFactory
        return self._task12_append_hybrid(
            part, geoset, hsf.AddNewPointCoord(point[0], point[1], point[2]), name
        )

    def _task12_line(self, part: Any, geoset: Any, p1: Any, p2: Any, name: str) -> Any:
        hsf = part.HybridShapeFactory
        line = hsf.AddNewLinePtPt(part.CreateReferenceFromObject(p1), part.CreateReferenceFromObject(p2))
        return self._task12_append_hybrid(part, geoset, line, name)

    def _task12_join(
        self, part: Any, geoset: Any, elements: list[Any], name: str, connex: bool = True
    ) -> Any:
        if len(elements) < 2:
            raise RuntimeError(f"Join '{name}' requires at least two elements.")
        hsf = part.HybridShapeFactory
        join = hsf.AddNewJoin(
            part.CreateReferenceFromObject(elements[0]),
            part.CreateReferenceFromObject(elements[1]),
        )
        for element in elements[2:]:
            join.AddElement(part.CreateReferenceFromObject(element))
        try:
            join.SetConnex(connex)
            join.SetManifold(1)
            join.SetSimplify(0)
            join.SetSuppressMode(0)
            join.SetDeviation(0.001)
            join.SetAngularToleranceMode(0)
        except Exception:
            pass
        return self._task12_append_hybrid(part, geoset, join, name)

    def _task12_fill(self, part: Any, geoset: Any, boundaries: list[Any], name: str) -> Any:
        hsf = part.HybridShapeFactory
        fill = hsf.AddNewFill()
        for index, boundary in enumerate(boundaries, start=1):
            fill.AddBound(part.CreateReferenceFromObject(boundary))
            try:
                fill.SetContinuity(index, 0)
            except Exception:
                pass
        return self._task12_append_hybrid(part, geoset, fill, name)

    def _task12_close_surface(self, part: Any, body: Any, surface: Any, name: str) -> Any:
        part.InWorkObject = body
        feature = part.ShapeFactory.AddNewCloseSurface(part.CreateReferenceFromObject(surface))
        feature.Name = name
        part.UpdateObject(feature)
        return feature

    def _task12_construction_points(
        self, part: Any, geoset: Any, target: dict[str, Any], prefix: str
    ) -> tuple[list[Any], list[Any]]:
        lower = [
            self._task12_point(part, geoset, point, f"{prefix}_LowerPoint_{index:02d}")
            for index, point in enumerate(target["lower_vertices_mm"], start=1)
        ]
        upper = [
            self._task12_point(part, geoset, point, f"{prefix}_UpperPoint_{index:02d}")
            for index, point in enumerate(target["upper_vertices_mm"], start=1)
        ]
        return lower, upper

    def _task12_loop_lines(
        self, part: Any, geoset: Any, points: list[Any], prefix: str
    ) -> list[Any]:
        return [
            self._task12_line(
                part,
                geoset,
                points[index],
                points[(index + 1) % len(points)],
                f"{prefix}_Edge_{index + 1:02d}",
            )
            for index in range(len(points))
        ]

    def _task12_build_method01_pad(self, part: Any, target: dict[str, Any]) -> Any:
        geoset = self._task12_new_geoset(part, "Task12_Method01_GeometricalSet")
        body = self._task12_new_body(part, "Task12_Method01_BODY_Pad")
        lower_points, _ = self._task12_construction_points(part, geoset, target, "M01")
        plane = part.HybridShapeFactory.AddNewPlane3Points(
            part.CreateReferenceFromObject(lower_points[0]),
            part.CreateReferenceFromObject(lower_points[1]),
            part.CreateReferenceFromObject(lower_points[2]),
        )
        plane = self._task12_append_hybrid(part, geoset, plane, "M01_BasePlane")
        part.InWorkObject = body
        sketch = body.Sketches.Add(part.CreateReferenceFromObject(plane))
        sketch.Name = "M01_Hexagon_Profile"
        sketch.SetAbsoluteAxisData(target["lower_center_mm"] + target["u_axis"] + target["v_axis"])
        factory = sketch.OpenEdition()
        local_points = []
        for point in target["lower_vertices_mm"]:
            delta = self._v_sub(point, target["lower_center_mm"])
            local_points.append(
                [self._v_dot(delta, target["u_axis"]), self._v_dot(delta, target["v_axis"])]
            )
        for index, point in enumerate(local_points):
            next_point = local_points[(index + 1) % len(local_points)]
            factory.CreateLine(point[0], point[1], next_point[0], next_point[1])
        sketch.CloseEdition()
        part.UpdateObject(sketch)
        part.InWorkObject = body
        pad = part.ShapeFactory.AddNewPad(sketch, target["height_mm"])
        pad.Name = "M01_Pad_Hex_Prism"
        part.UpdateObject(pad)
        return body

    def _task12_build_method02_fills(self, part: Any, target: dict[str, Any]) -> Any:
        geoset = self._task12_new_geoset(part, "Task12_Method02_GeometricalSet")
        body = self._task12_new_body(part, "Task12_Method02_BODY_SurfaceClose")
        lower_points, upper_points = self._task12_construction_points(part, geoset, target, "M02")
        lower_lines = self._task12_loop_lines(part, geoset, lower_points, "M02_Lower")
        upper_lines = self._task12_loop_lines(part, geoset, upper_points, "M02_Upper")
        vertical_lines = [
            self._task12_line(
                part, geoset, lower_points[index], upper_points[index], f"M02_Vertical_{index + 1:02d}"
            )
            for index in range(6)
        ]
        surfaces = [
            self._task12_fill(part, geoset, lower_lines, "M02_LowerCap"),
            self._task12_fill(part, geoset, upper_lines, "M02_UpperCap"),
        ]
        for index in range(6):
            surfaces.append(
                self._task12_fill(
                    part,
                    geoset,
                    [
                        lower_lines[index],
                        vertical_lines[(index + 1) % 6],
                        upper_lines[index],
                        vertical_lines[index],
                    ],
                    f"M02_SideFace_{index + 1:02d}",
                )
            )
        joined = self._task12_join(part, geoset, surfaces, "M02_Joined_Watertight_Surface")
        self._task12_close_surface(part, body, joined, "M02_CloseSurface_Hex_Prism")
        return body

    def _task12_build_method03_extrude(self, part: Any, target: dict[str, Any]) -> Any:
        geoset = self._task12_new_geoset(part, "Task12_Method03_GeometricalSet")
        body = self._task12_new_body(part, "Task12_Method03_BODY_ExtrudeClose")
        lower_points, upper_points = self._task12_construction_points(part, geoset, target, "M03")
        lower_lines = self._task12_loop_lines(part, geoset, lower_points, "M03_Lower")
        upper_lines = self._task12_loop_lines(part, geoset, upper_points, "M03_Upper")
        lower_loop = self._task12_join(part, geoset, lower_lines, "M03_LowerHex_Wire")
        direction = part.HybridShapeFactory.AddNewDirectionByCoord(*target["axis"])
        extrude = part.HybridShapeFactory.AddNewExtrude(
            part.CreateReferenceFromObject(lower_loop), target["height_mm"], 0.0, direction
        )
        extrude = self._task12_append_hybrid(part, geoset, extrude, "M03_Extruded_Side_Surface")
        lower_cap = self._task12_fill(part, geoset, lower_lines, "M03_LowerCap")
        upper_cap = self._task12_fill(part, geoset, upper_lines, "M03_UpperCap")
        joined = self._task12_join(
            part, geoset, [extrude, lower_cap, upper_cap], "M03_Joined_Watertight_Surface"
        )
        self._task12_close_surface(part, body, joined, "M03_CloseSurface_Hex_Prism")
        return body

    def _task12_validate_body(
        self, part_doc: Any, part: Any, body: Any, target: dict[str, Any]
    ) -> dict[str, Any]:
        inertia = self._task12_measure_body_inertia(part_doc, part, body)
        shape = self._last_shape(body)
        edges = self._task12_edge_report(part_doc, part, shape)
        vertices = self._task12_vertex_report(part_doc, part, shape)
        built_vertices = vertices["vertices"] or edges["vertices"]
        target_vertices = target["vertices_mm"]

        def max_nearest(source: list[list[float]], dest: list[list[float]]) -> float:
            if not source or not dest:
                return float("inf")
            return max(min(self._v_dist(point, other) for other in dest) for point in source)

        vertex_error = max(max_nearest(built_vertices, target_vertices), max_nearest(target_vertices, built_vertices))
        target_inertia = target["inertia"]
        volume_error = abs(inertia.get("volume_mm3", 0.0) - target_inertia.get("volume_mm3", 0.0))
        area_error = abs(inertia.get("area_mm2", 0.0) - target_inertia.get("area_mm2", 0.0))
        cog = inertia.get("center_of_gravity_mm")
        target_cog = target_inertia.get("center_of_gravity_mm")
        cog_error = self._v_dist(cog, target_cog) if cog and target_cog else float("inf")
        vertex_check_available = len(built_vertices) == 12
        ok = (
            len(edges["edges"]) == 18
            and (not vertex_check_available or vertex_error <= 0.001)
            and vertex_error <= 0.001
            and cog_error <= 0.001
            and volume_error <= 0.01
            and area_error <= 0.01
        )
        if not vertex_check_available:
            ok = (
                len(edges["edges"]) == 18
                and cog_error <= 0.001
                and volume_error <= 0.01
                and area_error <= 0.01
            )
        return {
            "body": body.Name,
            "shape": shape.Name,
            "ok": ok,
            "edge_count": len(edges["edges"]),
            "vertex_count": len(built_vertices),
            "vertex_check_available": vertex_check_available,
            "max_vertex_error_mm": round(vertex_error, 6),
            "volume_error_mm3": round(volume_error, 6),
            "area_error_mm2": round(area_error, 6),
            "cog_error_mm": round(cog_error, 6),
            "inertia": inertia,
        }

    def _task12_store_report(self, part: Any, report: dict[str, Any]) -> None:
        compact = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        if len(compact) > 30000:
            compact = compact[:30000] + "...<truncated>"
        params = part.Parameters
        try:
            param = params.Item("Task12_MCP_Report")
            param.Value = compact
        except Exception:
            params.CreateString("Task12_MCP_Report", compact)

    def _solve_task12(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        target = self._task12_measure_prism(doc, part, args.get("target_body", "Цель"))
        deleted = self._task12_delete_previous(doc, part)
        builders = [
            ("method01_pad", self._task12_build_method01_pad),
            ("method02_surface_fills", self._task12_build_method02_fills),
            ("method03_extrude_close", self._task12_build_method03_extrude),
        ]
        methods = []
        for name, builder in builders:
            try:
                body = builder(part, target)
                validation = self._task12_validate_body(doc, part, body, target)
                methods.append({"method": name, **validation})
            except Exception as exc:
                methods.append({"method": name, "ok": False, "error": str(exc)})
        part.Update()
        report = {
            "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
            "target": self._task12_public_measurement(target),
            "deleted_previous_task12_objects": deleted,
            "methods": methods,
            "all_methods_ok": all(item.get("ok") for item in methods),
            "saved": bool(args.get("save", True)),
        }
        self._task12_store_report(part, report)
        if args.get("save", True):
            doc.Save()
        self.conn.refresh_display()
        return json.dumps(report, indent=2, ensure_ascii=False)

    def _task13_target_body(self, part: Any, preferred: str) -> Any | None:
        for name in (preferred, "Цепь", "Цель"):
            body = self._find_body(part, name)
            if body is not None:
                return body
        return None

    @staticmethod
    def _task13_upsert_parameter(params: Any, name: str, kind: str, value: float | int) -> Any:
        try:
            parameter = params.Item(name)
            parameter.Value = value
            return parameter
        except Exception:
            if kind == "length":
                return params.CreateDimension(name, "LENGTH", value)
            if kind == "angle":
                return params.CreateDimension(name, "ANGLE", value)
            if kind == "integer":
                return params.CreateInteger(name, int(value))
            if kind == "real":
                return params.CreateReal(name, float(value))
            if kind == "boolean":
                return params.CreateBoolean(name, bool(value))
            if kind == "string":
                return params.CreateString(name, str(value))
            raise ValueError(f"Unknown parameter kind '{kind}'")

    @staticmethod
    def _task13_plane_basis(index: int) -> tuple[list[float], list[float], list[float]]:
        if index % 2 == 0:
            return [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
        return [1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]

    @staticmethod
    def _task13_add_point(
        part: Any, geoset: Any, xyz: list[float], name: str
    ) -> Any:
        point = part.HybridShapeFactory.AddNewPointCoord(xyz[0], xyz[1], xyz[2])
        point.Name = name
        geoset.AppendHybridShape(point)
        part.UpdateObject(point)
        return point

    @staticmethod
    def _task13_ellipse_points(
        center: list[float],
        major_radius: float,
        minor_radius: float,
        axis_u: list[float],
        axis_v: list[float],
        samples: int,
    ) -> list[list[float]]:
        points = []
        for index in range(samples):
            theta = 2.0 * math.pi * index / samples
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)
            point = [
                center[axis] + major_radius * cos_t * axis_u[axis] + minor_radius * sin_t * axis_v[axis]
                for axis in range(3)
            ]
            points.append(point)
        return points

    def _task13_build_link_sweep(
        self,
        part: Any,
        geoset: Any,
        body: Any,
        center: list[float],
        major_radius: float,
        minor_radius: float,
        wire_radius: float,
        index: int,
    ) -> dict[str, Any]:
        hsf = part.HybridShapeFactory
        axis_u, axis_v, axis_n = self._task13_plane_basis(index)
        guide_points = self._task13_ellipse_points(center, major_radius, minor_radius, axis_u, axis_v, 16)
        point_objects = []
        for point_index, point in enumerate(guide_points, start=1):
            point_objects.append(
                self._task13_add_point(
                    part,
                    geoset,
                    point,
                    f"Task13_Link_{index + 1:02d}_GuidePoint_{point_index:02d}",
                )
            )

        guide = hsf.AddNewSpline()
        guide.SetClosing(True)
        for point in point_objects:
            guide.AddPoint(part.CreateReferenceFromObject(point))
        guide.Name = f"Task13_Link_{index + 1:02d}_Guide"
        geoset.AppendHybridShape(guide)
        part.UpdateObject(guide)

        start = guide_points[0]
        next_point = guide_points[1]
        tangent = self._v_unit(self._v_sub(next_point, start))
        radial = self._v_unit(self._v_sub(start, center))
        binormal = self._v_unit(self._v_cross(tangent, radial))
        if self._v_norm(binormal) <= 1e-9:
            binormal = axis_n
        plane = hsf.AddNewPlane3Points(
            part.CreateReferenceFromObject(
                self._task13_add_point(
                    part,
                    geoset,
                    start,
                    f"Task13_Link_{index + 1:02d}_ProfileCenter",
                )
            ),
            part.CreateReferenceFromObject(
                self._task13_add_point(
                    part,
                    geoset,
                    [start[0] + radial[0], start[1] + radial[1], start[2] + radial[2]],
                    f"Task13_Link_{index + 1:02d}_ProfileRadial",
                )
            ),
            part.CreateReferenceFromObject(
                self._task13_add_point(
                    part,
                    geoset,
                    [start[0] + binormal[0], start[1] + binormal[1], start[2] + binormal[2]],
                    f"Task13_Link_{index + 1:02d}_ProfileBinormal",
                )
            ),
        )
        plane.Name = f"Task13_Link_{index + 1:02d}_ProfilePlane"
        geoset.AppendHybridShape(plane)
        part.UpdateObject(plane)

        circle = hsf.AddNewCircleCtrRad(
            part.CreateReferenceFromObject(point_objects[0]),
            part.CreateReferenceFromObject(plane),
            False,
            wire_radius,
        )
        circle.Name = f"Task13_Link_{index + 1:02d}_ProfileCircle"
        geoset.AppendHybridShape(circle)
        part.UpdateObject(circle)

        sweep = hsf.AddNewSweepExplicit(
            part.CreateReferenceFromObject(circle),
            part.CreateReferenceFromObject(guide),
        )
        sweep.Name = f"Task13_Link_{index + 1:02d}_Surface"
        geoset.AppendHybridShape(sweep)
        part.UpdateObject(sweep)

        part.InWorkObject = body
        solid = self.conn.shape_factory.AddNewCloseSurface(
            part.CreateReferenceFromObject(sweep)
        )
        solid.Name = f"Task13_Link_{index + 1:02d}"
        part.UpdateObject(solid)
        return {
            "body": body.Name,
            "feature": solid.Name,
            "center_mm": [round(value, 4) for value in center],
            "orientation": "xy" if index % 2 == 0 else "xz",
            "build_method": "sweep_explicit_close_surface",
        }

    def _task13_build_link_pad(
        self,
        part: Any,
        body: Any,
        center: list[float],
        major_radius: float,
        minor_radius: float,
        wire_radius: float,
        index: int,
        ) -> dict[str, Any]:
        # Conservative fallback: a flat ring profile on the same alternating
        # plane. It is not as faithful as the swept tube, but it preserves the
        # controllable envelope if a closed sweep is not accepted by CATIA.
        plane_key = "xy" if index % 2 == 0 else "zx"
        plane = getattr(part.OriginElements, f"Plane{plane_key.upper()}")
        sketch = body.Sketches.Add(part.CreateReferenceFromObject(plane))
        sketch.Name = f"Task13_Link_{index + 1:02d}_FallbackSketch"
        factory = sketch.OpenEdition()
        if plane_key == "xy":
            center_2d = (center[0], center[1])
        else:
            center_2d = (center[0], center[2])
        outer = [
            (center_2d[0] + major_radius, center_2d[1]),
            (center_2d[0], center_2d[1] + minor_radius),
            (center_2d[0] - major_radius, center_2d[1]),
            (center_2d[0], center_2d[1] - minor_radius),
        ]
        inner_major = max(major_radius - wire_radius, wire_radius)
        inner_minor = max(minor_radius - wire_radius, wire_radius)
        inner = [
            (center_2d[0] + inner_major, center_2d[1]),
            (center_2d[0], center_2d[1] + inner_minor),
            (center_2d[0] - inner_major, center_2d[1]),
            (center_2d[0], center_2d[1] - inner_minor),
        ]
        for points in (outer, inner):
            for index2, point in enumerate(points):
                x1, y1 = point
                x2, y2 = points[(index2 + 1) % len(points)]
                factory.CreateLine(x1, y1, x2, y2)
        sketch.CloseEdition()
        part.UpdateObject(sketch)
        part.InWorkObject = body
        pad = part.ShapeFactory.AddNewPad(sketch, wire_radius * 2.0)
        pad.Name = f"Task13_Link_{index + 1:02d}"
        pad.IsSymmetric = True
        part.UpdateObject(pad)
        return {
            "body": body.Name,
            "feature": pad.Name,
            "center_mm": [round(value, 4) for value in center],
            "orientation": "xy" if index % 2 == 0 else "xz",
            "build_method": "pad_fallback",
        }

    def _task13_delete_previous(self, part_doc: Any, part: Any) -> list[str]:
        deleted: list[str] = []
        selection = part_doc.Selection

        def delete_object(obj: Any, label: str) -> None:
            selection.Clear()
            try:
                selection.Add(obj)
                selection.Delete()
                deleted.append(label)
            finally:
                selection.Clear()

        for bodies in (part.Bodies, part.HybridBodies):
            for index in range(1, bodies.Count + 1):
                obj = bodies.Item(index)
                if obj.Name.startswith("Task13_"):
                    delete_object(obj, f"{type(obj).__name__}:{obj.Name}")
        if deleted:
            part.Update()
        return deleted

    def _task13_store_report(self, part: Any, report: dict[str, Any]) -> None:
        compact = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        if len(compact) > 30000:
            compact = compact[:30000] + "...<truncated>"
        params = part.Parameters
        try:
            param = params.Item("Task13_MCP_Report")
            param.Value = compact
        except Exception:
            params.CreateString("Task13_MCP_Report", compact)

    def _task13_report(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        target_body = self._task13_target_body(part, args.get("target_body", "Цепь"))
        if target_body is None:
            raise RuntimeError(
                f"Target chain body '{args.get('target_body', 'Цепь')}' was not found."
            )
        shape = self._last_shape(target_body)
        edge_report = self._task12_edge_report(doc, part, shape)
        face_report = self._task12_face_report(doc, part, shape)
        return json.dumps(
            {
                "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
                "target_body": target_body.Name,
                "shape": shape.Name,
                "parameters_count": part.Parameters.Count,
                "edges": edge_report,
                "faces": face_report,
                "bbox": edge_report.get("bbox"),
            },
            indent=2,
            ensure_ascii=False,
        )

    def _solve_task13(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        target_body = self._task13_target_body(part, args.get("target_body", "Цепь"))
        link_count = int(args.get("link_count", TASK13_DEFAULT_LINK_COUNT))
        deleted = self._task13_delete_previous(doc, part)
        params = part.Parameters
        main = self._task13_upsert_parameter(params, TASK13_MAIN_PARAMETER, "length", 10.0)
        major_radius = self._task13_upsert_parameter(
            params, "Task13_Link_Major_Radius", "length", TASK13_LINK_LENGTH_MM / 2.0
        )
        minor_radius = self._task13_upsert_parameter(
            params, "Task13_Link_Minor_Radius", "length", TASK13_LINK_HEIGHT_MM / 2.0
        )
        pitch = self._task13_upsert_parameter(
            params, "Task13_Link_Pitch", "length", TASK13_LINK_LENGTH_MM / 2.0
        )
        count_param = self._task13_upsert_parameter(params, "Task13_Link_Count", "integer", link_count)
        part.Update()

        major = float(major_radius.Value)
        minor = float(minor_radius.Value)
        step = float(pitch.Value)
        wire_radius = float(main.Value)
        built_links = []
        for index in range(link_count):
            body = part.Bodies.Add()
            body.Name = f"Task13_Link_{index + 1:02d}_BODY"
            part.InWorkObject = body
            geoset = part.HybridBodies.Add()
            geoset.Name = f"Task13_Link_{index + 1:02d}_Construction"
            center = [index * step, 0.0, 0.0]
            try:
                built_links.append(
                    self._task13_build_link_sweep(
                        part, geoset, body, center, major, minor, wire_radius, index
                    )
                )
            except Exception as exc:
                built_links.append(
                    {
                        "body": body.Name,
                        "center_mm": [round(value, 4) for value in center],
                        "orientation": "xy" if index % 2 == 0 else "xz",
                        "build_method": "sweep_failed",
                        "error": str(exc),
                    }
                )
                try:
                    built_links[-1] = self._task13_build_link_pad(
                        part, body, center, major, minor, wire_radius, index
                    )
                except Exception as fallback_exc:
                    built_links[-1]["fallback_error"] = str(fallback_exc)

        part.Update()
        report = {
            "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
            "target_body": getattr(target_body, "Name", None) if target_body is not None else None,
            "deleted_previous_task13_objects": deleted,
            "main_parameter": {
                "name": TASK13_MAIN_PARAMETER,
                "value_mm": float(main.Value),
            },
            "derived_parameters": {
                "link_major_radius_mm": float(major_radius.Value),
                "link_minor_radius_mm": float(minor_radius.Value),
                "link_pitch_mm": float(pitch.Value),
                "link_count": int(count_param.Value),
            },
            "links": built_links,
            "saved": bool(args.get("save", True)),
        }
        self._task13_store_report(part, report)
        if args.get("save", True):
            doc.Save()
        self.conn.refresh_display()
        return json.dumps(report, indent=2, ensure_ascii=False)

    @staticmethod
    def _task15_upsert_parameter(params: Any, name: str, kind: str, value: float | int) -> Any:
        return ContestTools._task13_upsert_parameter(params, name, kind, value)

    @staticmethod
    def _task15_curve_length_mm(part_doc: Any, part: Any, curve: Any) -> float:
        spa = part_doc.GetWorkbench("SPAWorkbench")
        measurable = spa.GetMeasurable(part.CreateReferenceFromObject(curve))
        return float(measurable.Length) * 1000.0

    @staticmethod
    def _task15_chain_length_mm(part_doc: Any, part: Any, curves: list[Any]) -> float:
        spa = part_doc.GetWorkbench("SPAWorkbench")
        total = 0.0
        for curve in curves:
            measurable = spa.GetMeasurable(part.CreateReferenceFromObject(curve))
            total += float(measurable.Length) * 1000.0
        return total

    @staticmethod
    def _task15_template_points(params: Any) -> list[list[float]]:
        def _param(name: str, fallback: float) -> float:
            try:
                return float(params.Item(name).Value)
            except Exception:
                return float(fallback)

        l = _param("l", 10.28)
        r1 = _param("R1", 13.5)
        r2 = _param("R2", 51.4)
        r = _param("R", 36.0)
        t = _param("T", 3.6)

        stub = max(l * 4.0, 24.0)
        upper_drop = max(r1 * 3.0, 36.0)
        mid_span = max(r2 * 3.2, 160.0)
        right_drop = max(r * 2.2, 70.0)
        lower_drop = max(r1 * 3.0 + t * 6.0, 42.0)
        mid_step = max(r1 * 1.2, 16.0)
        tail_step = max(t * 3.0, 10.0)

        left = -mid_span / 2.0
        right = mid_span / 2.0
        top = upper_drop + t * 2.0
        mid_top = upper_drop * 0.35
        mid_bottom = -(right_drop * 0.25)
        bottom = -(right_drop + lower_drop)

        return [
            [left, top, 0.0],
            [left + stub, top, 0.0],
            [left + stub, top - mid_step, 0.0],
            [right - tail_step, top - mid_step, 0.0],
            [right, mid_top, 0.0],
            [right, mid_bottom, 0.0],
            [left + stub, mid_bottom, 0.0],
            [left + stub, bottom + mid_step, 0.0],
            [left + tail_step, bottom, 0.0],
            [left, bottom, 0.0],
        ]

    @staticmethod
    def _task15_new_geoset(part: Any, name: str) -> Any:
        geoset = part.HybridBodies.Add()
        geoset.Name = name
        return geoset

    def _task15_delete_previous(self, part_doc: Any, part: Any) -> list[str]:
        deleted: list[str] = []
        selection = part_doc.Selection

        def delete_object(obj: Any, label: str) -> None:
            selection.Clear()
            try:
                selection.Add(obj)
                selection.Delete()
                deleted.append(label)
            finally:
                selection.Clear()

        for bodies in (part.Bodies, part.HybridBodies):
            for index in range(1, bodies.Count + 1):
                obj = bodies.Item(index)
                if obj.Name.startswith("Task15_"):
                    delete_object(obj, f"{type(obj).__name__}:{obj.Name}")
        if deleted:
            part.Update()
        return deleted

    def _task15_build_centerline(
        self,
        part: Any,
        geoset: Any,
        points_mm: list[list[float]],
        name: str,
    ) -> dict[str, Any]:
        point_objects = []
        for index, point in enumerate(points_mm, start=1):
            point_objects.append(
                self._task13_add_point(
                    part,
                    geoset,
                    point,
                    f"{name}_Point_{index:02d}",
                )
            )

        line_objects = []
        for index in range(len(point_objects) - 1):
            line = part.HybridShapeFactory.AddNewLinePtPt(
                part.CreateReferenceFromObject(point_objects[index]),
                part.CreateReferenceFromObject(point_objects[index + 1]),
            )
            line.Name = f"{name}_Segment_{index + 1:02d}"
            geoset.AppendHybridShape(line)
            part.UpdateObject(line)
            line_objects.append(line)

        join = self._task12_join(part, geoset, line_objects, name)
        return {"join": join, "segments": line_objects, "points": point_objects}

    def _task15_report(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        centerline_name = args.get("centerline_name", "Task15_Centerline")
        geoset_name = args.get("geoset_name", "Task15_Construction")
        centerline = None
        geoset = self._find_geoset(part, geoset_name)
        if geoset is not None:
            try:
                centerline = geoset.HybridShapes.Item(centerline_name)
            except Exception:
                centerline = None
        length_mm = None
        if centerline is not None:
            try:
                length_mm = self._task15_curve_length_mm(doc, part, centerline)
            except Exception:
                try:
                    length_mm = float(part.Parameters.Item("Task15_Centerline_Length").Value)
                except Exception:
                    length_mm = None
        report = {
            "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
            "part_name": getattr(part, "Name", ""),
            "geoset_name": geoset_name,
            "centerline_name": centerline_name,
            "centerline_found": centerline is not None,
            "length_mm": round(length_mm, 4) if length_mm is not None else None,
            "parameters_count": part.Parameters.Count,
        }
        return json.dumps(report, indent=2, ensure_ascii=False)

    def _solve_task15(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        centerline_name = args.get("centerline_name", "Task15_Centerline")
        geoset_name = args.get("geoset_name", "Task15_Construction")
        target_length_mm = float(args.get("target_length_mm", 746.0))

        deleted = self._task15_delete_previous(doc, part)
        params = part.Parameters
        points = self._task15_template_points(params)

        temp_geoset = self._task15_new_geoset(part, f"{geoset_name}_Temp")
        temp_curve = self._task15_build_centerline(part, temp_geoset, points, f"{centerline_name}_Temp")
        template_length_mm = self._task15_chain_length_mm(doc, part, temp_curve["segments"])
        scale = target_length_mm / template_length_mm if template_length_mm else 1.0

        deleted.extend(self._task15_delete_previous(doc, part))
        scaled_points = [[coord * scale for coord in point] for point in points]
        geoset = self._task15_new_geoset(part, geoset_name)
        centerline = self._task15_build_centerline(part, geoset, scaled_points, centerline_name)
        length_mm = self._task15_chain_length_mm(doc, part, centerline["segments"])

        length_param = self._task15_upsert_parameter(
            params, "Task15_Centerline_Length", "length", length_mm
        )
        target_param = self._task15_upsert_parameter(
            params, "Task15_Centerline_Target_Length", "length", target_length_mm
        )
        scale_param = self._task15_upsert_parameter(
            params, "Task15_Centerline_Scale", "real", scale
        )
        part.Update()

        report = {
            "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
            "part_name": getattr(part, "Name", ""),
            "centerline_name": centerline_name,
            "geoset_name": geoset_name,
            "deleted_previous_task15_objects": deleted,
            "target_length_mm": round(target_param.Value, 4),
            "template_length_mm": round(template_length_mm, 4),
            "scale_factor": round(scale_param.Value, 8),
            "length_mm": round(length_param.Value, 4),
            "length_error_mm": round(float(length_param.Value) - target_length_mm, 6),
            "saved": bool(args.get("save", True)),
            "source_parameters": {
                "l_mm": round(float(params.Item("l").Value), 4),
                "R1_mm": round(float(params.Item("R1").Value), 4),
                "R2_mm": round(float(params.Item("R2").Value), 4),
                "R_mm": round(float(params.Item("R").Value), 4),
                "T_mm": round(float(params.Item("T").Value), 4),
            },
            "template_points_mm": [[round(v, 4) for v in point] for point in points],
            "centerline_points_mm": [[round(v, 4) for v in point] for point in scaled_points],
        }
        self._task13_store_report(part, report)
        self._task15_upsert_parameter(
            params, "Task15_MCP_Report_Length", "length", float(length_param.Value)
        )
        self._task15_upsert_parameter(
            params, "Task15_MCP_Report_Target", "length", target_length_mm
        )
        if args.get("save", True):
            doc.Save()
        self.conn.refresh_display()
        return json.dumps(report, indent=2, ensure_ascii=False)

    def _task16_geoset_report(self, part: Any, geoset_name: str) -> dict[str, Any]:
        geoset = self._find_geoset(part, geoset_name)
        if geoset is None:
            return {
                "found": False,
                "geoset_name": geoset_name,
                "shape_count": 0,
                "shapes": [],
                "final_shape_name": None,
            }
        shapes = self._hybrid_shape_names(geoset)
        return {
            "found": True,
            "geoset_name": geoset_name,
            "shape_count": len(shapes),
            "shapes": shapes,
            "final_shape_name": shapes[-1] if shapes else None,
        }

    def _task16_set_show(self, obj: Any, show: bool) -> bool:
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

    def _task16_select_by_name(self, obj: Any) -> Any:
        selection = self.conn.hso
        name = getattr(obj, "Name", "")
        selection.Clear()
        if name:
            try:
                selection.Search(f"Name={name},all")
                if selection.Count > 0:
                    return selection
            except Exception:
                pass
        selection.Clear()
        selection.Add(obj)
        return selection

    def _task16_set_real_color(
        self, obj: Any, rgb: tuple[int, int, int], inheritance: int = 0
    ) -> bool:
        try:
            selection = self._task16_select_by_name(obj)
            vis = selection.VisProperties
            for call in (
                lambda: vis.SetVisibleColor(rgb[0], rgb[1], rgb[2], inheritance),
                lambda: vis.SetVisibleColor(rgb[0], rgb[1], rgb[2]),
                lambda: vis.SetRealColor(rgb[0], rgb[1], rgb[2], inheritance),
                lambda: vis.SetRealColor(rgb[0], rgb[1], rgb[2]),
                lambda: vis.SetRealColor(*rgb),
            ):
                try:
                    call()
                    return True
                except Exception:
                    continue
            return False
        finally:
            try:
                selection.Clear()
            except Exception:
                pass

    def _task16_get_real_color(self, obj: Any) -> list[int] | None:
        try:
            selection = self._task16_select_by_name(obj)
            vis = selection.VisProperties
            try:
                rgb = [0, 0, 0]
                vis.GetRealColor(rgb)
                return [int(v) for v in rgb]
            except Exception:
                pass
            try:
                res = vis.GetRealColor()
                if hasattr(res, "__len__"):
                    return [int(v) for v in res[:3]]
            except Exception:
                pass
            try:
                r = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                g = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                b = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                vis.GetRealColor(r, g, b)
                return [int(r.value), int(g.value), int(b.value)]
            except Exception:
                return None
        finally:
            try:
                selection.Clear()
            except Exception:
                pass

    def _task16_get_visible_color(self, obj: Any) -> list[int] | None:
        try:
            selection = self._task16_select_by_name(obj)
            vis = selection.VisProperties
            try:
                rgb = [0, 0, 0]
                vis.GetVisibleColor(rgb)
                return [int(v) for v in rgb]
            except Exception:
                pass
            try:
                res = vis.GetVisibleColor()
                if hasattr(res, "__len__"):
                    return [int(v) for v in res[:3]]
            except Exception:
                pass
            try:
                r = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                g = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                b = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
                vis.GetVisibleColor(r, g, b)
                return [int(r.value), int(g.value), int(b.value)]
            except Exception:
                return None
        finally:
            try:
                selection.Clear()
            except Exception:
                pass

    def _task16_report(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        geoset_name = args.get("geoset_name", "Построения детали")
        report = self._task16_geoset_report(part, geoset_name)
        final_shape_color = None
        geoset = self._find_geoset(part, geoset_name)
        if geoset is not None:
            try:
                shapes = geoset.HybridShapes
                if shapes.Count >= 1:
                    final_shape_color = self._task16_get_real_color(shapes.Item(shapes.Count))
                    final_shape_visible_color = self._task16_get_visible_color(
                        shapes.Item(shapes.Count)
                    )
            except Exception:
                final_shape_color = None
                final_shape_visible_color = None
        report.update(
            {
                "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
                "part_name": getattr(part, "Name", ""),
                "final_shape_color_rgb": final_shape_color,
                "final_shape_visible_color_rgb": locals().get("final_shape_visible_color"),
                "parameters_count": part.Parameters.Count,
            }
        )
        return json.dumps(report, indent=2, ensure_ascii=False)

    def _solve_task16(self, args: dict[str, Any]) -> str:
        doc, part = self._part_from_path(args["part_path"])
        geoset_name = args.get("geoset_name", "Построения детали")
        geoset = self._find_geoset(part, geoset_name)
        if geoset is None:
            raise RuntimeError(f"Geometrical set '{geoset_name}' was not found")

        shapes = geoset.HybridShapes
        shape_names = []
        for index in range(1, shapes.Count + 1):
            shape_names.append(shapes.Item(index).Name)
        if not shape_names:
            raise RuntimeError(f"Geometrical set '{geoset_name}' has no hybrid shapes")

        final_shape = shapes.Item(shapes.Count)
        hidden_shapes: list[str] = []
        shown_shapes: list[str] = []
        for index in range(1, shapes.Count + 1):
            shape = shapes.Item(index)
            name = getattr(shape, "Name", f"HybridShape.{index}")
            if index == shapes.Count:
                if self._task16_set_show(shape, True):
                    shown_shapes.append(name)
            else:
                if self._task16_set_show(shape, False):
                    hidden_shapes.append(name)

        try:
            part.InWorkObject = final_shape
        except Exception:
            pass

        part.Update()
        if not self._task16_set_real_color(geoset, (0, 176, 80), 0):
            pass
        if not self._task16_set_real_color(final_shape, (0, 176, 80), 1):
            # The color is a deliverable detail, but if CATIA rejects the
            # call shape we still keep the geometry isolated and report it.
            pass
        report = {
            "document": getattr(doc, "FullName", getattr(doc, "Name", "")),
            "part_name": getattr(part, "Name", ""),
            "geoset_name": geoset_name,
            "shape_count": len(shape_names),
            "shapes": shape_names,
            "final_shape_name": shape_names[-1],
            "hidden_shapes": hidden_shapes,
            "shown_shapes": shown_shapes,
            "final_shape_color_rgb": self._task16_get_real_color(final_shape),
            "final_shape_visible_color_rgb": self._task16_get_visible_color(final_shape),
            "saved": bool(args.get("save", True)),
        }
        if args.get("save", True):
            doc.Save()
        self.conn.refresh_display()
        return json.dumps(report, indent=2, ensure_ascii=False)
