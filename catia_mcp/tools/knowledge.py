"""CATIA Knowledgeware parameters, formulas, and design tables."""

from __future__ import annotations

import os
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.paths import normalize_catia_path
from catia_mcp.tools._geometry import object_schema, result


class KnowledgeTools:
    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    @staticmethod
    def _com_type_name(obj: Any) -> str:
        try:
            return obj._oleobj_.GetTypeInfo().GetDocumentation(-1)[0]
        except Exception:
            return type(obj).__name__

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
                "name": "catia_upsert_formula",
                "description": (
                    "Create a formula if it does not exist, or modify an existing formula "
                    "with the same name."
                ),
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
                "name": "catia_copy_parameter_as_link",
                "description": (
                    "Copy a parameter from one open CATIA Part into another open Part as "
                    "an external linked parameter (As Result With Link)."
                ),
                "inputSchema": object_schema(
                    {
                        "source_document_path": {"type": "string"},
                        "source_parameter": {"type": "string"},
                        "target_document_path": {"type": "string"},
                    },
                    ["source_document_path", "source_parameter", "target_document_path"],
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
            {
                "name": "catia_list_relations",
                "description": (
                    "List Knowledgeware relations in the active Part, including formulas "
                    "and their readable text when available."
                ),
                "inputSchema": object_schema(
                    {
                        "filter": {
                            "type": "string",
                            "description": "Optional case-insensitive substring filter for relation name/type/text.",
                        }
                    },
                    [],
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
        if tool_name == "catia_upsert_formula":
            target = params.Item(args["target"])
            try:
                formula = part.Relations.Item(args["name"])
                formula.Modify(args["expression"])
                created = False
            except Exception:
                formula = part.Relations.CreateFormula(
                    args["name"],
                    args.get("comment", "Created by CATIA MCP"),
                    target,
                    args["expression"],
                )
                created = True
            part.UpdateObject(formula)
            return result(
                name=formula.Name,
                target=args["target"],
                expression=args["expression"],
                created=created,
            )
        if tool_name == "catia_copy_parameter_as_link":
            source_doc = self._document_from_path(args["source_document_path"])
            target_doc = self._document_from_path(args["target_document_path"])
            source_part = source_doc.Part
            target_part = target_doc.Part
            source_param = source_part.Parameters.Item(args["source_parameter"])

            source_sel = source_doc.Selection
            target_sel = target_doc.Selection
            source_sel.Clear()
            target_sel.Clear()
            try:
                source_sel.Add(source_param)
                source_sel.Copy()
                source_sel.Clear()

                target_sel.Add(target_part)
                target_sel.PasteSpecial("CATPrtResult")

                pasted_param = None
                for index in range(1, target_sel.Count + 1):
                    candidate = target_sel.Item(index).Value
                    if self._com_type_name(candidate).lower() != "part":
                        pasted_param = candidate
                        break
                if pasted_param is None:
                    raise RuntimeError("Could not identify the pasted external parameter.")

                relation_name = target_part.Parameters.GetNameToUseInRelation(pasted_param)
                target_part.UpdateObject(pasted_param)
                return result(
                    source_document=getattr(source_doc, "FullName", getattr(source_doc, "Name", "")),
                    target_document=getattr(target_doc, "FullName", getattr(target_doc, "Name", "")),
                    source_parameter=args["source_parameter"],
                    target_parameter=relation_name,
                    target_parameter_name=getattr(pasted_param, "Name", relation_name),
                )
            finally:
                try:
                    source_sel.Clear()
                except Exception:
                    pass
                try:
                    target_sel.Clear()
                except Exception:
                    pass
        if tool_name == "catia_create_design_table":
            table = part.Relations.CreateDesignTable(
                args["name"], "Created by CATIA MCP", args.get("copy_mode", True), args["file_path"]
            )
            for parameter_name in args["parameters"]:
                table.AddAssociation(params.Item(parameter_name), parameter_name)
            part.UpdateObject(table)
            return result(
                name=table.Name, file_path=args["file_path"], parameters=args["parameters"]
            )
        if tool_name == "catia_list_relations":
            relation_filter = (args.get("filter") or "").strip().lower()
            relations = part.Relations
            items: list[dict[str, Any]] = []
            for index in range(1, relations.Count + 1):
                relation = relations.Item(index)
                entry: dict[str, Any] = {
                    "index": index,
                    "name": getattr(relation, "Name", f"Relation.{index}"),
                    "type": self._com_type_name(relation),
                }
                for attr in ("Comment", "Text", "Formula", "Value"):
                    try:
                        value = getattr(relation, attr)
                    except Exception:
                        continue
                    if value not in (None, ""):
                        entry[attr.lower()] = value
                haystack = " ".join(str(entry.get(field, "")) for field in ("name", "type", "comment", "text", "formula", "value")).lower()
                if relation_filter and relation_filter not in haystack:
                    continue
                items.append(entry)
            return result(relations=items, count=len(items))
        raise ValueError(f"Unknown Knowledgeware tool: {tool_name}")

    def _document_from_path(self, document_path: str) -> Any:
        self.conn.ensure_connected()
        docs = self.conn.documents
        document_path = normalize_catia_path(document_path)
        target = os.path.normcase(os.path.abspath(document_path))
        for index in range(1, docs.Count + 1):
            existing = docs.Item(index)
            full_name = getattr(existing, "FullName", "") or ""
            if full_name and os.path.normcase(os.path.abspath(full_name)) == target:
                try:
                    existing.Activate()
                except Exception:
                    pass
                return existing
        return docs.Open(document_path)
