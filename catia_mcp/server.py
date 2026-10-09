"""MCP transport with one shared CATIA connection and one serial STA worker."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from jsonschema import ValidationError, validate
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from catia_mcp.connection import CATIAConnection
from catia_mcp.results import operation_result
from catia_mcp.tools.assembly import AssemblyTools
from catia_mcp.tools.diagnostics import DiagnosticsTools
from catia_mcp.tools.document import DocumentTools
from catia_mcp.tools.drawing import DraftingTools
from catia_mcp.tools.export import ExportTools
from catia_mcp.tools.gsd import GSDTools
from catia_mcp.tools.knowledge import KnowledgeTools
from catia_mcp.tools.measurement import MeasurementTools
from catia_mcp.tools.part_design import PartDesignTools
from catia_mcp.tools.sketcher import SketcherTools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "catia_mcp.log"),
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("catia_mcp")


def structured_result(data: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(
                type="text", text=json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)
            )
        ],
        structuredContent=data,
        isError=data.get("ok") is not True,
    )


def failure(
    code: str, message: str, stage: str, modified: bool | None, tool: str
) -> CallToolResult:
    return structured_result(
        operation_result(
            tool=tool,
            ok=False,
            code=code,
            message=message,
            data={"failure_stage": stage},
            modified=modified,
        )
    )


class CATIAMCPServer:
    def __init__(self) -> None:
        self.server = Server("catia-v5-mcp")
        self.connection = CATIAConnection()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="catia-sta")
        self.document_tools = DocumentTools(self.connection)
        self.sketcher_tools = SketcherTools(self.connection)
        self.part_design_tools = PartDesignTools(self.connection)
        self.gsd_tools = GSDTools(self.connection)
        self.diagnostics_tools = DiagnosticsTools(self.connection)
        self.drafting_tools = DraftingTools(self.connection)
        self.knowledge_tools = KnowledgeTools(self.connection)
        self.assembly_tools = AssemblyTools(self.connection)
        self.measurement_tools = MeasurementTools(self.connection)
        self.export_tools = ExportTools(self.connection)
        self._tool_modules = [
            self.document_tools,
            self.sketcher_tools,
            self.part_design_tools,
            self.gsd_tools,
            self.diagnostics_tools,
            self.drafting_tools,
            self.knowledge_tools,
            self.assembly_tools,
            self.measurement_tools,
            self.export_tools,
        ]
        self._tool_router: dict[str, Any] = {}
        self._schemas: dict[str, dict] = {}
        for module in self._tool_modules:
            for definition in module.get_tool_definitions():
                name = definition["name"]
                if name in self._tool_router:
                    raise ValueError(f"Duplicate tool: {name}")
                self._tool_router[name] = module
                self._schemas[name] = definition["inputSchema"]
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return [
                Tool(**definition)
                for module in self._tool_modules
                for definition in module.get_tool_definitions()
            ]

        @self.server.call_tool(validate_input=False)
        async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
            return await self.call_tool(name, arguments or {})

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        future = asyncio.get_running_loop().run_in_executor(
            self._executor, self._execute_tool, name, arguments
        )
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            future.add_done_callback(
                lambda completed: completed.exception() if not completed.cancelled() else None
            )
            raise

    def _execute_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        module = self._tool_router.get(name)
        if module is None:
            return failure("UNKNOWN_TOOL", f"Unknown tool: {name}", "validate", False, name)
        try:
            validate(arguments, self._schemas[name])
        except ValidationError as error:
            return failure("INVALID_ARGUMENT", error.message, "validate", False, name)
        logger.info("Tool call: %s(%s)", name, arguments)
        stage = "connect"
        try:
            if name not in {"catia_connect", "catia_disconnect"}:
                self.connection.ensure_connected()
            stage = "connect" if name == "catia_connect" else "execute"
            result = module.execute(name, arguments)
            if isinstance(result, dict):
                logger.info("Tool result: %s %s", name, result.get("code"))
                return structured_result(result)
            logger.info("Tool result: %s", result[:200])
            return CallToolResult(content=[TextContent(type="text", text=result)])
        except Exception as error:
            logger.exception("Tool failed: %s: %s", name, error)  # noqa: TRY401 -- log preview includes the error message
            code = "UNSUPPORTED_CAPABILITY" if isinstance(error, AttributeError) else "COM_ERROR"
            message = str(error)
            if code == "UNSUPPORTED_CAPABILITY":
                message = (
                    f"UNSUPPORTED_CAPABILITY in {name}: the required CATIA automation API "
                    f"did not resolve ({error}). The API may be absent from this CATIA release, "
                    "or a stale pywin32 gen_py cache may be blocking resolution. Clearing caches "
                    "cannot add an absent API. For a stale cache, close CATIA and the server, "
                    "delete the %TEMP%\\gen_py folder, restart and retry once. A missing "
                    "workbench licence can also lock methods. Run catia_diagnose for details."
                )
            return failure(code, message, stage, False if stage == "connect" else None, name)

    async def close(self) -> None:
        try:
            await asyncio.get_running_loop().run_in_executor(
                self._executor, self.connection.disconnect
            )
        finally:
            self._executor.shutdown(wait=True)

    async def run(self) -> None:
        logger.info("Starting CATIA V5 MCP Server: %d tools", len(self._tool_router))
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream, write_stream, self.server.create_initialization_options()
                )
        finally:
            await self.close()


def main() -> None:
    asyncio.run(CATIAMCPServer().run())


if __name__ == "__main__":
    main()
