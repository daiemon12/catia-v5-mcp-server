"""Document management tools for CATIA V5 and CATIA 3DEXPERIENCE.

V5: create, open, save, close and list file-based documents (Part, Product,
Drawing). 3DEXPERIENCE: the same tools map onto PLM services: new content
through PLMNewService, save through PLMPropagateService (to the 3DSpace
database), and "documents" are the editors / windows open in the session.
Database search and open live in tools/plm.py.
"""

from __future__ import annotations

import json
from typing import Any

from catia_mcp.automation import com_name, iter_items, resolves, safe_get
from catia_mcp.connection import CATIAConnection
from catia_mcp.errors import (
    AmbiguousTarget,
    InvalidArgument,
    ObjectNotFound,
    UnsupportedCapability,
    after_mutation,
)
from catia_mcp.plm import PLMSession

def _same(a: Any, b: Any) -> bool:
    """COM identity (pywin32 compares the underlying IUnknown)."""
    try:
        return bool(a == b)
    except Exception:
        return a is b


DB_SAVE_NOTE = (
    "On 3DEXPERIENCE this writes to the shared 3DSpace database (visible to "
    "other users according to your collaborative space)."
)


class DocumentTools:
    """Tools for managing CATIA documents (V5) and editors (3DEXPERIENCE)."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection
        self.plm = PLMSession(connection)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_connect",
                "description": (
                    "Connect to CATIA V5 or CATIA 3DEXPERIENCE (detected automatically). "
                    "Attaches to a running instance or launches a new one. "
                    "Must be called before any other CATIA tool."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_disconnect",
                "description": "Disconnect from CATIA (does not close CATIA).",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_new_part",
                "description": (
                    "Create a new empty Part for single-body 3D modeling (sketches + "
                    "features). V5: a CATPart document. 3DEXPERIENCE: a 3D Part "
                    "(product + shape, needs the matching licence/role) or a 3D Shape, "
                    "created in session only; nothing reaches the database until "
                    "catia_save_document."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Optional name (V5 part name; 3DEXPERIENCE title V_Name)",
                        },
                        "plm_type": {
                            "type": "string",
                            "enum": ["auto", "3DPart", "3DShape"],
                            "description": (
                                "3DEXPERIENCE only. 'auto' (default) tries a 3D Part and "
                                "falls back to a 3D Shape when the licence refuses it."
                            ),
                        },
                    },
                },
            },
            {
                "name": "catia_new_product",
                "description": (
                    "Create a new empty Product (assembly). V5: a CATProduct document. "
                    "3DEXPERIENCE: a Physical Product (VPMReference), which needs a "
                    "licence/role allowing scripted product creation on many sites."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Optional name for the product/assembly",
                        },
                    },
                },
            },
            {
                "name": "catia_open_document",
                "description": (
                    "Open an existing CATIA document from a file path (.CATPart, "
                    ".CATProduct, .CATDrawing). On 3DEXPERIENCE, content lives in the "
                    "database: use catia_open_from_database instead (file opening is "
                    "attempted only where the installation still exposes Documents.Open)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Full path to the CATIA document to open",
                        },
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "catia_save_document",
                "description": (
                    "Save the active document. V5: Save, or Save As when file_path is "
                    "given. 3DEXPERIENCE: saves (propagates) the active editor's content "
                    "to the 3DSpace database; file_path is not accepted there (use "
                    "catia_export to write a file). " + DB_SAVE_NOTE
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "V5 only: new file path for Save As",
                        },
                    },
                },
            },
            {
                "name": "catia_close_document",
                "description": (
                    "Close the active document (V5) or the active editor window "
                    "(3DEXPERIENCE). Unsaved 3DEXPERIENCE changes are discarded unless "
                    "save=true."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "save": {
                            "type": "boolean",
                            "description": "Whether to save before closing (default: false)",
                            "default": False,
                        },
                    },
                },
            },
            {
                "name": "catia_list_documents",
                "description": (
                    "List open documents (V5) or open editors with their content type "
                    "and title (3DEXPERIENCE)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_get_active_document_info",
                "description": (
                    "Get detailed info about the active document / editor: name, type, "
                    "PLM attributes (3DEXPERIENCE), part bodies, features, geometrical "
                    "sets, components."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_activate_document",
                "description": (
                    "Bring an open document (V5, by name e.g. 'Part1.CATPart') or editor "
                    "window (3DEXPERIENCE, by title or window caption) to the front so "
                    "the next tools act on it. Most tools act on the active one."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Document name, title, or part of the window caption",
                        },
                    },
                    "required": ["name"],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_connect":
                return self.conn.connect()
            case "catia_disconnect":
                return self.conn.disconnect()
            case "catia_new_part":
                return self._new_part(arguments.get("name"), arguments.get("plm_type") or "auto")
            case "catia_new_product":
                return self._new_product(arguments.get("name"))
            case "catia_open_document":
                return self._open_document(arguments["file_path"])
            case "catia_save_document":
                return self._save_document(arguments.get("file_path"))
            case "catia_close_document":
                return self._close_document(arguments.get("save", False))
            case "catia_list_documents":
                return self._list_documents()
            case "catia_get_active_document_info":
                return self._get_active_document_info()
            case "catia_activate_document":
                return self._activate_document(arguments["name"])
            case _:
                raise ValueError(f"Unknown document tool: {tool_name}")

    # ── New ──

    def _new_part(self, name: str | None = None, plm_type: str = "auto") -> str:
        self.conn.ensure_connected()
        if self.conn.is_3dx:
            return self._new_part_3dx(name, plm_type)
        if plm_type != "auto":
            raise InvalidArgument("plm_type applies to 3DEXPERIENCE only; omit it on CATIA V5.")
        docs = self.conn.documents
        doc = docs.Add("Part")
        rename_note = ""
        if name:
            try:
                doc.Part.Name = name
            except Exception as e:
                rename_note = f" (rename to '{name}' not supported by this CATIA version: {e})"
        part_name = doc.Part.Name
        self.conn.refresh_display()
        return f"Created new Part document: '{part_name}'{rename_note}"

    def _new_part_3dx(self, name: str | None, plm_type: str) -> str:
        attempts = ["3DPart", "3DShape"] if plm_type == "auto" else [plm_type]
        errors: list[str] = []
        created = None
        for kind in attempts:
            try:
                self.plm.create(kind)
                created = kind
                break
            except Exception as e:
                errors.append(f"{kind}: {e}")
        if created is None:
            raise RuntimeError(
                "3DEXPERIENCE refused to create the part ("
                + "; ".join(errors)
                + "). Check that you are logged in, have a collaborative space "
                "selected, and hold a role allowing creation."
            )
        with after_mutation():
            part = self.conn.get_active_part()
            note = ""
            if created == "3DShape" and plm_type == "auto":
                note = (
                    " A 3D Part could not be created (" + errors[0] + "), so a 3D Shape was "
                    "created instead; it has no product node of its own."
                )
            title = self._apply_title(name, part)
        self.conn.refresh_display()
        return (
            f"Created new {created} '{title}' in the session (not yet saved to the "
            f"database).{note}"
        )

    def _apply_title(self, name: str | None, part: Any) -> str:
        """Set V_Name on the new content: the reference (3D Part, product) or
        rep (3D Shape), plus the shape rep of a 3D Part."""
        active = self.conn.active_object()
        if name:
            targets = []
            plm_object = self.plm.plm_object_of(active)
            if plm_object is not None:
                targets.append(plm_object)
            rep = safe_get(part, "Parent") if part is not None else None
            if rep is not None and resolves(rep, "SetAttributeValue"):
                if not any(_same(rep, t) for t in targets):
                    targets.append(rep)
            applied = [self.plm.set_title(t, name) for t in targets]
            if not any(applied):
                return f"{self.plm.title_of(active)} (title '{name}' could not be applied)"
        return self.plm.title_of(active)

    def _new_product(self, name: str | None = None) -> str:
        self.conn.ensure_connected()
        if self.conn.is_3dx:
            try:
                self.plm.create("VPMReference")
            except Exception as e:
                raise RuntimeError(
                    f"3DEXPERIENCE refused to create a Physical Product ({e}). Scripted "
                    "product creation needs a licence/role that many sites do not grant "
                    "(field reports: 'Operation not authorized'). Create the product in "
                    "the UI or open an existing one with catia_open_from_database."
                ) from e
            with after_mutation():
                title = self._apply_title(name, None)
            self.conn.refresh_display()
            return f"Created new Physical Product '{title}' in the session (not yet saved)."
        docs = self.conn.documents
        doc = docs.Add("Product")
        rename_note = ""
        if name:
            try:
                doc.Product.Name = name
            except Exception as e:
                rename_note = f" (rename to '{name}' not supported by this CATIA version: {e})"
            else:
                if doc.Product.Name != name:
                    rename_note = (
                        f" (requested name '{name}' was not applied by CATIA; "
                        f"kept '{doc.Product.Name}')"
                    )
        product_name = doc.Product.Name
        self.conn.refresh_display()
        return f"Created new Product (assembly) document: '{product_name}'{rename_note}"

    # ── Open / save / close ──

    def _open_document(self, file_path: str) -> str:
        self.conn.ensure_connected()
        if self.conn.is_3dx and not resolves(self.conn.app, "Documents"):
            raise UnsupportedCapability(
                "This 3DEXPERIENCE installation does not open files through "
                "automation: content lives in the database. Use "
                "catia_search_database / catia_open_from_database, or import the file "
                "in the CATIA UI first."
            )
        docs = self.conn.documents
        doc = docs.Open(file_path)
        return f"Opened document: '{doc.Name}' from {file_path}"

    def _save_document(self, file_path: str | None = None) -> str:
        if self.conn.is_3dx:
            if file_path:
                raise InvalidArgument(
                    "3DEXPERIENCE has no Save As to a file: content is saved to the "
                    "database. Omit file_path to save, or use catia_export to write a "
                    "STEP/STL/... file."
                )
            title = self.plm.title_of(self.conn.active_object())
            self.plm.propagate()
            return f"Saved '{title}' (active editor content) to the 3DEXPERIENCE database."
        doc = self.conn.active_document
        if file_path:
            doc.SaveAs(file_path)
            return f"Document saved as: {file_path}"
        else:
            doc.Save()
            return f"Document '{doc.Name}' saved"

    def _close_document(self, save: bool = False) -> str:
        if self.conn.is_3dx:
            title = self.plm.title_of(self.conn.active_object())
            if save:
                self.plm.propagate()
            app = self.conn.app
            previous_alerts = safe_get(app, "DisplayFileAlerts")
            try:
                if previous_alerts is not None:
                    app.DisplayFileAlerts = False
                self.conn.active_window.Close()
            finally:
                if previous_alerts is not None:
                    try:
                        app.DisplayFileAlerts = previous_alerts
                    except Exception:
                        pass
            return f"Editor '{title}' closed" + (
                " (saved to the database first)" if save else " (unsaved changes discarded)"
            )
        doc = self.conn.active_document
        name = doc.Name
        if save:
            doc.Save()
        doc.Close()
        return f"Document '{name}' closed" + (" (saved)" if save else "")

    # ── List / info / activate ──

    def _list_documents(self) -> str:
        self.conn.ensure_connected()
        if self.conn.is_3dx:
            return self._list_editors()
        docs = self.conn.documents
        result = []
        for i in range(1, docs.Count + 1):
            doc = docs.Item(i)
            doc_info = {
                "name": doc.Name,
                "path": doc.FullName if hasattr(doc, "FullName") else "unsaved",
            }
            # Detect document type
            try:
                _ = doc.Part
                doc_info["type"] = "CATPart"
            except Exception:
                try:
                    _ = doc.Product
                    doc_info["type"] = "CATProduct"
                except Exception:
                    doc_info["type"] = "Other"
            result.append(doc_info)

        if not result:
            return "No documents open in CATIA"
        return json.dumps(result, indent=2, ensure_ascii=False)

    def _list_editors(self) -> str:
        app = self.conn.app
        try:
            active = app.ActiveEditor
        except Exception:
            active = None
        editors = []
        for i, editor in enumerate(self.plm.editors(), start=1):
            obj = safe_get(editor, "ActiveObject")
            row: dict[str, Any] = {
                "index": i,
                "type": self.conn.classify(obj),
                "title": self.plm.title_of(obj) if obj is not None else None,
            }
            plm_object = self.plm.plm_object_of(obj) if obj is not None else None
            if plm_object is not None:
                row.update(self.plm.attributes(plm_object, ("PLM_ExternalID", "revision", "current")))
            try:
                row["active"] = bool(active is not None and editor == active)
            except Exception:
                pass
            editors.append(row)
        windows = []
        try:
            for window in iter_items(app.Windows):
                windows.append(str(safe_get(window, "Caption", "")))
        except Exception:
            pass
        if not editors and not windows:
            return "No editors open in CATIA 3DEXPERIENCE"
        return json.dumps({"editors": editors, "windows": windows}, indent=2, ensure_ascii=False)

    def _get_active_document_info(self) -> str:
        if self.conn.is_3dx:
            return self._active_info_3dx()
        doc = self.conn.active_document
        info: dict[str, Any] = {
            "name": doc.Name,
            "path": doc.FullName if hasattr(doc, "FullName") else "unsaved",
        }

        # Try Part document
        try:
            part = doc.Part
            info["type"] = "CATPart"
            info.update(self._part_summary(part))
            return json.dumps(info, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # Try Product document
        try:
            product = doc.Product
            info["type"] = "CATProduct"
            info["product_name"] = product.Name
            info["part_number"] = product.PartNumber

            # List sub-products
            prods = product.Products
            children = []
            for i in range(1, prods.Count + 1):
                child = prods.Item(i)
                children.append({
                    "name": child.Name,
                    "part_number": child.PartNumber,
                })
            info["components"] = children
            return json.dumps(info, indent=2, ensure_ascii=False)
        except Exception:
            pass

        info["type"] = "Unknown"
        return json.dumps(info, indent=2, ensure_ascii=False)

    def _part_summary(self, part: Any) -> dict[str, Any]:
        info: dict[str, Any] = {"part_name": part.Name}
        bodies = part.Bodies
        body_list = []
        for i in range(1, bodies.Count + 1):
            body = bodies.Item(i)
            shapes = []
            for j in range(1, body.Shapes.Count + 1):
                shapes.append(body.Shapes.Item(j).Name)
            body_list.append({
                "name": body.Name,
                "features": shapes,
            })
        info["bodies"] = body_list
        try:
            info["active_body"] = str(self.conn.get_active_part_body().Name)
        except Exception:
            pass

        # List geometrical sets (hybrid bodies)
        try:
            hbs = part.HybridBodies
            geo_sets = []
            for i in range(1, hbs.Count + 1):
                geo_sets.append(hbs.Item(i).Name)
            info["geometrical_sets"] = geo_sets
        except Exception:
            pass

        # Parameters count
        try:
            info["parameters_count"] = part.Parameters.Count
        except Exception:
            pass
        return info

    def _active_info_3dx(self) -> str:
        obj = self.conn.active_object()
        kind = self.conn.classify(obj)
        info: dict[str, Any] = {
            "platform": "3DEXPERIENCE",
            "type": kind,
            "title": self.plm.title_of(obj),
        }
        plm_object = self.plm.plm_object_of(obj)
        if plm_object is not None:
            info["plm_attributes"] = self.plm.attributes(plm_object)
        if kind in ("part", "product"):
            try:
                part = self.conn.get_active_part()
                info.update(self._part_summary(part))
            except Exception as e:
                if kind == "part":
                    info["part_error"] = str(e)
        if kind == "product":
            try:
                root = self.conn.root_occurrence()
                info["components"] = [
                    self.plm.occurrence_name(c) for c in self.plm.child_occurrences(root)
                ]
            except Exception as e:
                info["components_error"] = str(e)
        if kind == "drawing":
            try:
                info["sheets"] = [com_name(s) for s in iter_items(obj.Sheets)]
            except Exception:
                pass
        return json.dumps(info, indent=2, ensure_ascii=False)

    def _activate_document(self, name: str) -> str:
        self.conn.ensure_connected()
        if not self.conn.is_3dx:
            docs = self.conn.documents
            try:
                doc = docs.Item(name)
            except Exception:
                names = ", ".join(com_name(d) for d in iter_items(docs))
                raise ObjectNotFound(f"No open document named '{name}'. Open: {names or 'none'}.")
            doc.Activate()
            return f"Document '{doc.Name}' activated."
        app = self.conn.app
        windows = list(iter_items(app.Windows))
        captions = [str(safe_get(w, "Caption", "")) for w in windows]
        exact = [w for w, c in zip(windows, captions) if c == name]
        matches = exact or [w for w, c in zip(windows, captions) if name.lower() in c.lower()]
        if not matches:
            raise ObjectNotFound(
                f"No 3DEXPERIENCE window matches '{name}'. Windows: {', '.join(captions) or 'none'}."
            )
        if len(matches) > 1:
            raise AmbiguousTarget(
                f"'{name}' matches several windows: "
                + ", ".join(c for w, c in zip(windows, captions) if w in matches)
                + ". Pass more of the caption."
            )
        matches[0].Activate()
        return f"Window '{safe_get(matches[0], 'Caption', name)}' activated."
