"""Export tools for CATIA V5.

Export to STEP, IGES, STL, 3DXML, and other formats.
Also includes screenshot capture.
"""

from __future__ import annotations

import os
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.paths import normalize_catia_path

# CATIA export format identifiers
FORMAT_MAP = {
    "step": "stp",
    "stp": "stp",
    "iges": "igs",
    "igs": "igs",
    "stl": "stl",
    "3dxml": "3dxml",
    "wrl": "wrl",
    "vrml": "wrl",
    "pdf": "pdf",
    "cgr": "cgr",
}


class ExportTools:
    """Tools for exporting CATIA V5 data to external formats."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_export",
                "description": (
                    "Export the active document to a file. "
                    "Supported formats: STEP (.stp), IGES (.igs), STL (.stl), "
                    "3DXML (.3dxml), VRML (.wrl), PDF (2D drawings)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": (
                                "Output file path. The format is determined by the extension. "
                                "Example: 'C:/export/my_part.stp'"
                            ),
                        },
                        "format": {
                            "type": "string",
                            "description": (
                                "Export format (optional if file extension is provided). "
                                "One of: step, iges, stl, 3dxml, vrml"
                            ),
                            "enum": ["step", "iges", "stl", "3dxml", "vrml"],
                        },
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "catia_screenshot",
                "description": (
                    "Capture a screenshot of the current 3D view and save as an image. "
                    "Raster formats JPG/BMP/TIFF and vector EMF/CGM are chosen by the "
                    "file extension. CATIA cannot emit PNG, so a .png path is written as "
                    ".jpg instead (the returned path reflects this)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Output image path (e.g., 'C:/screenshots/part.jpg')",
                        },
                        "width": {
                            "type": "integer",
                            "description": "Image width in pixels (default: 1920)",
                            "default": 1920,
                        },
                        "height": {
                            "type": "integer",
                            "description": "Image height in pixels (default: 1080)",
                            "default": 1080,
                        },
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "catia_set_view",
                "description": (
                    "Set the 3D view orientation. "
                    "Standard views: front, back, top, bottom, left, right, isometric."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "view": {
                            "type": "string",
                            "description": "View orientation",
                            "enum": [
                                "front", "back", "top", "bottom",
                                "left", "right", "isometric",
                            ],
                        },
                    },
                    "required": ["view"],
                },
            },
            {
                "name": "catia_fit_all",
                "description": "Fit all geometry in the current 3D view (zoom to fit).",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_export":
                return self._export(arguments["file_path"], arguments.get("format"))
            case "catia_screenshot":
                return self._screenshot(
                    arguments["file_path"],
                    arguments.get("width", 1920),
                    arguments.get("height", 1080),
                )
            case "catia_set_view":
                return self._set_view(arguments["view"])
            case "catia_fit_all":
                return self._fit_all()
            case _:
                raise ValueError(f"Unknown export tool: {tool_name}")

    def _export(self, file_path: str, fmt: str | None = None) -> str:
        self.conn.ensure_connected()
        doc = self.conn.active_document

        # Determine format from extension if not specified
        if fmt is None:
            ext = os.path.splitext(file_path)[1].lstrip(".").lower()
            fmt = ext

        fmt_key = fmt.lower()
        if fmt_key not in FORMAT_MAP:
            supported = ", ".join(sorted(set(FORMAT_MAP.keys())))
            raise ValueError(
                f"Unsupported export format: '{fmt}'. Supported: {supported}"
            )

        # Normalize to a Windows path (CATIA rejects forward-slash paths with an
        # "invalid file name" dialog) and ensure the output directory exists.
        file_path = normalize_catia_path(file_path)

        # CATIA V5 export via SaveAs with format specification
        doc.ExportData(file_path, FORMAT_MAP[fmt_key])

        size_info = ""
        if os.path.exists(file_path):
            size_bytes = os.path.getsize(file_path)
            if size_bytes > 1024 * 1024:
                size_info = f" ({size_bytes / (1024*1024):.1f} MB)"
            elif size_bytes > 1024:
                size_info = f" ({size_bytes / 1024:.1f} KB)"
            else:
                size_info = f" ({size_bytes} bytes)"

        return f"Exported to {file_path}{size_info} (format: {fmt_key.upper()})"

    # CATIA's CatCaptureFormat enum (V5). There is NO PNG format - the raster
    # options are TIFF/BMP/JPEG; EMF/CGM are vector. CaptureToFile ignores the
    # file extension and writes whatever this integer selects, so passing 1
    # (EMF) wrote EMF content under a .png name regardless of the path.
    _CAPTURE_FORMATS = {
        ".cgm": 0,
        ".emf": 1,
        ".tif": 2,
        ".tiff": 2,
        ".bmp": 4,
        ".jpg": 5,
        ".jpeg": 5,
    }

    def _screenshot(self, file_path: str, width: int = 1920, height: int = 1080) -> str:
        self.conn.ensure_connected()

        # Normalize to a Windows path (forward slashes are rejected) and ensure
        # the output directory exists.
        file_path = normalize_catia_path(file_path)

        ext = os.path.splitext(file_path)[1].lower()
        capture_format = self._CAPTURE_FORMATS.get(ext)
        if capture_format is None:
            # PNG (or any unsupported extension): CATIA cannot emit PNG, so write
            # a JPEG and rename the path to match, keeping content and name in
            # agreement instead of an EMF-under-.png mismatch.
            capture_format = 5  # catCaptureFormatJPEG
            file_path = os.path.splitext(file_path)[0] + ".jpg"

        # Capture via the active viewer.
        viewer = self.conn.active_viewer
        viewer.CaptureToFile(capture_format, file_path)

        return f"Screenshot saved to {file_path}"

    def _set_view(self, view: str) -> str:
        self.conn.ensure_connected()
        viewer = self.conn.active_viewer
        viewpoint = viewer.Viewpoint3D

        # Standard view direction vectors and up vectors
        views = {
            "front":     {"sight": (0, 0, -1), "up": (0, 1, 0)},
            "back":      {"sight": (0, 0, 1),  "up": (0, 1, 0)},
            "top":       {"sight": (0, -1, 0), "up": (0, 0, -1)},
            "bottom":    {"sight": (0, 1, 0),  "up": (0, 0, 1)},
            "left":      {"sight": (1, 0, 0),  "up": (0, 1, 0)},
            "right":     {"sight": (-1, 0, 0), "up": (0, 1, 0)},
            "isometric": {"sight": (-1, -1, -1), "up": (0, 1, 0)},
        }

        if view not in views:
            raise ValueError(f"Unknown view: '{view}'")

        v = views[view]
        sight = v["sight"]
        up = v["up"]

        # Set viewpoint sight and up directions
        viewpoint.PutSightDirection(list(sight))
        viewpoint.PutUpDirection(list(up))

        # Fit all in view
        viewer.Reframe()

        return f"View set to: {view}"

    def _fit_all(self) -> str:
        self.conn.ensure_connected()
        viewer = self.conn.active_viewer
        viewer.Reframe()
        return "View fitted to all geometry"
