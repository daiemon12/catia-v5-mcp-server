"""CATIA COM connection manager for CATIA V5 and CATIA 3DEXPERIENCE (V6).

Both platforms register the same COM ProgID, "CATIA.Application", so the
attach logic is shared. What differs is the object model behind it:

- CATIA V5 is file based: Application.Documents, ActiveDocument.Part,
  ActiveDocument.Selection, Document.GetWorkbench("SPAWorkbench").
- 3DEXPERIENCE is PLM based: content lives in the 3DSpace database and is
  shown in Editors. Application.ActiveEditor.ActiveObject is the Part (3D
  Shape level) or a VPMRootOccurrence (3D Part / Physical Product level),
  the selection belongs to the Editor, and creating, opening and saving go
  through session services (PLMNewService, PLMOpenService,
  PLMPropagateService, Search).

The platform is detected once per connection (override with the
CATIA_MCP_PLATFORM environment variable or --platform: auto, v5, 3dx).
Tools ask this class for the active Part, body, selection or window and
never need to know which object model produced them.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from catia_mcp.automation import get_member, iter_items, name_exists, resolves, safe_get
from catia_mcp.errors import (
    InvalidArgument,
    NoActiveDocument,
    ObjectNotFound,
    WrongDocumentType,
)

logger = logging.getLogger("catia_mcp")

# COM imports are deferred to runtime (Windows only)
try:
    import pythoncom
    import win32com.client

    HAS_COM = True
except ImportError:
    HAS_COM = False

PLATFORM_V5 = "v5"
PLATFORM_3DX = "3dx"
PLATFORM_LABELS = {PLATFORM_V5: "CATIA V5", PLATFORM_3DX: "CATIA 3DEXPERIENCE"}
_PLATFORM_ALIASES = {
    "auto": None, "": None,
    "v5": PLATFORM_V5,
    "3dx": PLATFORM_3DX, "3dexperience": PLATFORM_3DX, "v6": PLATFORM_3DX,
}


def normalize_platform(value: str | None) -> str | None:
    key = (value or "auto").strip().lower()
    if key not in _PLATFORM_ALIASES:
        raise ValueError(
            f"Unknown CATIA platform '{value}'. Use auto, v5 or 3dx (3DEXPERIENCE)."
        )
    return _PLATFORM_ALIASES[key]


class CATIAConnection:
    """Manages the connection to CATIA V5 or 3DEXPERIENCE via COM Automation."""

    # Both CATIA V5 and 3DEXPERIENCE register this ProgID.
    CATIA_PROGID = "CATIA.Application"

    def __init__(self, platform: str | None = None) -> None:
        self.app: Any | None = None
        self._initialized_com = False
        self._forced_platform = normalize_platform(
            platform if platform is not None else os.environ.get("CATIA_MCP_PLATFORM")
        )
        self.platform: str | None = None
        # Part key -> body name selected with catia_set_active_body.
        self._active_bodies: dict[str, str] = {}

    # ── Connection lifecycle ──

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
            self.platform = None
            return False

    @property
    def is_3dx(self) -> bool:
        return self.platform == PLATFORM_3DX

    @property
    def platform_label(self) -> str:
        return PLATFORM_LABELS.get(self.platform or "", "CATIA (platform not detected yet)")

    def connect(self) -> str:
        """Connect to CATIA. Tries a running instance first, then launches one.

        Returns a status message string.
        """
        if not HAS_COM:
            raise RuntimeError(
                "pywin32 is not installed. Install it with: pip install pywin32\n"
                "Note: This MCP server requires Windows with CATIA V5 or "
                "CATIA 3DEXPERIENCE installed."
            )

        if self.is_connected:
            version = self._get_version()
            return f"Already connected to {self.platform_label} ({version})"

        # Initialize COM for this thread
        if not self._initialized_com:
            pythoncom.CoInitialize()
            self._initialized_com = True

        # Phase 1: Try to attach to a running CATIA instance
        try:
            self.app = win32com.client.GetActiveObject(self.CATIA_PROGID)
            self.platform = self._detect_platform()
            version = self._get_version()
            logger.info("Connected to running %s instance (%s)", self.platform_label, version)
            return f"Connected to running {self.platform_label} instance ({version})"
        except Exception:
            logger.info("No running CATIA instance found, launching new one...")

        # Phase 2: Launch a new CATIA instance
        try:
            self.app = win32com.client.Dispatch(self.CATIA_PROGID)
            self.app.Visible = True
            self.platform = self._detect_platform()
            version = self._get_version()
            logger.info("Launched new %s instance (%s)", self.platform_label, version)
            note = ""
            if self.is_3dx:
                note = (
                    " Log in to the 3DEXPERIENCE platform in that window before "
                    "creating or opening content."
                )
            return f"Launched new {self.platform_label} instance ({version}).{note}"
        except Exception as e:
            self.app = None
            self.platform = None
            raise RuntimeError(
                f"Failed to connect to CATIA: {e}\n"
                "Make sure CATIA V5 or CATIA 3DEXPERIENCE is installed, licensed and "
                "registered as COM server (V5: cnext.exe /regserver from code\\bin; "
                "3DEXPERIENCE: start the native app once from the launcher). For "
                "3DEXPERIENCE, start CATIA and log in before connecting."
            ) from e

    def disconnect(self) -> str:
        """Disconnect from CATIA (does not close CATIA)."""
        if self.app is not None:
            self.app = None
        self.platform = None
        if self._initialized_com:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._initialized_com = False
        return "Disconnected from CATIA"

    def ensure_connected(self) -> None:
        """Ensure we have an active CATIA connection, connecting if needed."""
        if not self.is_connected:
            self.connect()

    def _detect_platform(self) -> str:
        if self._forced_platform:
            return self._forced_platform
        app = self.app
        # Session services and editors exist only in the 3DEXPERIENCE object
        # model; the name check does not invoke the method.
        if name_exists(app, "GetSessionService") or name_exists(app, "ActiveEditor"):
            return PLATFORM_3DX
        try:
            if int(app.SystemConfiguration.Version) >= 6:
                return PLATFORM_3DX
        except Exception:
            pass
        try:
            if "3DEXPERIENCE" in str(app.Caption).upper():
                return PLATFORM_3DX
        except Exception:
            pass
        return PLATFORM_V5

    def _get_version(self) -> str:
        """Get CATIA version string."""
        try:
            caption = self.app.Caption
            return caption if caption else "unknown version"
        except Exception:
            return "unknown version"

    # ── Platform services (3DEXPERIENCE) ──

    def session_service(self, name: str) -> Any:
        """A 3DEXPERIENCE session service (PLMNewService, Search, ...)."""
        self.ensure_connected()
        return self.app.GetSessionService(name)

    @property
    def active_editor(self) -> Any:
        """The 3DEXPERIENCE active Editor."""
        self.ensure_connected()
        try:
            editor = self.app.ActiveEditor
        except Exception:
            editor = None
        if editor is None:
            raise NoActiveDocument(
                "No active editor in CATIA 3DEXPERIENCE. Create content with "
                "catia_new_part / catia_new_product / catia_new_drawing or open it "
                "with catia_open_from_database first."
            )
        return editor

    def editor_service(self, name: str, editor: Any | None = None) -> Any:
        """A 3DEXPERIENCE editor-level service (MeasurableService, ...)."""
        return (editor or self.active_editor).GetService(name)

    # ── Helper properties for quick access to CATIA objects ──

    @property
    def documents(self) -> Any:
        """Get the CATIA V5 Documents collection."""
        self.ensure_connected()
        return self.app.Documents

    @property
    def active_document(self) -> Any:
        """The active V5 document, or the active Editor on 3DEXPERIENCE.

        Both expose Selection; document-only members (Name, FullName,
        Save, ExportData) must not be used on the 3DEXPERIENCE path.
        """
        self.ensure_connected()
        if self.is_3dx:
            return self.active_editor
        try:
            return self.app.ActiveDocument
        except Exception:
            raise NoActiveDocument(
                "No active document in CATIA. Create or open a document first."
            )

    @property
    def active_window(self) -> Any:
        """Get the active window (exists on both platforms)."""
        self.ensure_connected()
        return self.app.ActiveWindow

    @property
    def hso(self) -> Any:
        """Get the Highlighted Set of Objects (selection)."""
        self.ensure_connected()
        return self.active_document.Selection

    def refresh_display(self) -> None:
        """Refresh the CATIA 3D view."""
        try:
            self.active_window.ActiveViewer.Reframe()
        except Exception:
            pass

    def active_object(self) -> Any:
        """The 3DEXPERIENCE active editor's ActiveObject."""
        try:
            obj = self.active_editor.ActiveObject
        except NoActiveDocument:
            raise
        except Exception:
            obj = None
        if obj is None:
            raise NoActiveDocument("The active 3DEXPERIENCE editor shows no object.")
        return obj

    @staticmethod
    def classify(obj: Any) -> str:
        """Classify a 3DEXPERIENCE editor object: part, product, drawing, other."""
        if obj is None:
            return "none"
        if resolves(obj, "ShapeFactory"):
            return "part"
        if resolves(obj, "Sheets"):
            return "drawing"
        if resolves(obj, "ReferenceRootOccurrenceOf") or resolves(obj, "RepInstances"):
            return "product"
        return "other"

    def active_object_kind(self) -> str:
        """Classify the 3DEXPERIENCE active object: part, product, drawing, other."""
        return self.classify(self.active_object())

    # ── Part resolution ──

    @staticmethod
    def part_from_reference(reference: Any) -> Any | None:
        """Part of a VPMReference's first 3D Shape representation, if any.

        Path field-documented for 3DEXPERIENCE: VPMReference.RepInstances
        -> VPMRepInstance.ReferenceInstanceOf -> VPMRepReference.GetItem("Part").
        A reference may hold several representations (shape, drawing), so
        each is tried in order.
        """
        try:
            reps = reference.RepInstances
        except Exception:
            return None
        for rep_instance in iter_items(reps):
            rep_ref = safe_get(rep_instance, "ReferenceInstanceOf")
            if rep_ref is None:
                continue
            try:
                part = rep_ref.GetItem("Part")
            except Exception:
                continue
            if part is not None and resolves(part, "ShapeFactory"):
                return part
        return None

    def _part_3dx(self) -> Any:
        obj = self.active_object()
        if resolves(obj, "ShapeFactory"):
            # 3D Shape level: the ActiveObject is the Part itself.
            return obj
        reference = None
        if resolves(obj, "ReferenceRootOccurrenceOf"):
            reference = get_member(obj, "ReferenceRootOccurrenceOf")
        elif resolves(obj, "RepInstances"):
            reference = obj
        if reference is not None:
            part = self.part_from_reference(reference)
            if part is not None:
                return part
            raise WrongDocumentType(
                "The active editor shows a Physical Product without a 3D Shape "
                "representation of its own. Open or create a 3D Part / 3D Shape "
                "(catia_new_part) or open the part in its own editor."
            )
        if resolves(obj, "Sheets"):
            raise WrongDocumentType(
                "The active editor shows a Drawing, not a Part. Activate the part's "
                "window with catia_activate_document."
            )
        raise WrongDocumentType(
            "The active 3DEXPERIENCE editor does not show a 3D Part or 3D Shape."
        )

    def get_active_part(self) -> Any:
        """Get the Part object of the active document / editor."""
        if self.is_3dx:
            return self._part_3dx()
        doc = self.active_document
        try:
            return doc.Part
        except Exception:
            raise WrongDocumentType(
                "Active document is not a Part document. "
                "Open or create a Part document first."
            )

    def get_active_product(self) -> Any:
        """V5: the active Product. 3DEXPERIENCE: the root VPMOccurrence."""
        if self.is_3dx:
            return self.root_occurrence()
        doc = self.active_document
        try:
            return doc.Product
        except Exception:
            raise WrongDocumentType(
                "Active document is not a Product document. "
                "Open or create an Assembly (Product) document first."
            )

    def root_occurrence(self, editor: Any | None = None) -> Any:
        """3DEXPERIENCE root occurrence of an editor's product structure."""
        editor = editor or self.active_editor
        for service in ("PLMProductService", "PLMProductContext"):
            try:
                root = editor.GetService(service).RootOccurrence
            except Exception:
                continue
            if root is not None:
                return root
        try:
            obj = editor.ActiveObject
        except Exception:
            obj = None
        if obj is not None and resolves(obj, "ReferenceRootOccurrenceOf"):
            return obj
        raise WrongDocumentType(
            "The active editor shows no product structure (3D Part or Physical "
            "Product). Open one with catia_open_from_database."
        )

    # ── Bodies ──

    @staticmethod
    def part_key(part: Any) -> str:
        """Stable-enough identity of a Part for per-part session state."""
        parent = safe_get(part, "Parent")
        for getter in (
            lambda: parent.GetAttributeValue("PLM_ExternalID"),
            lambda: parent.FullName,
            lambda: parent.Name,
        ):
            try:
                value = getter()
            except Exception:
                continue
            if value:
                return f"{value}|{safe_get(part, 'Name', '')}"
        return str(safe_get(part, "Name", "part"))

    def set_active_body(self, body_name: str | None) -> Any:
        """Select the body that receives new sketches and features
        (None resets to the part's main body)."""
        part = self.get_active_part()
        key = self.part_key(part)
        if not body_name:
            self._active_bodies.pop(key, None)
            body = part.MainBody
        else:
            bodies = part.Bodies
            try:
                body = bodies.Item(body_name)
            except Exception:
                names = ", ".join(str(b.Name) for b in iter_items(bodies))
                raise ObjectNotFound(
                    f"No body named '{body_name}'. Top-level bodies: {names or 'none'}."
                )
            self._active_bodies[key] = str(body.Name)
        try:
            part.InWorkObject = body
        except Exception:
            pass
        return body

    def get_active_part_body(self) -> Any:
        """The body that receives new features: the one chosen with
        catia_set_active_body for this part, else the part's MainBody."""
        part = self.get_active_part()
        key = self.part_key(part)
        name = self._active_bodies.get(key)
        if name:
            try:
                return part.Bodies.Item(name)
            except Exception:
                self._active_bodies.pop(key, None)
                raise ObjectNotFound(
                    f"The active body '{name}' no longer exists in this part (deleted "
                    "or renamed). New features would land elsewhere, so nothing was "
                    "done. Call catia_set_active_body to choose a body."
                )
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

    def require_platform(self, platform: str, tool: str) -> None:
        if self.platform != platform:
            raise InvalidArgument(
                f"{tool} is only available on {PLATFORM_LABELS[platform]}; the "
                f"connected session is {self.platform_label}."
            )
