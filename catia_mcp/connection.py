"""CATIA V5 COM Connection Manager.

Manages the connection to CATIA V5 via Windows COM Automation API (win32com).
Supports connecting to a running instance or launching a new one.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("catia_mcp")

# COM imports are deferred to runtime (Windows only)
try:
    import pythoncom
    import win32com.client

    HAS_COM = True
except ImportError:
    HAS_COM = False


class CATIAConnection:
    """Manages connection to CATIA V5 via COM Automation."""

    # CATIA V5 COM ProgID
    CATIA_PROGID = "CATIA.Application"

    def __init__(self) -> None:
        self.app: Any | None = None
        self._initialized_com = False

    @property
    def is_connected(self) -> bool:
        """Check if we have an active CATIA connection."""
        if self.app is None:
            return False
        try:
            # Try accessing a property to verify the connection is alive
            _ = self.app.Caption
            return True
        except Exception:
            self.app = None
            return False

    def connect(self) -> str:
        """Connect to CATIA V5. Tries running instance first, then launches new one.

        Returns a status message string.
        """
        if not HAS_COM:
            raise RuntimeError(
                "pywin32 is not installed. Install it with: pip install pywin32\n"
                "Note: This MCP server requires Windows with CATIA V5 installed."
            )

        if self.is_connected:
            version = self._get_version()
            return f"Already connected to CATIA V5 ({version})"

        # Initialize COM for this thread
        if not self._initialized_com:
            pythoncom.CoInitialize()
            self._initialized_com = True

        # Phase 1: Try to attach to a running CATIA instance
        try:
            self.app = win32com.client.GetActiveObject(self.CATIA_PROGID)
            version = self._get_version()
            logger.info("Connected to running CATIA V5 instance (%s)", version)
            return f"Connected to running CATIA V5 instance ({version})"
        except Exception:
            logger.info("No running CATIA instance found, launching new one...")

        # Phase 2: Launch a new CATIA instance
        try:
            self.app = win32com.client.Dispatch(self.CATIA_PROGID)
            self.app.Visible = True
            version = self._get_version()
            logger.info("Launched new CATIA V5 instance (%s)", version)
            return f"Launched new CATIA V5 instance ({version})"
        except Exception as e:
            self.app = None
            raise RuntimeError(
                f"Failed to connect to CATIA V5: {e}\n"
                "Make sure CATIA V5 is installed and licensed on this machine."
            ) from e

    def disconnect(self) -> str:
        """Disconnect from CATIA V5 (does not close CATIA)."""
        if self.app is not None:
            self.app = None
        if self._initialized_com:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._initialized_com = False
        return "Disconnected from CATIA V5"

    def ensure_connected(self) -> None:
        """Ensure we have an active CATIA connection, connecting if needed."""
        if not self.is_connected:
            self.connect()

    def _get_version(self) -> str:
        """Get CATIA version string."""
        try:
            # CATIA V5 exposes SystemService.Environ or Caption
            caption = self.app.Caption
            return caption if caption else "unknown version"
        except Exception:
            return "unknown version"

    # ── Helper properties for quick access to CATIA objects ──

    @property
    def documents(self) -> Any:
        """Get the CATIA Documents collection."""
        self.ensure_connected()
        return self.app.Documents

    @property
    def active_document(self) -> Any:
        """Get the active CATIA document."""
        self.ensure_connected()
        try:
            return self.app.ActiveDocument
        except Exception:
            raise RuntimeError("No active document in CATIA. Create or open a document first.")

    @property
    def active_editor(self) -> Any:
        """Get the active editor."""
        self.ensure_connected()
        return self.app.ActiveEditor

    @property
    def hso(self) -> Any:
        """Get the Highlighted Set of Objects (selection)."""
        self.ensure_connected()
        return self.active_document.Selection

    def refresh_display(self) -> None:
        """Refresh the CATIA 3D view."""
        try:
            self.active_editor.ActiveViewer.Reframe()
        except Exception:
            pass

    # ── Document type detection ──

    def get_active_part(self) -> Any:
        """Get the Part object from the active PartDocument."""
        doc = self.active_document
        try:
            return doc.Part
        except Exception:
            raise RuntimeError(
                "Active document is not a Part document. "
                "Open or create a Part document first."
            )

    def get_active_product(self) -> Any:
        """Get the Product object from the active ProductDocument."""
        doc = self.active_document
        try:
            return doc.Product
        except Exception:
            raise RuntimeError(
                "Active document is not a Product document. "
                "Open or create an Assembly (Product) document first."
            )

    def get_active_part_body(self) -> Any:
        """Get the main PartBody from the active Part document."""
        part = self.get_active_part()
        return part.MainBody

    def get_origin_elements(self) -> dict[str, Any]:
        """Get the origin planes (XY, YZ, ZX) from the active Part."""
        part = self.get_active_part()
        origin = part.OriginElements
        return {
            "xy": origin.PlaneXY,
            "yz": origin.PlaneYZ,
            "zx": origin.PlaneZX,
        }
