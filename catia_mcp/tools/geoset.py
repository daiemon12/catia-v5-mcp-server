"""Geometrical-set management and stable reference selection."""

from __future__ import annotations

import json
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools._geometry import GeometryContext, object_schema, ref_handle, result


class GeosetTools:
    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self.geo = GeometryContext(connection)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_new_geoset",
                "description": "Create and activate a geometrical set.",
                "inputSchema": object_schema(
                    {"name": {"type": "string", "minLength": 1}, "parent": {"type": "string"}},
                    ["name"],
                ),
            },
            {
                "name": "catia_list_geosets",
                "description": "List geometrical sets in the active Part.",
                "inputSchema": object_schema({}),
            },
            {
                "name": "catia_set_active_geoset",
                "description": "Set the geometrical set used by GSD tools.",
                "inputSchema": object_schema({"name": {"type": "string"}}, ["name"]),
            },
            {
                "name": "catia_select_reference",
                "description": "Resolve and validate a stable feature/sub-element reference handle.",
                "inputSchema": object_schema(
                    {
                        "feature": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": ["feature", "face", "edge", "vertex"],
                            "default": "feature",
                        },
                        "index": {"type": "integer", "minimum": 1},
                        "brep_name": {"type": "string"},
                        "nearest_point": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                        "normal": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 3,
                            "maxItems": 3,
                        },
                    }
                ),
            },
            {
                "name": "catia_list_subelements",
                "description": "List stable face, edge, or vertex handles on a named feature.",
                "inputSchema": object_schema(
                    {
                        "feature": {"type": "string"},
                        "kind": {"type": "string", "enum": ["face", "edge", "vertex"]},
                    },
                    ["feature", "kind"],
                ),
            },
        ]

    def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "catia_new_geoset":
            part = self.geo.part
            parent = args.get("parent")
            collection = self.geo.geoset(parent).HybridBodies if parent else part.HybridBodies
            body = collection.Add()
            body.Name = args["name"]
            part.InWorkObject = body
            self.conn.active_geoset_name = body.Name
            return result(name=body.Name, parent=parent, active=True)
        if tool_name == "catia_list_geosets":
            return json.dumps(self._list(self.geo.part.HybridBodies), indent=2)
        if tool_name == "catia_set_active_geoset":
            body = self.geo.geoset(args["name"])
            self.geo.part.InWorkObject = body
            return result(name=body.Name, active=True)
        if tool_name == "catia_select_reference":
            spec = dict(args)
            if spec.get("brep_name"):
                self.geo.resolve(spec)
                return result(
                    reference=ref_handle(
                        spec.get("feature", ""), spec.get("kind", "feature"), spec["brep_name"]
                    )
                )
            if not spec.get("feature"):
                raise ValueError("feature is required when brep_name is not supplied")
            if spec.get("kind", "feature") == "feature":
                self.geo.resolve(spec)
                return result(reference=ref_handle(spec["feature"]))
            matches = self.geo.list_subelements(spec["feature"], spec["kind"])
            chosen = self.geo._choose_subelement(matches, spec)
            return result(
                reference=ref_handle(spec["feature"], spec["kind"], chosen.get("brep_name")),
                index=chosen["index"],
            )
        if tool_name == "catia_list_subelements":
            values = self.geo.list_subelements(args["feature"], args["kind"])
            return json.dumps(
                [
                    {
                        key: value
                        for key, value in item.items()
                        if key not in {"object", "reference"}
                    }
                    for item in values
                ],
                indent=2,
            )
        raise ValueError(f"Unknown geoset tool: {tool_name}")

    def _list(self, bodies: Any, parent: str | None = None) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for index in range(1, bodies.Count + 1):
            body = bodies.Item(index)
            values.append(
                {
                    "name": body.Name,
                    "parent": parent,
                    "active": body.Name == self.conn.active_geoset_name,
                }
            )
            try:
                values.extend(self._list(body.HybridBodies, body.Name))
            except Exception:
                pass
        return values
