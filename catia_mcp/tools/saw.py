"""Parametric circular saw blade builder for CATIA V5."""

from __future__ import annotations

import json
import math
import os
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.paths import normalize_catia_path
from catia_mcp.tools._geometry import object_schema
from catia_mcp.tools.knowledge import KnowledgeTools


DEFAULTS = {
    "R": 36.0,
    "N": 22,
    "document_path": r"C:\Users\sup02\Documents\CATIA_2026_LADUGA\08\08.CATPart",
    "output_path": r"C:\Users\sup02\Documents\CATIA_2026_LADUGA\08\08.CATPart",
}


class SawTools:
    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        positive = {"type": "number", "exclusiveMinimum": 0}
        props: dict[str, Any] = {
            "document_path": {"type": "string"},
            "output_path": {"type": "string"},
            "R": positive,
            "N": {"type": "integer", "minimum": 3},
        }
        return [
            {
                "name": "catia_design_circular_saw",
                "description": (
                    "Build a simplified parametric circular saw blade in an existing CATPart. "
                    "The blade scales from R and tooth count N, with derived parameters r, h, l, "
                    "R1, R2 and T created in Knowledgeware."
                ),
                "inputSchema": object_schema(
                    props,
                    ["document_path", "R", "N"],
                ),
            }
        ]

    @staticmethod
    def validate(arguments: dict[str, Any]) -> dict[str, Any]:
        values = {**DEFAULTS, **arguments}
        for name in ("R",):
            if not isinstance(values.get(name), (int, float)) or values[name] <= 0:
                raise ValueError(f"{name} must be greater than zero")
        if not isinstance(values.get("N"), int) or values["N"] < 3:
            raise ValueError("N must be an integer >= 3")
        values["r"] = values["R"] / 3.0
        values["h"] = values["R"] / 8.0
        values["l"] = 2.0 * math.pi * values["R"] / values["N"]
        values["R1"] = values["h"] * 3.0
        values["R2"] = values["l"] * 5.0
        values["T"] = values["R"] / 10.0
        values["outer_radius"] = values["R"] + values["h"]
        values["tooth_step_deg"] = 360.0 / values["N"]
        return values

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if tool_name != "catia_design_circular_saw":
            raise ValueError(f"Unknown saw tool: {tool_name}")
        values = self.validate(arguments)
        report: dict[str, Any] = {
            "status": "in_progress",
            "parameters": values,
            "warnings": [],
            "phases": [],
        }
        try:
            self.conn.ensure_connected()
            doc = self._document_from_path(values["document_path"])
            try:
                doc.Activate()
            except Exception:
                pass

            part = doc.Part
            part_prefix = os.path.splitext(doc.Name)[0]
            knowledge = KnowledgeTools(self.conn)
            for name, kind, value in (
                ("R", "length", values["R"]),
                ("N", "integer", values["N"]),
                ("r", "length", values["r"]),
                ("h", "length", values["h"]),
                ("l", "length", values["l"]),
                ("R1", "length", values["R1"]),
                ("R2", "length", values["R2"]),
                ("T", "length", values["T"]),
            ):
                knowledge.execute(
                    "catia_create_parameter",
                    {"name": name, "type": kind, "value": value},
                )
            report["phases"].append({"name": "parameters", "status": "complete"})
            for name, expression in (
                ("h", "R / 8"),
                ("l", "2 * 3.141592653589793 * R / N"),
                ("R1", "h * 3"),
                ("R2", "l * 5"),
                ("T", "R / 10"),
                ("r", "R / 3"),
            ):
                try:
                    knowledge.execute(
                        "catia_create_formula",
                        {
                            "name": f"{name}_formula",
                            "target": f"{part_prefix}\\{name}",
                            "expression": expression,
                        },
                    )
                except Exception as exc:
                    report["warnings"].append(f"Formula {name} could not be created: {exc}")

            body = part.MainBody
            origin = part.OriginElements
            blade_sketch = body.Sketches.Add(part.CreateReferenceFromObject(origin.PlaneXY))
            self._try_rename(blade_sketch, "Saw_Perimeter")
            factory = blade_sketch.OpenEdition()
            outline_points = self._tooth_outline_points(values)
            for p1, p2 in zip(outline_points, outline_points[1:] + outline_points[:1]):
                factory.CreateLine(*p1, *p2)
            blade_sketch.CloseEdition()
            part.UpdateObject(blade_sketch)
            report["phases"].append({"name": "perimeter_sketch", "status": "complete"})

            part.InWorkObject = body
            blade = part.ShapeFactory.AddNewPad(blade_sketch, values["T"])
            blade.IsSymmetric = True
            self._try_rename(blade, "Saw_Blade")
            part.UpdateObject(blade)
            report["phases"].append({"name": "blade_pad", "status": "complete", "feature": blade.Name})

            hole_sketch = body.Sketches.Add(part.CreateReferenceFromObject(origin.PlaneXY))
            self._try_rename(hole_sketch, "Saw_Bore")
            hole_factory = hole_sketch.OpenEdition()
            hole_factory.CreateClosedCircle(0, 0, values["r"])
            hole_sketch.CloseEdition()
            part.UpdateObject(hole_sketch)
            part.InWorkObject = body
            bore = part.ShapeFactory.AddNewPocket(hole_sketch, values["T"])
            bore.IsSymmetric = True
            self._try_rename(bore, "Saw_Bore_Cut")
            part.UpdateObject(bore)
            report["phases"].append({"name": "center_bore", "status": "complete", "feature": bore.Name})

            doc.SaveAs(normalize_catia_path(values["output_path"]))
            report["output_path"] = values["output_path"]
            report["status"] = "complete"
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = str(exc)
        return json.dumps(report, indent=2, ensure_ascii=False)

    @staticmethod
    def _tooth_outline_points(values: dict[str, Any]) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        step = math.pi / values["N"]
        start = -math.pi / 2
        outer = values["outer_radius"]
        inner = values["R"]
        for index in range(values["N"] * 2):
            angle = start + index * step
            radius = outer if index % 2 == 0 else inner
            points.append(
                (
                    round(radius * math.cos(angle), 6),
                    round(radius * math.sin(angle), 6),
                )
            )
        return points

    @staticmethod
    def _try_rename(obj: Any, name: str) -> None:
        try:
            obj.Name = name
        except Exception:
            pass

    def _document_from_path(self, document_path: str | None) -> Any:
        if not document_path:
            return self.conn.active_document

        import os

        self.conn.ensure_connected()
        docs = self.conn.documents
        target = os.path.normcase(os.path.abspath(normalize_catia_path(document_path)))
        for index in range(1, docs.Count + 1):
            doc = docs.Item(index)
            full_name = getattr(doc, "FullName", "") or ""
            if full_name and os.path.normcase(os.path.abspath(full_name)) == target:
                return doc
        return docs.Open(normalize_catia_path(document_path))
