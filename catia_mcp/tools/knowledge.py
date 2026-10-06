"""Knowledgeware tools for CATIA V5.

Parameters, formulas, design tables and relation listing on the active
Part, through the documented Parameters / Relations automation
interfaces. Lengths and angles are valuated from strings with explicit
units ("20mm", "45deg"), which sidesteps the magnitude/unit ambiguity of
Dimension.Value.
"""

from __future__ import annotations

import json
from typing import Any

from catia_mcp.connection import CATIAConnection

_UNITS = {"length": "mm", "angle": "deg"}


class KnowledgeTools:
    """Tools for CATIA V5 Knowledgeware (parameters, formulas, design tables)."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_create_parameter",
                "description": (
                    "Create a user parameter on the active Part, or set its "
                    "value if it already exists. Types: length (mm), angle "
                    "(deg), real, integer, string, boolean. Parameters can "
                    "then drive features through formulas."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Parameter name (e.g. 'Thickness')"},
                        "type": {
                            "type": "string",
                            "enum": ["length", "angle", "real", "integer", "string", "boolean"],
                            "description": "Parameter type",
                        },
                        "value": {"description": "Initial value (number, string or boolean)"},
                    },
                    "required": ["name", "type", "value"],
                },
            },
            {
                "name": "catia_set_formula",
                "description": (
                    "Create or update a formula driving a parameter of the "
                    "active Part. The expression uses CATIA syntax, with "
                    "parameter paths in backticks, e.g. "
                    "\"`PartBody\\\\Pad.1\\\\FirstLimit\\\\Length` * 2\" or "
                    "\"Thickness + 5mm\". If a relation with the same name "
                    "exists it is modified in place."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Formula (relation) name"},
                        "target_parameter": {
                            "type": "string",
                            "description": "Parameter that receives the result (name or full path from catia_get_parameters)",
                        },
                        "expression": {"type": "string", "description": "Formula body in CATIA syntax"},
                        "comment": {"type": "string", "description": "Optional comment"},
                    },
                    "required": ["name", "target_parameter", "expression"],
                },
            },
            {
                "name": "catia_list_relations",
                "description": (
                    "List the relations of the active Part (formulas, design "
                    "tables, rules, checks) with their bodies and comments. "
                    "Optional substring filter."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filter": {"type": "string", "description": "Case-insensitive substring filter"},
                    },
                },
            },
            {
                "name": "catia_delete_relation",
                "description": "Delete a relation (formula, design table, rule, check) of the active Part by name.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Relation name (see catia_list_relations)"},
                    },
                    "required": ["name"],
                },
            },
            {
                "name": "catia_create_design_table",
                "description": (
                    "Create a design table from an Excel or text sheet "
                    "(absolute path on the CATIA machine) and associate its "
                    "columns to parameters of the active Part by name. The "
                    "sheet's column headers must match the parameter names "
                    "given in 'parameters'."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Design table name"},
                        "file_path": {"type": "string", "description": "Absolute path to the .xls/.xlsx/.txt sheet on the CATIA machine"},
                        "parameters": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Parameter names to associate (one per sheet column with the same header)",
                        },
                        "copy_mode": {
                            "type": "boolean",
                            "description": "Copy the sheet data into the part (default true) rather than linking the file",
                        },
                        "comment": {"type": "string", "description": "Optional comment"},
                    },
                    "required": ["name", "file_path", "parameters"],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_create_parameter":
                return self._create_parameter(arguments)
            case "catia_set_formula":
                return self._set_formula(arguments)
            case "catia_list_relations":
                return self._list_relations(arguments.get("filter"))
            case "catia_delete_relation":
                return self._delete_relation(arguments["name"])
            case "catia_create_design_table":
                return self._create_design_table(arguments)
            case _:
                raise ValueError(f"Unknown knowledge tool: {tool_name}")

    # ------------------------------------------------------------------
    def _find_parameter(self, params: Any, name: str) -> Any | None:
        try:
            return params.Item(name)
        except Exception:
            return None

    def _create_parameter(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        params = part.Parameters
        name, ptype, value = args["name"], args["type"], args["value"]

        existing = self._find_parameter(params, name)
        if existing is not None:
            self._assign(existing, ptype, value)
            part.Update()
            return f"Parameter '{name}' already existed; value set to {value}{_UNITS.get(ptype, '')}."

        if ptype == "length":
            param = params.CreateDimension(name, "LENGTH", 0)
            param.ValuateFromString(f"{float(value)}mm")
        elif ptype == "angle":
            param = params.CreateDimension(name, "ANGLE", 0)
            param.ValuateFromString(f"{float(value)}deg")
        elif ptype == "real":
            param = params.CreateReal(name, float(value))
        elif ptype == "integer":
            param = params.CreateInteger(name, int(value))
        elif ptype == "string":
            param = params.CreateString(name, str(value))
        elif ptype == "boolean":
            param = params.CreateBoolean(name, bool(value))
        else:
            raise ValueError(f"Unknown parameter type '{ptype}'")
        part.Update()
        return f"Parameter '{param.Name}' ({ptype}) created with value {value}{_UNITS.get(ptype, '')}."

    @staticmethod
    def _assign(param: Any, ptype: str, value: Any) -> None:
        if ptype in _UNITS:
            param.ValuateFromString(f"{float(value)}{_UNITS[ptype]}")
        elif ptype == "integer":
            param.Value = int(value)
        elif ptype == "real":
            param.Value = float(value)
        elif ptype == "boolean":
            param.Value = bool(value)
        else:
            param.Value = str(value)

    def _set_formula(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        params = part.Parameters
        target = self._find_parameter(params, args["target_parameter"])
        if target is None:
            raise RuntimeError(
                f"No parameter '{args['target_parameter']}' on the active part. "
                "Use catia_get_parameters to find the exact name or path."
            )
        relations = part.Relations
        name = args["name"]
        comment = args.get("comment") or ""
        expression = args["expression"]
        existing = None
        try:
            existing = relations.Item(name)
        except Exception:
            pass
        if existing is not None:
            existing.Modify(expression)
            part.Update()
            return f"Formula '{name}' updated: {expression}"
        formula = relations.CreateFormula(name, comment, target, expression)
        part.Update()
        return f"Formula '{formula.Name}' created on '{args['target_parameter']}': {expression}"

    def _list_relations(self, name_filter: str | None) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        relations = part.Relations
        needle = (name_filter or "").lower()
        rows = []
        for i in range(1, relations.Count + 1):
            rel = relations.Item(i)
            row: dict[str, Any] = {"index": i, "name": str(rel.Name)}
            for attr, key in (("Value", "body"), ("Comment", "comment")):
                try:
                    v = getattr(rel, attr)
                    if v not in (None, ""):
                        row[key] = str(v)
                except Exception:
                    pass
            if needle and needle not in json.dumps(row).lower():
                continue
            rows.append(row)
        if not rows:
            return "No relations" + (f" matching '{name_filter}'" if name_filter else "") + " on the active part."
        return json.dumps(rows, indent=2, ensure_ascii=False)

    def _delete_relation(self, name: str) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        relations = part.Relations
        try:
            relations.Item(name)
        except Exception:
            raise RuntimeError(f"No relation named '{name}'. See catia_list_relations.")
        relations.Remove(name)
        part.Update()
        return f"Relation '{name}' deleted."

    def _create_design_table(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part = self.conn.get_active_part()
        params = part.Parameters
        names = list(args["parameters"])
        missing = [n for n in names if self._find_parameter(params, n) is None]
        if missing:
            raise RuntimeError(
                f"Unknown parameter(s): {', '.join(missing)}. Create them first "
                "with catia_create_parameter."
            )
        table = part.Relations.CreateDesignTable(
            args["name"], args.get("comment") or "", bool(args.get("copy_mode", True)), args["file_path"]
        )
        for n in names:
            table.AddAssociation(params.Item(n), n)
        part.Update()
        return (
            f"Design table '{table.Name}' created from '{args['file_path']}' with "
            f"{len(names)} association(s): {', '.join(names)}."
        )
