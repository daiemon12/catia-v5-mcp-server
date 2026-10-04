"""Drafting (Drawing) tools for CATIA V5.

Built from field-validated automation probes run on CATIA V5R20 by
community tester ESE3X: Drawing document creation, generative view
creation (Sheets / Views.Add / GenerativeBehavior / DefineFrontView /
Update) and view positioning are confirmed working through COM.

The module is intentionally minimal while the full drafting field
campaign is in progress; projection/section views, dimensions and title
blocks are planned follow-ups.
"""

from __future__ import annotations

from typing import Any

from catia_mcp.connection import CATIAConnection

# DefineFrontView takes the two sheet-plane axis vectors expressed in the
# 3D part's coordinate system.
_PLANE_VECTORS = {
    "xy": (1, 0, 0, 0, 1, 0),
    "yz": (0, 1, 0, 0, 0, 1),
    "zx": (0, 0, 1, 1, 0, 0),
}


class DraftingTools:
    """Tools for CATIA V5 Drawing documents (generative drafting)."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_new_drawing",
                "description": (
                    "Create a new empty Drawing document (CATDrawing) for "
                    "generative drafting. The drawing becomes the active "
                    "document; the source Part stays open and is referenced "
                    "by catia_drawing_add_view."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_drawing_add_view",
                "description": (
                    "Add a generative front view of an open Part to the "
                    "active Drawing's active sheet, projected on the chosen "
                    "plane, then update it. Create the drawing first with "
                    "catia_new_drawing. Experimental: field-validated on "
                    "V5R20 for front views; projection/section views are "
                    "planned."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "part_name": {
                            "type": "string",
                            "description": (
                                "Open Part document to represent (e.g. "
                                "'Part1.CATPart'). Defaults to the only "
                                "open Part when unambiguous."
                            ),
                        },
                        "plane": {
                            "type": "string",
                            "enum": ["xy", "yz", "zx"],
                            "description": "Projection plane (default xy)",
                        },
                        "x": {
                            "type": "number",
                            "description": "View X position on the sheet in mm (default 300)",
                        },
                        "y": {
                            "type": "number",
                            "description": "View Y position on the sheet in mm (default 150)",
                        },
                        "name": {
                            "type": "string",
                            "description": "View name (default 'Front View')",
                        },
                    },
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_new_drawing":
                return self._new_drawing()
            case "catia_drawing_add_view":
                return self._add_view(arguments)
            case _:
                raise ValueError(f"Unknown drafting tool: {tool_name}")

    def _new_drawing(self) -> str:
        self.conn.ensure_connected()
        drawing = self.conn.documents.Add("Drawing")
        sheet = drawing.Sheets.ActiveSheet
        return (
            f"Drawing created: '{drawing.Name}' (active sheet '{sheet.Name}', "
            f"{drawing.Sheets.Count} sheet(s)). Use catia_drawing_add_view "
            "to project a part onto it."
        )

    def _find_part_document(self, part_name: str | None) -> Any:
        docs = self.conn.documents
        open_parts = []
        for i in range(1, docs.Count + 1):
            doc = docs.Item(i)
            try:
                doc_name = str(doc.Name)
            except Exception:
                continue
            if doc_name.lower().endswith(".catpart"):
                open_parts.append(doc)
                if part_name and doc_name == part_name:
                    return doc

        if part_name:
            names = ", ".join(str(d.Name) for d in open_parts) or "none"
            raise RuntimeError(
                f"No open Part named '{part_name}'. Open parts: {names}."
            )
        if len(open_parts) == 1:
            return open_parts[0]
        names = ", ".join(str(d.Name) for d in open_parts) or "none"
        raise RuntimeError(
            "Pass 'part_name' to pick the part to project. "
            f"Open parts: {names}."
        )

    def _find_active_drawing(self) -> Any:
        app = self.conn.app
        try:
            active = app.ActiveDocument
            if str(active.Name).lower().endswith(".catdrawing"):
                return active
        except Exception:
            pass
        docs = self.conn.documents
        drawings = []
        for i in range(1, docs.Count + 1):
            doc = docs.Item(i)
            try:
                if str(doc.Name).lower().endswith(".catdrawing"):
                    drawings.append(doc)
            except Exception:
                continue
        if len(drawings) == 1:
            return drawings[0]
        raise RuntimeError(
            "No active Drawing document. Run catia_new_drawing first."
        )

    def _add_view(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        part_doc = self._find_part_document(args.get("part_name"))
        drawing = self._find_active_drawing()

        plane = (args.get("plane") or "xy").lower()
        if plane not in _PLANE_VECTORS:
            raise ValueError(f"Unknown plane '{plane}'. Use 'xy', 'yz', or 'zx'.")
        vx1, vy1, vz1, vx2, vy2, vz2 = _PLANE_VECTORS[plane]

        sheet = drawing.Sheets.ActiveSheet
        view = sheet.Views.Add(args.get("name") or "Front View")

        gb = view.GenerativeBehavior
        gb.Document = part_doc
        gb.DefineFrontView(vx1, vy1, vz1, vx2, vy2, vz2)

        view.x = args.get("x", 300)
        view.y = args.get("y", 150)
        gb.Update()

        self.conn.refresh_display()
        return (
            f"View '{view.Name}' of '{part_doc.Name}' added to sheet "
            f"'{sheet.Name}' ({plane.upper()} projection) and updated."
        )
