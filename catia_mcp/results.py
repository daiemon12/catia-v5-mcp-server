"""Structured operation results for the CAA adapter and server failures."""
from __future__ import annotations

from typing import Any
from uuid import uuid4


def operation_result(*, tool: str, ok: bool, code: str, message: str,
                     data: dict[str, Any], modified: bool | None,
                     operation_id: str | None = None,
                     diagnostics: list[dict[str, Any]] | None = None,
                     warnings: list[str] | None = None) -> dict[str, Any]:
    if modified is None:
        next_actions = ["Inspect CATIA and the pending Bridge request before restarting MCP"]
    elif not ok and modified:
        next_actions = ["Inspect partial model changes; recovery is manual"]
    else:
        next_actions = []
    return {
        "ok": ok,
        "code": code,
        "operation_id": operation_id or uuid4().hex,
        "tool": tool,
        "message": message,
        "data": data,
        "effects": {"modified": modified},
        "diagnostics": diagnostics or [],
        "warnings": warnings or [],
        "recovery": {
            "rollback_supported": False,
            "automatic_retry_allowed": False,
            "next_actions": next_actions,
        },
    }
