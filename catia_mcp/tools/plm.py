"""PLM tools: 3DEXPERIENCE database search/open, PLM attributes, product tree.

Database search and open, and PLM attributes, exist only on 3DEXPERIENCE.
The product tree works on both platforms (V5 Products recursion,
3DEXPERIENCE occurrence recursion).
"""

from __future__ import annotations

import json
from typing import Any

from catia_mcp.automation import com_name, iter_items, safe_get
from catia_mcp.connection import PLATFORM_3DX, CATIAConnection
from catia_mcp.errors import InvalidArgument
from catia_mcp.plm import STANDARD_ATTRIBUTES, PLMSession

_TYPE_HELP = (
    "Database type: 'VPMReference' (Physical Product / 3D Part, default), "
    "'3DShape', 'Drawing', or another type name of your data model"
)


class PLMTools:
    """3DEXPERIENCE PLM database tools plus a cross-platform product tree."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self.plm = PLMSession(connection)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_search_database",
                "description": (
                    "3DEXPERIENCE only: search the 3DSpace database by title (V_Name) "
                    "or another attribute; '*' works as a wildcard. Returns title, "
                    "name (PLM_ExternalID), revision, maturity, owner. Read-only."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Value to match, e.g. 'Bracket*'"},
                        "type": {"type": "string", "description": _TYPE_HELP},
                        "attribute": {
                            "type": "string",
                            "description": "Attribute to match (default 'V_Name' = title; 'PLM_ExternalID' = name)",
                        },
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "description": "Maximum rows returned (default 25)",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "catia_open_from_database",
                "description": (
                    "3DEXPERIENCE only: open an object from the 3DSpace database in a new "
                    "editor (search + PLMOpen). Refuses to guess when several objects "
                    "match: pass 'revision' or the 1-based 'index' from "
                    "catia_search_database."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title (V_Name) or value of 'attribute'"},
                        "type": {"type": "string", "description": _TYPE_HELP},
                        "attribute": {
                            "type": "string",
                            "description": "Attribute to match (default 'V_Name')",
                        },
                        "revision": {"type": "string", "description": "Optional revision to pick, e.g. 'A.1'"},
                        "index": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "1-based result index when several objects match",
                        },
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "catia_get_plm_attributes",
                "description": (
                    "3DEXPERIENCE only: read PLM attributes (title V_Name, name "
                    "PLM_ExternalID, revision, maturity 'current', description, owner, "
                    "...) of the object shown in the active editor."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Attribute names to read (default: the standard set)",
                        },
                    },
                },
            },
            {
                "name": "catia_set_plm_attributes",
                "description": (
                    "3DEXPERIENCE only: set PLM attributes (e.g. V_Name title, "
                    "V_description, custom attributes) of the object shown in the active "
                    "editor. Changes stay in session until catia_save_document; the data "
                    "model and your role decide which attributes are writable."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "attributes": {
                            "type": "object",
                            "additionalProperties": {"type": ["string", "number", "boolean"]},
                            "description": "Attribute name -> value, e.g. {\"V_description\": \"Rev B bracket\"}",
                        },
                    },
                    "required": ["attributes"],
                },
            },
            {
                "name": "catia_get_product_tree",
                "description": (
                    "Return the product structure of the active product as a tree: V5 "
                    "components (name, part number), 3DEXPERIENCE occurrences (instance "
                    "name, reference title, revision, leaf or sub-assembly)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "max_depth": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "description": "Maximum depth (default 10)",
                        },
                    },
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_search_database":
                return self._search(arguments)
            case "catia_open_from_database":
                return self._open(arguments)
            case "catia_get_plm_attributes":
                return self._get_attributes(arguments.get("names"))
            case "catia_set_plm_attributes":
                return self._set_attributes(arguments["attributes"])
            case "catia_get_product_tree":
                return self._product_tree(int(arguments.get("max_depth", 10)))
            case _:
                raise ValueError(f"Unknown PLM tool: {tool_name}")

    def _search(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        self.conn.require_platform(PLATFORM_3DX, "catia_search_database")
        base_type = args.get("type") or "VPMReference"
        attribute = args.get("attribute") or "V_Name"
        limit = int(args.get("max_results", 25))
        entities = self.plm.search(args["query"], base_type, attribute)
        rows = [self.plm.describe(e, i) for i, e in enumerate(entities[:limit], start=1)]
        return json.dumps(
            {
                "query": args["query"],
                "type": base_type,
                "attribute": attribute,
                "total": len(entities),
                "returned": len(rows),
                "results": rows,
            },
            indent=2,
            ensure_ascii=False,
        )

    def _open(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        self.conn.require_platform(PLATFORM_3DX, "catia_open_from_database")
        base_type = args.get("type") or "VPMReference"
        attribute = args.get("attribute") or "V_Name"
        extra = {"revision": args["revision"]} if args.get("revision") else None
        entities = self.plm.search(args["title"], base_type, attribute, extra)
        description = f"{base_type} with {attribute}='{args['title']}'" + (
            f" revision {args['revision']}" if args.get("revision") else ""
        )
        entity = self.plm.pick_one(entities, description, args.get("index"))
        summary = self.plm.describe(entity)
        self.plm.open_entity(entity)
        obj = self.conn.active_object()
        return (
            f"Opened {self.conn.classify(obj)} '{self.plm.title_of(obj)}' "
            f"({', '.join(f'{k}={v}' for k, v in summary.items())}) in a new editor."
        )

    def _get_attributes(self, names: list[str] | None) -> str:
        self.conn.ensure_connected()
        self.conn.require_platform(PLATFORM_3DX, "catia_get_plm_attributes")
        plm_object = self.plm.plm_object_of_active()
        wanted = list(names) if names else list(STANDARD_ATTRIBUTES)
        values = self.plm.attributes(plm_object, wanted)
        missing = [n for n in wanted if n not in values]
        result: dict[str, Any] = {"attributes": values}
        if missing:
            result["unavailable"] = missing
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    def _set_attributes(self, attributes: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        self.conn.require_platform(PLATFORM_3DX, "catia_set_plm_attributes")
        if not attributes:
            raise InvalidArgument("attributes must name at least one attribute.")
        plm_object = self.plm.plm_object_of_active()
        applied, failed = {}, {}
        for name, value in attributes.items():
            try:
                plm_object.SetAttributeValue(name, value)
                applied[name] = self.plm.attribute(plm_object, name)
            except Exception as e:
                failed[name] = str(e)
        result: dict[str, Any] = {"applied": applied, "saved": False}
        if failed:
            result["failed"] = failed
        if not applied:
            raise RuntimeError(
                "No attribute could be set: "
                + "; ".join(f"{k}: {v}" for k, v in failed.items())
                + ". The attribute may be read-only for your role, or not part of this type."
            )
        result["note"] = "Changes are in session only until catia_save_document."
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    def _product_tree(self, max_depth: int) -> str:
        self.conn.ensure_connected()
        if self.conn.is_3dx:
            root = self.conn.root_occurrence()
            reference = self.plm.reference_of(root)
            tree = {
                "title": self.plm.attribute(reference, "V_Name") if reference is not None else None,
                "children": self._occurrence_children(root, 1, max_depth),
            }
            return json.dumps(tree, indent=2, ensure_ascii=False, default=str)
        product = self.conn.get_active_product()
        tree = {
            "name": com_name(product),
            "part_number": str(safe_get(product, "PartNumber", "")),
            "children": self._product_children(product, 1, max_depth),
        }
        return json.dumps(tree, indent=2, ensure_ascii=False)

    def _occurrence_children(self, occurrence: Any, depth: int, max_depth: int) -> list[dict[str, Any]]:
        rows = []
        for child in self.plm.child_occurrences(occurrence):
            instance = safe_get(child, "InstanceOccurrenceOf")
            reference = safe_get(instance, "ReferenceInstanceOf") if instance is not None else None
            row: dict[str, Any] = {"instance": self.plm.occurrence_name(child)}
            if reference is not None:
                row.update(self.plm.attributes(reference, ("V_Name", "PLM_ExternalID", "revision", "current")))
            grandchildren = self.plm.child_occurrences(child)
            row["kind"] = "sub-assembly" if grandchildren else "part"
            if grandchildren and depth < max_depth:
                row["children"] = self._occurrence_children(child, depth + 1, max_depth)
            elif grandchildren:
                row["truncated"] = True
            rows.append(row)
        return rows

    def _product_children(self, product: Any, depth: int, max_depth: int) -> list[dict[str, Any]]:
        rows = []
        try:
            children = list(iter_items(product.Products))
        except Exception:
            return rows
        for child in children:
            row: dict[str, Any] = {
                "name": com_name(child),
                "part_number": str(safe_get(child, "PartNumber", "")),
            }
            try:
                count = int(child.Products.Count)
            except Exception:
                count = 0
            if count and depth < max_depth:
                row["children"] = self._product_children(child, depth + 1, max_depth)
            elif count:
                row["truncated"] = True
            rows.append(row)
        return rows
