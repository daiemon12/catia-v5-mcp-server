"""Document management tools for CATIA V5.

Create, open, save, close, and list documents (Part, Product, Drawing).
"""

from __future__ import annotations

import json
import os
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.paths import normalize_catia_path


class DocumentTools:
    """Tools for managing CATIA V5 documents."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_connect",
                "description": (
                    "Connect to CATIA V5. Attaches to a running instance or launches a new one. "
                    "Must be called before any other CATIA tool."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_disconnect",
                "description": "Disconnect from CATIA V5 (does not close CATIA).",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_new_part",
                "description": (
                    "Create a new empty Part document in CATIA V5. "
                    "A Part is used for single-body 3D modeling (sketches + features)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Optional name for the part",
                        },
                    },
                },
            },
            {
                "name": "catia_new_product",
                "description": (
                    "Create a new empty Product (assembly) document in CATIA V5. "
                    "A Product is used to assemble multiple Parts together."
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
                "description": "Open an existing CATIA document from a file path (.CATPart, .CATProduct, .CATDrawing).",
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
                "name": "catia_activate_document",
                "description": "Activate an already-open CATIA document by full path or document name.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Full path of the open document to activate",
                        },
                        "name": {
                            "type": "string",
                            "description": "Document name to activate, e.g. '10.CATPart'",
                        },
                    },
                },
            },
            {
                "name": "catia_save_document",
                "description": "Save the active CATIA document. Optionally save to a new path (Save As).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Optional new file path for Save As",
                        },
                    },
                },
            },
            {
                "name": "catia_close_document",
                "description": "Close the active CATIA document.",
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
                "description": "List all open documents in CATIA V5 with their types and paths.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "catia_get_active_document_info",
                "description": (
                    "Get detailed info about the active CATIA document: "
                    "name, type, path, part bodies, features, etc."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
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
                return self._new_part(arguments.get("name"))
            case "catia_new_product":
                return self._new_product(arguments.get("name"))
            case "catia_open_document":
                return self._open_document(arguments["file_path"])
            case "catia_activate_document":
                return self._activate_document(
                    arguments.get("file_path"), arguments.get("name")
                )
            case "catia_save_document":
                return self._save_document(arguments.get("file_path"))
            case "catia_close_document":
                return self._close_document(arguments.get("save", False))
            case "catia_list_documents":
                return self._list_documents()
            case "catia_get_active_document_info":
                return self._get_active_document_info()
            case _:
                raise ValueError(f"Unknown document tool: {tool_name}")

    def _new_part(self, name: str | None = None) -> str:
        self.conn.ensure_connected()
        docs = self.conn.documents
        doc = docs.Add("Part")
        if name:
            doc.Part.Name = name
        part_name = doc.Part.Name
        self.conn.refresh_display()
        return f"Created new Part document: '{part_name}'"

    def _new_product(self, name: str | None = None) -> str:
        self.conn.ensure_connected()
        docs = self.conn.documents
        doc = docs.Add("Product")
        if name:
            doc.Product.Name = name
        product_name = doc.Product.Name
        self.conn.refresh_display()
        return f"Created new Product (assembly) document: '{product_name}'"

    def _open_document(self, file_path: str) -> str:
        self.conn.ensure_connected()
        docs = self.conn.documents
        file_path = normalize_catia_path(file_path)
        # Calling Documents.Open on a document that is already open raises a
        # blocking modal dialog that hangs the automation call until someone
        # dismisses it on the CATIA desktop. If the target is already open,
        # reuse and activate it instead of reopening.
        target = os.path.normcase(os.path.abspath(file_path))
        for index in range(1, docs.Count + 1):
            existing = docs.Item(index)
            full_name = getattr(existing, "FullName", "") or ""
            if full_name and os.path.normcase(os.path.abspath(full_name)) == target:
                self._activate_document(file_path=file_path)
                return f"Document already open; reused: '{existing.Name}' from {file_path}"
        doc = docs.Open(file_path)
        self._ensure_active_document(doc.Name, file_path)
        return f"Opened document: '{doc.Name}' from {file_path}"

    def _activate_document(self, file_path: str | None = None, name: str | None = None) -> str:
        self.conn.ensure_connected()
        if not file_path and not name:
            raise ValueError("file_path or name is required")

        docs = self.conn.documents
        target_path = (
            os.path.normcase(os.path.abspath(normalize_catia_path(file_path)))
            if file_path
            else None
        )
        target_name = name.casefold() if name else None
        selected = None

        for index in range(1, docs.Count + 1):
            doc = docs.Item(index)
            full_name = getattr(doc, "FullName", "") or ""
            path_matches = (
                bool(target_path)
                and full_name
                and os.path.normcase(os.path.abspath(full_name)) == target_path
            )
            name_matches = bool(target_name) and doc.Name.casefold() == target_name
            if path_matches or name_matches:
                selected = doc
                break

        if selected is None:
            wanted = file_path or name
            raise RuntimeError(f"Open document was not found: {wanted}")

        # CATIA automation can leave ActiveDocument unchanged after Document.Activate()
        # when many documents are open. Activate both the document and its window,
        # then verify the active document before returning.
        try:
            selected.Activate()
        except Exception:
            pass
        try:
            windows = self.conn.app.Windows
            for index in range(1, windows.Count + 1):
                window = windows.Item(index)
                caption = getattr(window, "Caption", "") or ""
                if selected.Name.casefold() in caption.casefold():
                    window.Activate()
                    break
        except Exception:
            pass

        self._ensure_active_document(selected.Name, getattr(selected, "FullName", "") or None)
        return f"Activated document: '{selected.Name}'"

    def _ensure_active_document(self, name: str, file_path: str | None = None) -> None:
        active = self.conn.active_document
        active_path = getattr(active, "FullName", "") or ""
        if active.Name == name:
            if not file_path:
                return
            if active_path and os.path.normcase(os.path.abspath(active_path)) == os.path.normcase(
                os.path.abspath(file_path)
            ):
                return
        raise RuntimeError(
            f"CATIA did not activate '{name}'. Active document is "
            f"'{active.Name}' ({active_path or 'unsaved'})."
        )

    def _save_document(self, file_path: str | None = None) -> str:
        doc = self.conn.active_document
        if file_path:
            # CATIA rejects forward-slash paths ("invalid file name" dialog) and
            # won't create missing directories — normalize before SaveAs.
            file_path = normalize_catia_path(file_path)
            doc.SaveAs(file_path)
            return f"Document saved as: {file_path}"
        else:
            doc.Save()
            return f"Document '{doc.Name}' saved"

    def _close_document(self, save: bool = False) -> str:
        doc = self.conn.active_document
        name = doc.Name
        if save:
            doc.Save()
        doc.Close()
        return f"Document '{name}' closed" + (" (saved)" if save else "")

    def _list_documents(self) -> str:
        self.conn.ensure_connected()
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

    def _get_active_document_info(self) -> str:
        doc = self.conn.active_document
        info: dict[str, Any] = {
            "name": doc.Name,
            "path": doc.FullName if hasattr(doc, "FullName") else "unsaved",
        }

        # Try Part document
        try:
            part = doc.Part
            info["type"] = "CATPart"
            info["part_name"] = part.Name

            # List bodies
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
