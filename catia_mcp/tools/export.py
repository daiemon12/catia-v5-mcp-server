"""Export tools for CATIA V5.

Export to STEP, IGES, STL, 3DXML, and other formats.
Also includes screenshot capture.
"""

from __future__ import annotations

import os
from typing import Any

from catia_mcp.connection import CATIAConnection
from catia_mcp.screenshot import capture_cropped_screenshot

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
                    "Capture the current CATIA view, trim outer white margins and save a lossless "
                    "PNG without resizing. Temporarily hides the specification tree and compass "
                    "and sets a white background, then restores original UI and background. "
                    "Keeps every non-white point, line and annotation inside the optional region. "
                    "The corner navigation axis cannot be hidden through this tool; use region "
                    "to exclude it. Contents outside region are discarded. Does not move the camera. "
                    "Rejects all-white captures and "
                    "existing output files. Returns actual dimensions and source crop coordinates."
                ),
                "inputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "file_path": {
                            "type": "string", "minLength": 1,
                            "description": "Absolute path for a new PNG file; never overwrites.",
                        },
                        "padding": {
                            "type": "integer", "minimum": 0, "maximum": 4096, "default": 16,
                            "description": "Pixels kept around content, limited by capture edges.",
                        },
                        "white_tolerance": {
                            "type": "integer", "minimum": 0, "maximum": 32, "default": 0,
                            "description": (
                                "Background when every RGB channel is >= 255 minus this value. "
                                "0 removes only exact white; larger values may trim very pale content."
                            ),
                        },
                        "region": {
                            "type": "object", "additionalProperties": False,
                            "description": (
                                "Optional source pixel rectangle containing all desired model content. "
                                "Left/top inclusive, right/bottom exclusive. Default: whole capture. "
                                "Choose a region excluding the lower-right navigation axis; "
                                "content outside is discarded. Padding stays inside this region."
                            ),
                            "properties": {
                                "left": {"type": "integer", "minimum": 0},
                                "top": {"type": "integer", "minimum": 0},
                                "right": {"type": "integer", "minimum": 1},
                                "bottom": {"type": "integer", "minimum": 1},
                            },
                            "required": ["left", "top", "right", "bottom"],
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

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str | dict[str, Any]:
        match tool_name:
            case "catia_export":
                return self._export(arguments["file_path"], arguments.get("format"))
            case "catia_screenshot":
                return capture_cropped_screenshot(self.conn, arguments)
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

        # Ensure output directory exists
        output_dir = os.path.dirname(file_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

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

    def _set_view(self, view: str) -> str:
        self.conn.ensure_connected()
        viewer = self.conn.active_window.ActiveViewer
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
        viewer = self.conn.active_window.ActiveViewer
        viewer.Reframe()
        return "View fitted to all geometry"
