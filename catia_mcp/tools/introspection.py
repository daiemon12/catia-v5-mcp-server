"""API discovery tools: inspect the live automation API, run opt-in scripts.

CATIA automation signatures and enum values drift between releases, and the
3DEXPERIENCE API is documented only in each installation's
DSYAutomation.chm. catia_inspect_api reads the type information of live
objects (read-only), so an agent can find the exact member names,
parameters and enum values of the user's CATIA before calling them.

catia_run_script runs VBScript inside CATIA to bridge gaps no tool covers.
It is disabled unless the server was started with --allow-scripts (or
CATIA_MCP_ALLOW_SCRIPTS=1), because a script can do anything the user can.
"""

from __future__ import annotations

import json
import re
from typing import Any

from catia_mcp.automation import evaluate, get_member
from catia_mcp.connection import CATIAConnection
from catia_mcp.errors import InvalidArgument, ObjectNotFound, PermissionDenied
from catia_mcp.introspect import describe_members, find_enum, list_enums, type_name

# Getter-like methods allowed in an inspection path; no other call is made.
_ALLOWED_CALLS = {
    "item", "getitem", "getservice", "getsessionservice", "getworkbench",
    "gettechnologicalobject", "referencerootoccurrenceof", "referenceinstanceof",
    "instanceoccurrenceof",
}
_SEGMENT = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)(?:\((?:(-?\d+)|"([^"]*)")?\))?')
_ROOTS = ("app", "editor", "document", "part", "product", "selection", "window")


def _parse_path(path: str) -> list[tuple[str, bool, Any]]:
    segments: list[tuple[str, bool, Any]] = []
    pos = 0
    text = path.strip()
    while pos < len(text):
        match = _SEGMENT.match(text, pos)
        if not match:
            raise InvalidArgument(f"Cannot parse inspection path at: {text[pos:]!r}")
        name, number, string = match.groups()
        called = match.group(0).endswith(")")
        arg = int(number) if number is not None else string
        segments.append((name, called, arg))
        pos = match.end()
        if pos < len(text):
            if text[pos] != ".":
                raise InvalidArgument(f"Expected '.' at: {text[pos:]!r}")
            pos += 1
    if not segments:
        raise InvalidArgument("Empty inspection path.")
    return segments


def _jsonable(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)) and depth < 3:
        return [_jsonable(v, depth + 1) for v in value]
    if hasattr(value, "_oleobj_"):
        return f"<COM object {type_name(value) or 'unknown type'}>"
    return str(value)


class IntrospectionTools:
    """Read-only API inspection and opt-in script execution."""

    def __init__(self, connection: CATIAConnection, allow_scripts: bool = False) -> None:
        self.conn = connection
        self.allow_scripts = allow_scripts

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_inspect_api",
                "description": (
                    "Read-only discovery of the live CATIA automation API: resolve an "
                    "object path and list its properties and methods (with parameter "
                    "names and directions) from the installation's type library, and "
                    "read enum values. Use it when a tool reports "
                    "UNSUPPORTED_CAPABILITY or before scripting. Path roots: app, "
                    "editor (3DEXPERIENCE), document, part, product, selection, window; "
                    "segments are properties or the getters Item(n|\"name\"), "
                    "GetItem(\"X\"), GetService(\"X\"), GetSessionService(\"X\"), "
                    "GetWorkbench(\"X\"). Examples: 'part.ShapeFactory', "
                    "'editor.GetService(\"MeasurableService\")', "
                    "'app.ActiveEditor.ActiveObject'."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Object path, e.g. 'part.HybridShapeFactory'"},
                        "filter": {
                            "type": "string",
                            "description": "Case-insensitive substring filter on member names",
                        },
                        "enum": {
                            "type": "string",
                            "description": "Enum to read from the object's type library, e.g. 'CATMeasurableType'",
                        },
                        "list_enums": {
                            "type": "boolean",
                            "description": "List the enum names declared in the object's type library",
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "catia_run_script",
                "description": (
                    "Run a VBScript function inside CATIA through "
                    "SystemService.Evaluate and return its result. Disabled unless the "
                    "server was started with --allow-scripts (or "
                    "CATIA_MCP_ALLOW_SCRIPTS=1): a script runs with the user's full "
                    "rights in CATIA and on the machine. The global CATIA object is "
                    "available inside the script. Model changes are not verified."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "VBScript source defining the function to call",
                        },
                        "function": {
                            "type": "string",
                            "description": "Name of the function to call (default 'CATMain')",
                        },
                        "args": {
                            "type": "array",
                            "items": {"type": ["string", "number", "boolean"]},
                            "description": "Arguments passed to the function",
                        },
                    },
                    "required": ["code"],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_inspect_api":
                return self._inspect(arguments)
            case "catia_run_script":
                return self._run_script(arguments)
            case _:
                raise ValueError(f"Unknown introspection tool: {tool_name}")

    def _root(self, name: str) -> Any:
        key = name.lower()
        if key == "app":
            return self.conn.app
        if key == "editor":
            return self.conn.active_editor
        if key == "document":
            return self.conn.active_document
        if key == "part":
            return self.conn.get_active_part()
        if key == "product":
            return self.conn.get_active_product()
        if key == "selection":
            return self.conn.hso
        if key == "window":
            return self.conn.active_window
        raise InvalidArgument(f"Unknown path root '{name}'. Use one of: {', '.join(_ROOTS)}.")

    def _resolve(self, path: str) -> Any:
        segments = _parse_path(path)
        root_name, root_called, _ = segments[0]
        if root_called:
            raise InvalidArgument("The path root cannot be a call.")
        obj = self._root(root_name)
        walked = root_name
        for name, called, arg in segments[1:]:
            if called and name.lower() not in _ALLOWED_CALLS:
                raise InvalidArgument(
                    f"'{name}(...)' is not an allowed getter. Allowed calls: Item, GetItem, "
                    "GetService, GetSessionService, GetWorkbench, GetTechnologicalObject, "
                    "ReferenceRootOccurrenceOf, ReferenceInstanceOf, InstanceOccurrenceOf."
                )
            try:
                if called and arg is not None:
                    obj = getattr(obj, name)(arg)
                else:
                    obj = get_member(obj, name)
            except AttributeError:
                raise ObjectNotFound(f"'{walked}' has no member '{name}'.")
            except Exception as e:
                raise ObjectNotFound(f"Reading '{walked}.{name}' failed: {e}")
            walked += f".{name}"
        return obj

    def _inspect(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        obj = self._resolve(args["path"])
        result: dict[str, Any] = {"path": args["path"], "platform": self.conn.platform_label}
        if not hasattr(obj, "_oleobj_"):
            result["value"] = _jsonable(obj)
            return json.dumps(result, indent=2, ensure_ascii=False)
        result["type"] = type_name(obj)
        if args.get("enum"):
            values = find_enum([obj, self.conn.app], args["enum"])
            result["enum"] = {args["enum"]: values} if values else (
                f"Enum '{args['enum']}' not found in this object's type library."
            )
        if args.get("list_enums"):
            result["enums"] = list_enums([obj])
        if not args.get("enum") or args.get("filter"):
            members = describe_members(obj)
            needle = (args.get("filter") or "").lower()
            if needle:
                members = [m for m in members if needle in m["name"].lower()]
            result["members"] = members
        return json.dumps(result, indent=2, ensure_ascii=False)

    def _run_script(self, args: dict[str, Any]) -> str:
        if not self.allow_scripts:
            raise PermissionDenied(
                "catia_run_script is disabled. Restart the server with --allow-scripts "
                "(or set CATIA_MCP_ALLOW_SCRIPTS=1) to enable it; scripts run with your "
                "full rights in CATIA and on this machine."
            )
        self.conn.ensure_connected()
        function = args.get("function") or "CATMain"
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", function):
            raise InvalidArgument(f"Invalid function name {function!r}.")
        result = evaluate(self.conn.app, args["code"], function, list(args.get("args") or []))
        return json.dumps({"function": function, "result": _jsonable(result)}, indent=2, ensure_ascii=False)
