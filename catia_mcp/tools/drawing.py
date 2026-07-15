"""Drawing (CATDrawing) tools.

Generative 2D drafting: create a drawing, add generative views projected from an
existing 3D part (front/top/right/iso), projection views off a parent, section and
detail views, regenerate, and inspect the sheet structure. PDF export is handled by
catia_export (Document.ExportData), not duplicated here.

All COM access goes through the active Drawing document's DrawingRoot, never the
Application object (GetWorkbench/roots live on the Document). Method names and enum
values were taken from pycatia's drafting_interfaces source; expect to confirm the 3D
link and generative-update calls live on the target seat (see docs/PLAN.md).
"""

from __future__ import annotations

import os
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.paths import normalize_catia_path
from catia_mcp.tools._geometry import object_schema, result

# CatPaperSize / CatPaperOrientation / CatProjViewType (pycatia enumeration/enums.py).
PAPER_SIZES = {"letter": 0, "legal": 1, "A0": 2, "A1": 3, "A2": 4, "A3": 5, "A4": 6}
ORIENTATIONS = {"portrait": 0, "landscape": 1}
PROJECTION_TYPES = {"right": 0, "left": 1, "top": 2, "bottom": 3}

# Named base-view orientation -> (V1, V2): the two 3D vectors that DefineFrontView maps
# to the view's horizontal (X) and vertical (Y) axes. These are conventional mappings
# and may need adjustment per the part's own orientation / drafting standard (verified
# live). Isometric uses two vectors whose cross product is the (1,1,1) projection dir.
VIEW_ORIENTATIONS = {
    "front": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "back": ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "top": ((1.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
    "bottom": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "right": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
    "left": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
}
ISO_VECTORS = ((0.7071, 0.7071, 0.0), (-0.4082, 0.4082, 0.8165))


def _safe(getter: Any) -> Any:
    try:
        return getter()
    except Exception:
        return None


class DrawingTools:
    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    # ── tool definitions ────────────────────────────────────────────────
    def get_tool_definitions(self) -> list[dict[str, Any]]:
        paper = {"type": "string", "enum": list(PAPER_SIZES), "default": "A3"}
        orient = {"type": "string", "enum": list(ORIENTATIONS), "default": "landscape"}
        orientation_enum = {"type": "string", "enum": list(VIEW_ORIENTATIONS) + ["iso"]}
        return [
            self._d(
                "catia_new_drawing",
                "Create a new CATDrawing document and configure its active sheet.",
                {
                    "paper_size": paper,
                    "orientation": orient,
                    "scale": {"type": "number", "exclusiveMinimum": 0},
                },
            ),
            self._d(
                "catia_drawing_base_view",
                "Add a generative view projected from an open 3D part/product onto the "
                "active drawing sheet. orientation is one of front/back/top/bottom/left/"
                "right/iso.",
                {
                    "orientation": {**orientation_enum, "default": "front"},
                    "part_name": {
                        "type": "string",
                        "description": "Source document name, or 'active' for the most "
                        "recent open CATPart/CATProduct.",
                        "default": "active",
                    },
                    "name": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "scale": {"type": "number", "exclusiveMinimum": 0},
                },
            ),
            self._d(
                "catia_drawing_projection_view",
                "Add a projection view (right/left/top/bottom) off an existing parent "
                "view on the active sheet. Inherits the parent's scale and is offset in "
                "the projection direction unless x/y/scale are given.",
                {
                    "parent_view": {"type": "string"},
                    "direction": {"type": "string", "enum": list(PROJECTION_TYPES)},
                    "name": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "scale": {"type": "number", "exclusiveMinimum": 0},
                    "gap": {
                        "type": "number",
                        "default": 100,
                        "description": "Distance from the parent view (mm on sheet).",
                    },
                },
                ["parent_view", "direction"],
            ),
            self._d(
                "catia_drawing_section_view",
                "Add a section view cut by a profile polyline defined in the parent "
                "view's axis system.",
                {
                    "parent_view": {"type": "string"},
                    "profile": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4,
                        "description": "Flat sheet coords [x1,y1,x2,y2,...] of the "
                        "cutting polyline.",
                    },
                    "section_type": {
                        "type": "string",
                        "enum": ["SectionView", "SectionCut"],
                        "default": "SectionView",
                    },
                    "profile_type": {
                        "type": "string",
                        "enum": ["Offset", "Aligned"],
                        "default": "Offset",
                    },
                    "side": {"type": "integer", "enum": [0, 1], "default": 1},
                    "name": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "scale": {"type": "number", "exclusiveMinimum": 0},
                },
                ["parent_view", "profile"],
            ),
            self._d(
                "catia_drawing_detail_view",
                "Add a circular detail (blow-up) view of a region of a parent view.",
                {
                    "parent_view": {"type": "string"},
                    "center_x": {"type": "number"},
                    "center_y": {"type": "number"},
                    "radius": {"type": "number", "exclusiveMinimum": 0},
                    "name": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "scale": {"type": "number", "exclusiveMinimum": 0},
                },
                ["parent_view", "center_x", "center_y", "radius"],
            ),
            self._d(
                "catia_drawing_update",
                "Regenerate all generative views on the active sheet.",
                {},
            ),
            self._d(
                "catia_drawing_info",
                "List the active drawing's sheets and views (name, scale, position).",
                {},
            ),
            self._d(
                "catia_fill_drawing_bom",
                "Fill an existing CATDrawing bill-of-materials/specification table. "
                "Rows are matched by the first column's component name; the quantity "
                "column is filled with each row's quantity.",
                {
                    "drawing_path": {
                        "type": "string",
                        "description": "Optional full path to the CATDrawing to open before filling.",
                    },
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "quantity": {"type": "integer", "minimum": 0},
                            },
                            "required": ["name", "quantity"],
                        },
                        "minItems": 1,
                    },
                    "name_column": {"type": "integer", "minimum": 1, "default": 1},
                    "quantity_column": {"type": "integer", "minimum": 1, "default": 2},
                    "create_if_missing": {"type": "boolean", "default": True},
                    "x": {
                        "type": "number",
                        "default": 250,
                        "description": "Sheet X position for a newly created BOM table.",
                    },
                    "y": {
                        "type": "number",
                        "default": 180,
                        "description": "Sheet Y position for a newly created BOM table.",
                    },
                    "row_height": {"type": "number", "exclusiveMinimum": 0, "default": 8},
                    "name_column_width": {"type": "number", "exclusiveMinimum": 0, "default": 38},
                    "quantity_column_width": {"type": "number", "exclusiveMinimum": 0, "default": 24},
                    "name_header": {"type": "string", "default": "Наименование"},
                    "quantity_header": {"type": "string", "default": "Количество"},
                    "save": {"type": "boolean", "default": True},
                },
                ["rows"],
            ),
            self._d(
                "catia_drawing_from_part",
                "One-call drawing: new sheet + front/top/right + isometric views from an "
                "open 3D part, regenerated, with optional PDF export.",
                {
                    "part_name": {"type": "string", "default": "active"},
                    "paper_size": paper,
                    "orientation": orient,
                    "scale": {"type": "number", "exclusiveMinimum": 0},
                    "view_scale": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "default": 0.15,
                        "description": "Scale applied to each view so a large part fits "
                        "without the views overlapping.",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "If set, export the drawing to this PDF path.",
                    },
                },
            ),
        ]

    def _d(
        self, name: str, description: str, props: dict[str, Any], required: list[str] | None = None
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "inputSchema": object_schema(props, required),
        }

    # ── dispatch ────────────────────────────────────────────────────────
    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_new_drawing":
                return self._new_drawing(arguments)
            case "catia_drawing_base_view":
                return self._base_view(arguments)
            case "catia_drawing_projection_view":
                return self._projection_view(arguments)
            case "catia_drawing_section_view":
                return self._section_view(arguments)
            case "catia_drawing_detail_view":
                return self._detail_view(arguments)
            case "catia_drawing_update":
                return self._update(arguments)
            case "catia_drawing_info":
                return self._info(arguments)
            case "catia_fill_drawing_bom":
                return self._fill_bom(arguments)
            case "catia_drawing_from_part":
                return self._from_part(arguments)
            case _:
                raise ValueError(f"Unknown drawing tool: {tool_name}")

    # ── helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _try_rename(obj: Any, name: str | None) -> None:
        if not name:
            return
        try:
            obj.Name = name
        except Exception:
            pass

    def _root(self) -> Any:
        doc = self.conn.active_document
        try:
            return doc.DrawingRoot
        except Exception as exc:
            raise RuntimeError(
                "The active document is not a CATDrawing (no DrawingRoot). "
                "Create one with catia_new_drawing first."
            ) from exc

    def _active_sheet(self) -> Any:
        return self._root().Sheets.ActiveSheet

    def _open_drawing_if_needed(self, drawing_path: str | None) -> None:
        if not drawing_path:
            return
        self.conn.ensure_connected()
        docs = self.conn.documents
        drawing_path = normalize_catia_path(drawing_path)
        target = os.path.normcase(os.path.abspath(drawing_path))
        for index in range(1, docs.Count + 1):
            existing = docs.Item(index)
            full_name = getattr(existing, "FullName", "") or ""
            if full_name and os.path.normcase(os.path.abspath(full_name)) == target:
                try:
                    existing.Activate()
                except Exception:
                    pass
                return
        docs.Open(drawing_path)

    def _find_view(self, sheet: Any, name: str) -> Any:
        views = sheet.Views
        for i in range(1, views.Count + 1):
            view = views.Item(i)
            if getattr(view, "Name", None) == name:
                return view
        raise RuntimeError(f"View '{name}' was not found on the active sheet.")

    @staticmethod
    def _is_3d(doc: Any) -> bool:
        try:
            _ = doc.Part
            return True
        except Exception:
            try:
                _ = doc.Product
                return True
            except Exception:
                return False

    def _find_source_document(self, part_name: str | None) -> Any:
        docs = self.conn.documents
        if part_name and part_name != "active":
            for i in range(1, docs.Count + 1):
                doc = docs.Item(i)
                if getattr(doc, "Name", None) == part_name:
                    return doc
            raise RuntimeError(f"Source document '{part_name}' is not open in CATIA.")
        candidate = None
        for i in range(1, docs.Count + 1):
            doc = docs.Item(i)
            if self._is_3d(doc):
                candidate = doc  # keep the last (most recently added) 3D document
        if candidate is None:
            raise RuntimeError("No open CATPart/CATProduct to draw from.")
        return candidate

    def _add_view(self, sheet: Any, name: str | None, default: str) -> Any:
        view = sheet.Views.Add(name or default)
        self._try_rename(view, name)
        return view

    @staticmethod
    def _place(view: Any, args: dict[str, Any]) -> None:
        if "x" in args or "y" in args:
            try:
                if "x" in args:
                    view.x = args["x"]
                if "y" in args:
                    view.y = args["y"]
            except Exception:
                pass
        if args.get("scale"):
            try:
                view.Scale = args["scale"]
            except Exception:
                pass

    @staticmethod
    def _carry_link(view: Any, parent: Any) -> None:
        """Carry a parent view's 3D source onto a derived (projection/section/detail)
        view. Without it the derived view defines its relationship but generates no
        geometry (verified live: projection views came out empty until linked)."""
        try:
            view.GenerativeBehavior.Document = parent.GenerativeBehavior.Document
        except Exception:
            try:
                parent.GenerativeLinks.CopyLinksTo(view.GenerativeLinks)
            except Exception:
                pass

    @staticmethod
    def _update_view(view: Any) -> None:
        """Regenerate a single generative view. The exact update entry point differs
        across releases; try the view's generative behavior first, then the view."""
        gb = view.GenerativeBehavior
        for call in (lambda: gb.Update(), lambda: view.Update()):
            try:
                call()
                return
            except Exception:
                continue

    # ── tools ───────────────────────────────────────────────────────────
    def _new_drawing(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        doc = self.conn.documents.Add("Drawing")
        sheet = self._active_sheet()
        if args.get("paper_size") in PAPER_SIZES:
            try:
                sheet.PaperSize = PAPER_SIZES[args["paper_size"]]
            except Exception:
                pass
        if args.get("orientation") in ORIENTATIONS:
            try:
                sheet.Orientation = ORIENTATIONS[args["orientation"]]
            except Exception:
                pass
        if args.get("scale"):
            try:
                sheet.Scale = args["scale"]
            except Exception:
                pass
        self.conn.refresh_display()
        return result(
            document=doc.Name,
            sheet=sheet.Name,
            paper_size=args.get("paper_size"),
            orientation=args.get("orientation"),
            tool="catia_new_drawing",
        )

    def _base_view(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        orientation = args.get("orientation", "front")
        if orientation != "iso" and orientation not in VIEW_ORIENTATIONS:
            raise ValueError(f"Unknown orientation: {orientation}")
        source = self._find_source_document(args.get("part_name", "active"))
        sheet = self._active_sheet()
        view = self._add_view(sheet, args.get("name"), f"{orientation}_view")
        # Associate the view with the 3D document, then define its projection. The
        # GenerativeBehavior.Document property is the standard association ("which 3D
        # doc does this view draw"); GenerativeLinks.AddLink is a secondary mechanism
        # that fails with E_FAIL on this seat, so it is only a fallback.
        gb = view.GenerativeBehavior
        try:
            gb.Document = source
        except Exception:
            view.GenerativeLinks.AddLink(source)
        if orientation == "iso":
            (a, b) = ISO_VECTORS
            gb.DefineIsometricView(a[0], a[1], a[2], b[0], b[1], b[2])
        else:
            v1, v2 = VIEW_ORIENTATIONS[orientation]
            gb.DefineFrontView(v1[0], v1[1], v1[2], v2[0], v2[1], v2[2])
        self._place(view, args)
        self._update_view(view)
        self.conn.refresh_display()
        return result(
            view=view.Name,
            orientation=orientation,
            source=source.Name,
            tool="catia_drawing_base_view",
        )

    def _projection_view(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        direction = args["direction"]
        if direction not in PROJECTION_TYPES:
            raise ValueError(f"Unknown projection direction: {direction}")
        sheet = self._active_sheet()
        parent = self._find_view(sheet, args["parent_view"])
        view = self._add_view(sheet, args.get("name"), f"{direction}_view")
        gb = view.GenerativeBehavior
        # A projection view needs the same 3D source as its parent, else it defines the
        # projection relationship but generates no geometry.
        self._carry_link(view, parent)
        gb.DefineProjectionView(parent.GenerativeBehavior, PROJECTION_TYPES[direction])
        # Projection views do not inherit the parent's scale/position through the API
        # (they land at 0,0 / 1:1). Match the parent's scale and offset the view in the
        # projection direction so it lands next to its parent.
        parent_scale = _safe(lambda: parent.Scale) or 1.0
        px = _safe(lambda: parent.x) or 0.0
        py = _safe(lambda: parent.y) or 0.0
        gap = args.get("gap", 100.0)
        offsets = {"right": (gap, 0.0), "left": (-gap, 0.0), "top": (0.0, gap), "bottom": (0.0, -gap)}
        dx, dy = offsets[direction]
        try:
            view.Scale = args.get("scale", parent_scale)
            view.x = args.get("x", px + dx)
            view.y = args.get("y", py + dy)
        except Exception:
            pass
        self._update_view(view)
        self.conn.refresh_display()
        return result(
            view=view.Name,
            direction=direction,
            parent=args["parent_view"],
            scale=_safe(lambda: view.Scale),
            tool="catia_drawing_projection_view",
        )

    def _section_view(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        sheet = self._active_sheet()
        parent = self._find_view(sheet, args["parent_view"])
        view = self._add_view(sheet, args.get("name"), "section_view")
        self._carry_link(view, parent)
        gb = view.GenerativeBehavior
        profile = tuple(float(v) for v in args["profile"])
        section_type = args.get("section_type", "SectionView")
        profile_type = args.get("profile_type", "Offset")
        side = int(args.get("side", 1))
        try:
            gb.DefineSectionView(
                profile, section_type, profile_type, side, parent.GenerativeBehavior
            )
        except Exception:
            # The profile is a CATSafeArrayVariant; if a plain tuple is rejected, retry
            # with an explicit VARIANT SAFEARRAY of doubles.
            import pythoncom
            from win32com.client import VARIANT

            arr = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(profile))
            gb.DefineSectionView(
                arr, section_type, profile_type, side, parent.GenerativeBehavior
            )
        if not args.get("scale"):
            args = {**args, "scale": _safe(lambda: parent.Scale)}
        self._place(view, args)
        self._update_view(view)
        self.conn.refresh_display()
        return result(
            view=view.Name,
            parent=args["parent_view"],
            section_type=section_type,
            tool="catia_drawing_section_view",
        )

    def _detail_view(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        sheet = self._active_sheet()
        parent = self._find_view(sheet, args["parent_view"])
        view = self._add_view(sheet, args.get("name"), "detail_view")
        self._carry_link(view, parent)
        gb = view.GenerativeBehavior
        gb.DefineCircularDetailView(
            float(args["center_x"]),
            float(args["center_y"]),
            float(args["radius"]),
            parent.GenerativeBehavior,
        )
        self._place(view, args)
        self._update_view(view)
        self.conn.refresh_display()
        return result(
            view=view.Name, parent=args["parent_view"], tool="catia_drawing_detail_view"
        )

    def _update(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        sheet = self._active_sheet()
        views = sheet.Views
        updated: list[str] = []
        for i in range(1, views.Count + 1):
            view = views.Item(i)
            before = updated[:]
            self._update_view(view)
            # _update_view swallows errors; record the name regardless so callers see
            # which views were attempted.
            if updated == before:
                updated.append(getattr(view, "Name", f"View.{i}"))
        try:
            self.conn.active_document.Update()
        except Exception:
            pass
        self.conn.refresh_display()
        return result(updated_views=updated, tool="catia_drawing_update")

    def _info(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        root = self._root()
        sheets = root.Sheets
        sheets_out: list[dict[str, Any]] = []
        for i in range(1, sheets.Count + 1):
            sheet = sheets.Item(i)
            views_out: list[dict[str, Any]] = []
            views = sheet.Views
            for j in range(1, views.Count + 1):
                view = views.Item(j)
                views_out.append(
                    {
                        "name": getattr(view, "Name", f"View.{j}"),
                        "scale": _safe(lambda v=view: v.Scale),
                        "x": _safe(lambda v=view: v.x),
                        "y": _safe(lambda v=view: v.y),
                        "tables": self._table_diagnostics(view),
                        "texts": self._text_diagnostics(view),
                    }
                )
            sheets_out.append(
                {
                    "name": getattr(sheet, "Name", f"Sheet.{i}"),
                    "paper_size": _safe(lambda s=sheet: s.PaperSize),
                    "orientation": _safe(lambda s=sheet: s.Orientation),
                    "scale": _safe(lambda s=sheet: s.Scale),
                    "views": views_out,
                }
            )
        return result(
            document=self.conn.active_document.Name,
            sheets=sheets_out,
            tool="catia_drawing_info",
        )

    @staticmethod
    def _cell_text(table: Any, row: int, column: int) -> str:
        for getter in (
            lambda: table.GetCellString(row, column),
            lambda: table.GetCellObject(row, column).Text,
        ):
            try:
                value = getter()
                return "" if value is None else str(value)
            except Exception:
                continue
        return ""

    @staticmethod
    def _set_cell_text(table: Any, row: int, column: int, text: str) -> None:
        for setter in (
            lambda: table.SetCellString(row, column, text),
            lambda: setattr(table.GetCellObject(row, column), "Text", text),
        ):
            try:
                setter()
                return
            except Exception:
                continue
        raise RuntimeError(f"Could not write drawing table cell ({row}, {column}).")

    @staticmethod
    def _table_size(table: Any) -> tuple[int, int]:
        rows = _safe(lambda: table.NumberOfRows) or _safe(lambda: table.Rows.Count) or 0
        columns = _safe(lambda: table.NumberOfColumns) or _safe(lambda: table.Columns.Count) or 0
        return int(rows or 0), int(columns or 0)

    def _table_diagnostics(self, view: Any) -> list[dict[str, Any]]:
        tables = _safe(lambda: view.Tables)
        if tables is None:
            return []
        out: list[dict[str, Any]] = []
        for i in range(1, tables.Count + 1):
            table = tables.Item(i)
            row_count, column_count = self._table_size(table)
            sample: list[list[str]] = []
            for row in range(1, min(row_count, 5) + 1):
                sample.append([
                    self._cell_text(table, row, column)
                    for column in range(1, min(column_count, 4) + 1)
                ])
            out.append(
                {
                    "index": i,
                    "name": getattr(table, "Name", f"Table.{i}"),
                    "rows": row_count,
                    "columns": column_count,
                    "sample": sample,
                }
            )
        return out

    @staticmethod
    def _text_diagnostics(view: Any) -> list[dict[str, Any]]:
        texts = _safe(lambda: view.Texts)
        if texts is None:
            return []
        out: list[dict[str, Any]] = []
        for i in range(1, min(texts.Count, 20) + 1):
            text = texts.Item(i)
            out.append(
                {
                    "index": i,
                    "name": getattr(text, "Name", f"Text.{i}"),
                    "text": _safe(lambda t=text: t.Text),
                    "x": _safe(lambda t=text: t.x),
                    "y": _safe(lambda t=text: t.y),
                }
            )
        return out

    def _find_bom_table(self, expected_names: set[str]) -> tuple[Any, dict[str, Any]]:
        root = self._root()
        sheets = root.Sheets
        diagnostics: list[dict[str, Any]] = []
        best_table = None
        best_score = -1
        best_context: dict[str, Any] = {}
        for sheet_index in range(1, sheets.Count + 1):
            sheet = sheets.Item(sheet_index)
            sheet_diag: dict[str, Any] = {
                "name": getattr(sheet, "Name", f"Sheet.{sheet_index}"),
                "views": [],
            }
            views = sheet.Views
            for view_index in range(1, views.Count + 1):
                view = views.Item(view_index)
                view_diag = {
                    "name": getattr(view, "Name", f"View.{view_index}"),
                    "tables": self._table_diagnostics(view),
                    "texts": self._text_diagnostics(view),
                }
                sheet_diag["views"].append(view_diag)
                tables = _safe(lambda v=view: v.Tables)
                if tables is None:
                    continue
                for table_index in range(1, tables.Count + 1):
                    table = tables.Item(table_index)
                    row_count, column_count = self._table_size(table)
                    if row_count <= 0 or column_count <= 0:
                        continue
                    score = 0
                    for row in range(1, row_count + 1):
                        for column in range(1, column_count + 1):
                            if self._cell_text(table, row, column).strip() in expected_names:
                                score += 1
                    if score > best_score:
                        best_table = table
                        best_score = score
                        best_context = {
                            "sheet": sheet_diag["name"],
                            "view": view_diag["name"],
                            "table_index": table_index,
                            "rows": row_count,
                            "columns": column_count,
                            "matched_names": score,
                        }
            diagnostics.append(sheet_diag)
        if best_table is None or best_score <= 0:
            raise RuntimeError(
                "No DrawingTable containing the requested component names was found. "
                + result(tool="catia_fill_drawing_bom", diagnostics=diagnostics)
            )
        return best_table, best_context

    def _target_table_view(self) -> Any:
        sheet = self._active_sheet()
        views = sheet.Views
        fallback = None
        for index in range(1, views.Count + 1):
            view = views.Item(index)
            name = getattr(view, "Name", "")
            if fallback is None:
                fallback = view
            if str(name).lower() != "background view":
                return view
        if fallback is None:
            raise RuntimeError("The active drawing sheet has no views for placing a BOM table.")
        return fallback

    @staticmethod
    def _set_table_column_width(table: Any, column: int, width: float) -> None:
        for setter in (
            lambda: table.SetColumnSize(column, width),
            lambda: table.SetColumnWidth(column, width),
        ):
            try:
                setter()
                return
            except Exception:
                continue

    @staticmethod
    def _set_table_row_height(table: Any, row: int, height: float) -> None:
        for setter in (
            lambda: table.SetRowSize(row, height),
            lambda: table.SetRowHeight(row, height),
        ):
            try:
                setter()
                return
            except Exception:
                continue

    def _create_bom_table(
        self, args: dict[str, Any], rows: list[dict[str, Any]]
    ) -> tuple[Any, dict[str, Any]]:
        view = self._target_table_view()
        tables = view.Tables
        row_height = float(args.get("row_height", 8))
        name_width = float(args.get("name_column_width", 38))
        quantity_width = float(args.get("quantity_column_width", 24))
        x = float(args.get("x", 250))
        y = float(args.get("y", 180))
        table = tables.Add(x, y, len(rows) + 1, 2, row_height, name_width)
        self._set_table_column_width(table, 1, name_width)
        self._set_table_column_width(table, 2, quantity_width)
        for row_index in range(1, len(rows) + 2):
            self._set_table_row_height(table, row_index, row_height)
        self._set_cell_text(table, 1, 1, str(args.get("name_header", "Наименование")))
        self._set_cell_text(table, 1, 2, str(args.get("quantity_header", "Количество")))
        for index, row in enumerate(rows, start=2):
            self._set_cell_text(table, index, 1, str(row["name"]))
            self._set_cell_text(table, index, 2, str(int(row["quantity"])))
        return table, {
            "sheet": self._active_sheet().Name,
            "view": getattr(view, "Name", "unknown"),
            "table_index": _safe(lambda: view.Tables.Count),
            "rows": len(rows) + 1,
            "columns": 2,
            "created": True,
            "x": x,
            "y": y,
        }

    def _fill_bom(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        self._open_drawing_if_needed(args.get("drawing_path"))
        rows = args["rows"]
        expected: dict[str, int] = {str(row["name"]): int(row["quantity"]) for row in rows}
        name_column = int(args.get("name_column", 1))
        quantity_column = int(args.get("quantity_column", 2))
        created = False
        try:
            table, context = self._find_bom_table(set(expected))
        except RuntimeError:
            if not args.get("create_if_missing", True):
                raise
            table, context = self._create_bom_table(args, rows)
            created = True
        row_count, _column_count = self._table_size(table)
        written: dict[str, int] = {}
        missing = set(expected)
        for row_index in range(1, row_count + 1):
            component_name = self._cell_text(table, row_index, name_column).strip()
            if component_name not in expected:
                continue
            quantity = expected[component_name]
            self._set_cell_text(table, row_index, quantity_column, str(quantity))
            written[component_name] = quantity
            missing.discard(component_name)
        if missing:
            raise RuntimeError(
                f"DrawingTable was found, but these components were not present in "
                f"column {name_column}: {sorted(missing)}. Context: {context}"
            )
        try:
            self.conn.active_document.Update()
        except Exception:
            pass
        if args.get("save", True):
            self.conn.active_document.Save()
        self.conn.refresh_display()
        return result(
            document=self.conn.active_document.Name,
            context=context,
            written=written,
            created=created,
            saved=bool(args.get("save", True)),
            tool="catia_fill_drawing_bom",
        )

    def _from_part(self, args: dict[str, Any]) -> str:
        self.conn.ensure_connected()
        # Resolve the source before creating the drawing (which becomes the active doc).
        source_name = self._find_source_document(args.get("part_name", "active")).Name
        self._new_drawing(
            {
                "paper_size": args.get("paper_size", "A3"),
                "orientation": args.get("orientation", "landscape"),
                "scale": args.get("scale"),
            }
        )
        view_scale = args.get("view_scale", 0.15)
        # Front is the primary; the right/top projections auto-position relative to it
        # and inherit its scale, so only Front and the independent Iso need placing.
        self._base_view(
            {"part_name": source_name, "orientation": "front", "name": "Front",
             "x": 110, "y": 150, "scale": view_scale}
        )
        for direction, name in (("right", "Right"), ("top", "Top")):
            self._projection_view(
                {"parent_view": "Front", "direction": direction, "name": name}
            )
        self._base_view(
            {"part_name": source_name, "orientation": "iso", "name": "Iso",
             "x": 340, "y": 190, "scale": view_scale}
        )
        self._update({})
        out: dict[str, Any] = {
            "tool": "catia_drawing_from_part",
            "document": self.conn.active_document.Name,
            "source": source_name,
            "views": ["Front", "Right", "Top", "Iso"],
        }
        output_path = args.get("output_path")
        if output_path:
            path = normalize_catia_path(output_path)
            try:
                self.conn.active_document.ExportData(path, "pdf")
                out["pdf"] = path
            except Exception as exc:
                out["pdf_error"] = str(exc)
        return result(**out)
