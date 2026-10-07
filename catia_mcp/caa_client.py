"""MCP preflight and results for the bundled Point-only CAA protocol."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator

from .caa.client import CatiaCaaBridgeClient
from .caa.runtime_manifest import verify_files, DLL_NAMES
from .results import operation_result

METHOD = "catia_caa_demo_create_point"
SCHEMA = json.loads(Path(__file__).with_name("caa_point.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


class CaaPreflightError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def validate_params(params: dict[str, Any]) -> None:
    VALIDATOR.validate(params)
    if any(not math.isfinite(params[key]) for key in ("x_mm", "y_mm", "z_mm")):
        raise ValueError("Coordinates must be finite")


def configured_runtime() -> Path:
    value = os.environ.get("CATIA_MCP_CAA_RUNTIME")
    if not value:
        raise CaaPreflightError("CAA_BRIDGE_UNAVAILABLE", "Set CATIA_MCP_CAA_RUNTIME to the built Point runtime directory")
    runtime = Path(value).expanduser()
    if not runtime.is_absolute() or not runtime.is_dir():
        raise CaaPreflightError("CAA_BRIDGE_UNAVAILABLE", "CATIA_MCP_CAA_RUNTIME must be an existing absolute directory")
    runtime = runtime.resolve()
    verify_files(runtime)
    return runtime


def verify_runtime(pid: int, runtime: Path, *, preview: bool = False) -> None:
    """Verify the actual loaded modules, not just files on disk."""
    import win32api
    import win32con
    import win32process

    verify_files(runtime)
    handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
    try:
        loaded = {}
        for module in win32process.EnumProcessModules(handle):
            path = Path(win32process.GetModuleFileNameEx(handle, module))
            if path.name in DLL_NAMES:
                loaded[path.name] = path.resolve()
        for name in DLL_NAMES:
            expected_path = (runtime / "code/bin" / name).resolve()
            # CATCommandHeader loads the command DLL on first invocation. A
            # read-only preview may load it; writes require it already verified.
            if preview and name == "CatiaPyBridgeCmdModule.dll" and name not in loaded:
                continue
            if loaded.get(name) != expected_path:
                raise CaaPreflightError("CAA_BRIDGE_MISMATCH", f"CATIA must load {name} from the configured Point runtime")
    finally:
        win32api.CloseHandle(handle)


def create_point(connection, params: dict[str, Any]) -> dict[str, Any]:
    """Preflight cannot write; after delivery unknown mutation state stays null."""
    stage = "validate"
    operation_id = uuid4().hex
    modified = None
    try:
        validate_params(params)
        stage = "dependency"
        runtime = configured_runtime()
        stage = "attach"
        app = connection.attach_caa(params["catia_process_id"])
        stage = "runtime"
        verify_runtime(params["catia_process_id"], runtime, preview=params.get("dry_run", True))
        stage = "transport"
        data = CatiaCaaBridgeClient(catia=app, operation_id=operation_id).demo_create_point(**params)
        modified = data.get("modified")
        stage = "postflight"
        verify_runtime(params["catia_process_id"], runtime)
        result = operation_result(tool=METHOD, ok=True, code="OK", data=data,
                                  modified=modified, operation_id=operation_id,
                                  message="Point CAA operation completed",
                                  warnings=["Experimental B30 probe; object handles and automatic rollback are unsupported"])
        result["effects"].update({key: data[key] for key in
                                  ("created", "saved", "coordinates_mm", "coordinate_system") if key in data})
        return result
    except Exception as error:
        detail = getattr(error, "detail", None)
        try:
            evidence = json.loads(detail) if detail else {}
            if not isinstance(evidence, dict):
                evidence = {"detail": detail}
        except (TypeError, ValueError):
            evidence = {"detail": detail}
        evidence.setdefault("failure_stage", stage)
        evidence.setdefault("modified", modified if stage in {"transport", "postflight"} else False)
        code = getattr(error, "code", None)
        if code is None:
            if stage == "validate":
                code = "INVALID_ARGUMENT"
            elif isinstance(error, TimeoutError):
                code = "COM_TIMEOUT"
            elif stage == "transport":
                code = "BRIDGE_PROTOCOL_ERROR"
            elif stage == "attach":
                code = "NOT_CONNECTED"
            else:
                code = "CAA_BRIDGE_MISMATCH"
        return operation_result(tool=METHOD, ok=False, code=code,
                                message=str(error), data=evidence,
                                modified=evidence["modified"], operation_id=operation_id,
                                diagnostics=[{"code": code, "stage": evidence["failure_stage"], "detail": evidence}],
                                warnings=["Automatic rollback is unsupported; preserve any partial native modification"])
