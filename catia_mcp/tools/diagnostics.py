"""Diagnostics tool for CATIA V5 installations.

Reports the exact CATIA release, and probes which automation APIs the
running installation currently resolves. Installations differ: old
releases lack some APIs entirely, and configurations without certain
products/licenses (including floating licenses currently in use by
others) may not expose or honor factory creation methods. The probes
test COM name resolution under the server's late-bound dispatch; a
method that resolves can still fail at call time if a license is
missing, so treat results as strong hints, not proof. This tool turns "what CATIA do you have and what
works on it" into a single call whose JSON output can be pasted into a
compatibility report or GitHub issue.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from catia_mcp.connection import CATIAConnection

# Factory methods probed on an active Part document. These lists mirror
# the methods the real tools call, so a probe that fails here fails the
# same way in the corresponding tool.
_SHAPE_FACTORY_METHODS = [
    "AddNewPad",
    "AddNewPocket",
    "AddNewShaft",
    "AddNewGroove",
    "AddNewSolidEdgeFilletWithConstantRadius",
    "AddNewChamfer",
    "AddNewHole",
    "AddNewRectPattern",
    "AddNewCircPattern",
    "AddNewMirror",
    "AddNewShell",
    "AddNewDraft",
    "AddNewThickness",
    "AddNewThickSurface",
    "AddNewCloseSurface",
]

_HYBRID_SHAPE_FACTORY_METHODS = [
    "AddNewPointCoord",
    "AddNewLinePtPt",
    "AddNewPlaneOffset",
    "AddNewPlane3Points",
    "AddNewSpline",
    "AddNewCircleCtrRad",
    "AddNewDirectionByCoord",
    "AddNewProject",
    "AddNewIntersection",
    "AddNewLoft",
    "AddNewSweepExplicit",
    "AddNewExtrude",
    "AddNewRevol",
    "AddNewFill",
    "AddNewBlend",
    "AddNewOffset",
    "AddNewJoin",
    "AddNewHybridSplit",
    "AddNewHybridTrim",
    "AddNewSymmetry",
]


class DiagnosticsTools:
    """Diagnostics for the running CATIA installation."""

    def __init__(self, connection: CATIAConnection) -> None:
        self.conn = connection

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "catia_diagnose",
                "description": (
                    "Diagnose the running CATIA V5 installation: exact version, "
                    "release and service pack, Python/pywin32 environment, and a "
                    "probe of which automation APIs (Part Design ShapeFactory, "
                    "GSD HybridShapeFactory, SPAWorkbench measurement) are "
                    "actually exposed. Run this first when tools fail with "
                    "UNSUPPORTED_CAPABILITY, and include its output when "
                    "reporting compatibility issues. Probing factories requires "
                    "an active Part document; without one, only "
                    "application-level info is reported."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        match tool_name:
            case "catia_diagnose":
                return self._diagnose()
            case _:
                raise ValueError(f"Unknown diagnostics tool: {tool_name}")

    def _diagnose(self) -> str:
        self.conn.ensure_connected()
        app = self.conn.app

        report: dict[str, Any] = {"python": self._python_info(app)}
        report["catia"] = self._catia_info(app)
        report["workbenches"] = self._workbench_probe()
        report["factories"] = self._factory_probe()
        report["notes"] = self._notes(report)

        return json.dumps(report, indent=2)

    def _python_info(self, app: Any) -> dict[str, Any]:
        info: dict[str, Any] = {
            "python_version": sys.version.split()[0],
            "com_binding": type(app).__name__,
        }
        try:
            import win32com

            info["pywin32_build"] = getattr(win32com, "__build__", "unknown")
            gen_path = getattr(win32com, "__gen_path__", None)
            if gen_path:
                info["gen_py_cache"] = gen_path
                try:
                    info["gen_py_entries"] = len(os.listdir(gen_path))
                except Exception:
                    pass
        except Exception:
            info["pywin32_build"] = "unavailable"
        return info

    def _catia_info(self, app: Any) -> dict[str, Any]:
        info: dict[str, Any] = {}
        try:
            info["caption"] = app.Caption
        except Exception:
            pass
        try:
            conf = app.SystemConfiguration
            info["version"] = conf.Version
            info["release"] = conf.Release
            info["service_pack"] = conf.ServicePack
        except Exception as e:
            info["system_configuration_error"] = str(e)
        try:
            info["full_name"] = app.FullName
        except Exception:
            pass
        return info

    def _workbench_probe(self) -> dict[str, str]:
        # GetWorkbench is a Document method in the V5 automation model, so
        # probing needs an open document. SPAWorkbench is what the
        # measurement tools rely on. Note that "PartDesign" is NOT a valid
        # GetWorkbench id: Part Design is reached through Part.ShapeFactory,
        # so a GetWorkbench("PartDesign") failure proves nothing.
        try:
            doc = self.conn.active_document
        except Exception:
            doc = None
        if doc is None:
            return {
                "skipped": (
                    "No active document. Open or create one, then run "
                    "catia_diagnose again to probe workbenches."
                )
            }
        probes = {}
        for wb in ("SPAWorkbench",):
            try:
                doc.GetWorkbench(wb)
                probes[wb] = "available"
            except Exception as e:
                probes[wb] = f"unavailable: {e}"
        return probes

    def _factory_probe(self) -> dict[str, Any]:
        result: dict[str, Any] = {}

        doc = None
        try:
            doc = self.conn.active_document
        except Exception:
            pass
        part = None
        if doc is not None:
            try:
                part = doc.Part
            except Exception:
                pass
        if part is None:
            result["skipped"] = (
                "No active Part document. Create or open a CATPart, then run "
                "catia_diagnose again to probe the factories."
            )
            return result

        result["shape_factory"] = self._probe_methods(
            part, "ShapeFactory", _SHAPE_FACTORY_METHODS
        )
        result["hybrid_shape_factory"] = self._probe_methods(
            part, "HybridShapeFactory", _HYBRID_SHAPE_FACTORY_METHODS
        )
        return result

    def _probe_methods(
        self, part: Any, factory_attr: str, methods: list[str]
    ) -> dict[str, Any]:
        probe: dict[str, Any] = {}
        try:
            factory = getattr(part, factory_attr)
        except Exception as e:
            probe["factory"] = f"unavailable: {e}"
            return probe

        probe["factory"] = "available"
        exposed: list[str] = []
        missing: list[str] = []
        errored: dict[str, str] = {}
        for m in methods:
            # getattr resolution mirrors how the real tools reach these
            # methods under late-bound dispatch (it does not invoke them).
            try:
                getattr(factory, m)
                exposed.append(m)
            except AttributeError:
                missing.append(m)
            except Exception as e:
                errored[m] = str(e)
        probe["exposed_methods"] = exposed
        probe["missing_methods"] = missing
        if errored:
            probe["errored_methods"] = errored
        return probe

    def _notes(self, report: dict[str, Any]) -> list[str]:
        notes: list[str] = []
        factories = report.get("factories", {})
        labels = {
            "shape_factory": ("ShapeFactory", "Part Design (MD2/PD1 level)"),
            "hybrid_shape_factory": (
                "HybridShapeFactory",
                "Generative Shape Design (GS1/GSD level)",
            ),
        }
        for key, (name, lic) in labels.items():
            probe = factories.get(key, {})
            status = probe.get("factory", "")
            if status.startswith("unavailable"):
                notes.append(
                    f"{name} itself is not reachable on this installation "
                    f"({status}). The corresponding tools will fail."
                )
            elif probe.get("missing_methods"):
                notes.append(
                    f"{name} exists but some creation methods did not "
                    "resolve. Field-confirmed first suspect: a stale "
                    "pywin32 gen_py cache (close CATIA and the server, "
                    "delete the %TEMP%\\gen_py folder, restart, re-run "
                    "catia_diagnose). Otherwise the " + lic + " license "
                    "may not be active right now (floating licenses come "
                    "and go during the day) or the release predates the "
                    "API. Check Tools > Options > Licensing and compare "
                    "two catia_diagnose runs."
                )
            if probe.get("errored_methods"):
                notes.append(
                    f"Some {name} probes errored (neither exposed nor "
                    "cleanly missing); include this report in a GitHub "
                    "issue."
                )
        wb = report.get("workbenches", {})
        for wb_name, status in wb.items():
            if wb_name != "skipped" and str(status).startswith("unavailable"):
                notes.append(
                    f"{wb_name} is unavailable; measurement tools "
                    "(distance, inertia, bounding box) will fail."
                )
        release = report.get("catia", {}).get("release")
        if isinstance(release, int) and release < 26:
            notes.append(
                f"CATIA release R{release} is older than the project's "
                "tested baseline (R2016 = R26). Core document/sketch/GSD "
                "tools are known to work on V5R20, but expect gaps; please "
                "report your results in a GitHub issue."
            )
        if not notes:
            notes.append("No compatibility concern detected by the probes.")
        return notes
