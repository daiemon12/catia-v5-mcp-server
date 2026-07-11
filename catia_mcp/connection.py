"""CATIA V5 COM Connection Manager.

Manages the connection to CATIA V5 via Windows COM Automation API (win32com).
Supports connecting to a running instance or launching a new one.
"""

from __future__ import annotations

import logging
import os
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

    def __init__(self, host: str | None = None) -> None:
        # Remote machine for DCOM activation. Empty/unset means local.
        self.host = host if host is not None else os.environ.get("CATIA_HOST", "").strip()
        # Explicit CLSID for remote activation. The ProgID "CATIA.Application"
        # can only be resolved on a machine where CATIA is installed, so when
        # this client machine has no CATIA, the remote class GUID must be
        # supplied (read it on the CATIA machine: reg query HKCR\CATIA.Application\CLSID).
        self.clsid = os.environ.get("CATIA_CLSID", "").strip()
        # Credentials for remote DCOM. pywin32 cannot pass credentials to the
        # activation call itself, so we impersonate with a network-only logon
        # (LOGON32_LOGON_NEW_CREDENTIALS): local execution stays under the
        # current user, but all outgoing network auth uses these credentials.
        self.user = os.environ.get("CATIA_USER", "").strip()
        self.password = os.environ.get("CATIA_PASSWORD", "")
        self.app: Any | None = None
        self._initialized_com = False
        self._impersonating = False
        self.active_geoset_name: str | None = None

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

        # Remote host: activate CATIA on another machine via DCOM.
        # GetActiveObject only works locally, so DispatchEx is the only option here.
        if self.host:
            if self.user and not self._impersonating:
                self._impersonate_network_credentials()
            try:
                self.app = win32com.client.DispatchEx(
                    self.clsid or self.CATIA_PROGID, machine=self.host
                )
                self.app.Visible = True
                version = self._get_version()
                logger.info(
                    "Connected to CATIA V5 on %s via DCOM (%s)", self.host, version
                )
                return f"Connected to CATIA V5 on {self.host} via DCOM ({version})"
            except Exception as e:
                self.app = None
                hint = (
                    "The ProgID cannot be resolved because CATIA is not "
                    "installed on this client machine. Set CATIA_CLSID to the "
                    "class GUID from the CATIA machine (run there: "
                    "reg query HKCR\\CATIA.Application\\CLSID).\n"
                    if not self.clsid
                    else ""
                )
                raise RuntimeError(
                    f"Failed to connect to CATIA V5 on {self.host} via DCOM: {e}\n"
                    f"{hint}"
                    "Check that: (1) CATIA is registered as a COM server on the "
                    "remote machine (cnext.exe /regserver), (2) DCOM remote "
                    "activation/access is granted to your user (dcomcnfg), "
                    "(3) firewall allows DCOM (TCP 135 + dynamic RPC ports), "
                    "(4) both machines share credentials (same domain user)."
                ) from e

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

    def _impersonate_network_credentials(self) -> None:
        """Impersonate CATIA_USER for network calls only (DCOM auth).

        Uses LOGON32_LOGON_NEW_CREDENTIALS: the local security context is
        unchanged, but NTLM/Kerberos challenges from remote machines are
        answered with these credentials. Dynamic cloaking makes COM pick up
        the thread's impersonation token for activation and proxy calls, so
        the thread must stay impersonated for the lifetime of the connection.
        """
        import win32con
        import win32security

        # COM must use the thread token (cloaking), not the process token.
        # CoInitializeSecurity can only be called once per process; if COM
        # already initialized security implicitly, this raises and we proceed
        # (activation may then still fail with access denied).
        try:
            pythoncom.CoInitializeSecurity(
                None,
                None,
                None,
                pythoncom.RPC_C_AUTHN_LEVEL_DEFAULT,
                pythoncom.RPC_C_IMP_LEVEL_IMPERSONATE,
                None,
                pythoncom.EOAC_DYNAMIC_CLOAKING,
                None,
            )
        except pythoncom.com_error:
            logger.warning(
                "CoInitializeSecurity already called; cloaking may be unavailable"
            )

        domain, _, username = self.user.rpartition("\\")
        token = win32security.LogonUser(
            username,
            domain or None,
            self.password,
            win32con.LOGON32_LOGON_NEW_CREDENTIALS,
            win32con.LOGON32_PROVIDER_WINNT50,
        )
        win32security.ImpersonateLoggedOnUser(token)
        token.Close()
        self._impersonating = True
        logger.info("Impersonating %s for network calls to %s", self.user, self.host)

    def disconnect(self) -> str:
        """Disconnect from CATIA V5 (does not close CATIA)."""
        if self.app is not None:
            self.app = None
        if self._impersonating:
            try:
                import win32security

                win32security.RevertToSelf()
            except Exception:
                pass
            self._impersonating = False
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

    @property
    def hybrid_shape_factory(self) -> Any:
        """Return the active Part's GSD factory (raw COM object)."""
        return self.get_active_part().HybridShapeFactory

    @property
    def shape_factory(self) -> Any:
        """Return the active Part's solid feature factory.

        ShapeFactory is a property of Part, not Body — Body only exposes
        Shapes/Sketches. Calling .ShapeFactory on a Body raises a dynamic-
        dispatch AttributeError (pywin32 reports it as "<unknown>.ShapeFactory").
        """
        return self.get_active_part().ShapeFactory

    def pycatia_part_document(self) -> Any:
        """Wrap the active raw COM PartDocument for typed GSD adapters."""
        try:
            from pycatia.mec_mod_interfaces.part_document import PartDocument
        except ImportError as exc:
            raise RuntimeError("pycatia is required for GSD tools") from exc
        return PartDocument(self.active_document)
