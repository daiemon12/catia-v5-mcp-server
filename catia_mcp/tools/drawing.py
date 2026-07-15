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
