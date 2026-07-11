"""CATIA Knowledgeware parameters, formulas, and design tables."""

from __future__ import annotations

from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools._geometry import object_schema, result


class KnowledgeTools:
    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_create_parameter",
                "description": "Create or update a named Knowledgeware parameter.",
                "inputSchema": object_schema(
                    {
                        "name": {"type": "string"},
                        "type": {
                            "type": "string",
                            "enum": ["length", "angle", "real", "integer", "string", "boolean"],
                        },
                        "value": {},
                    },
                    ["name", "type", "value"],
                ),
            },
            {
                "name": "catia_create_formula",
                "description": "Create a formula driving a target parameter.",
                "inputSchema": object_schema(
                    {
                        "name": {"type": "string"},
                        "target": {"type": "string"},
                        "expression": {"type": "string"},
                        "comment": {"type": "string", "default": "Created by CATIA MCP"},
                    },
                    ["name", "target", "expression"],
                ),
            },
            {
                "name": "catia_create_design_table",
                "description": "Bind parameters to an external design-table file.",
                "inputSchema": object_schema(
                    {
                        "name": {"type": "string"},
                        "file_path": {"type": "string"},
                        "parameters": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                        "copy_mode": {"type": "boolean", "default": True},
                    },
                    ["name", "file_path", "parameters"],
                ),
            },
        ]

    def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        part = self.conn.get_active_part()
        params = part.Parameters
        if tool_name == "catia_create_parameter":
            try:
                parameter = params.Item(args["name"])
                parameter.Value = args["value"]
                created = False
            except Exception:
                creators = {
                    "length": lambda: params.CreateDimension(args["name"], "LENGTH", args["value"]),
                    "angle": lambda: params.CreateDimension(args["name"], "ANGLE", args["value"]),
                    "real": lambda: params.CreateReal(args["name"], args["value"]),
                    "integer": lambda: params.CreateInteger(args["name"], args["value"]),
                    "string": lambda: params.CreateString(args["name"], args["value"]),
                    "boolean": lambda: params.CreateBoolean(args["name"], args["value"]),
                }
                parameter = creators[args["type"]]()
                created = True
            part.UpdateObject(parameter)
            return result(
                name=parameter.Name,
                value=getattr(parameter, "Value", args["value"]),
                created=created,
            )
        if tool_name == "catia_create_formula":
            target = params.Item(args["target"])
            formula = part.Relations.CreateFormula(
                args["name"],
                args.get("comment", "Created by CATIA MCP"),
                target,
                args["expression"],
            )
            part.UpdateObject(formula)
            return result(name=formula.Name, target=args["target"], expression=args["expression"])
        if tool_name == "catia_create_design_table":
            table = part.Relations.CreateDesignTable(
                args["name"], "Created by CATIA MCP", args.get("copy_mode", True), args["file_path"]
            )
            for parameter_name in args["parameters"]:
                table.AddAssociation(params.Item(parameter_name))
            part.UpdateObject(table)
            return result(
                name=table.Name, file_path=args["file_path"], parameters=args["parameters"]
            )
        raise ValueError(f"Unknown Knowledgeware tool: {tool_name}")
