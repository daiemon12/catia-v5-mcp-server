"""MCP transport with one shared CATIA connection and one serial STA worker."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
import sys
from typing import Any

from jsonschema import validate, ValidationError
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from catia_mcp.connection import CATIAConnection
from catia_mcp.results import operation_result
from catia_mcp.tools.assembly import AssemblyTools
from catia_mcp.tools.caa import CaaTools
from catia_mcp.tools.document import DocumentTools
from catia_mcp.tools.drawing import DraftingTools
from catia_mcp.tools.export import ExportTools
from catia_mcp.tools.diagnostics import DiagnosticsTools
from catia_mcp.tools.gsd import GSDTools
from catia_mcp.tools.knowledge import KnowledgeTools
from catia_mcp.tools.measurement import MeasurementTools
from catia_mcp.tools.part_design import PartDesignTools
from catia_mcp.tools.sketcher import SketcherTools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "catia_mcp.log"),
        encoding="utf-8"), logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("catia_mcp")


def structured_result(data: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False, allow_nan=False))],
        structuredContent=data, isError=data["ok"] is not True,
    )


def failure(code: str, message: str, stage: str, modified: bool | None, tool: str) -> CallToolResult:
    return structured_result(operation_result(tool=tool, ok=False, code=code, message=message,
                                             data={"failure_stage": stage}, modified=modified))


class CATIAMCPServer:
    def __init__(self) -> None:
        self.server = Server("catia-v5-mcp")
        self.connection = CATIAConnection()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="catia-sta")
        self._uncertain = False
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
        self.caa_tools = CaaTools(self.connection)
        self._tool_modules = [self.document_tools, self.sketcher_tools, self.part_design_tools,
                              self.gsd_tools, self.diagnostics_tools, self.drafting_tools,
                              self.knowledge_tools, self.assembly_tools, self.measurement_tools,
                              self.export_tools, self.caa_tools]
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
            return [Tool(**definition) for module in self._tool_modules
                    for definition in module.get_tool_definitions()]

        @self.server.call_tool(validate_input=False)
        async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
            return await self.call_tool(name, arguments or {})

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        if self._uncertain:
            return failure("SESSION_STATE_UNKNOWN", "Check the CATIA model and pending Bridge request before restarting MCP",
                           "session", None, name)
        future = asyncio.get_running_loop().run_in_executor(self._executor, self._execute_tool, name, arguments)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            self._uncertain = True
            future.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)
            raise

    def _execute_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        if self._uncertain:
            return failure("SESSION_STATE_UNKNOWN", "Previous operation completion is uncertain; inspect CATIA before restarting MCP",
                           "session", None, name)
        module = self._tool_router.get(name)
        if module is None:
            return failure("UNKNOWN_TOOL", f"Unknown tool: {name}", "validate", False, name)
        try:
            validate(arguments, self._schemas[name])
        except ValidationError as error:
            return failure("INVALID_ARGUMENT", error.message, "validate", False, name)
        logger.info("Tool call: %s", name)
        try:
            if module is self.caa_tools:
                result = module.execute(name, arguments)
                if result["ok"] is False and result["effects"]["modified"] is None:
                    self._uncertain = True
                logger.info("CAA operation: %s (%s)", result["operation_id"], result["code"])
                return structured_result(result)
            if name not in {"catia_connect", "catia_disconnect"}:
                self.connection.ensure_connected()
            text = module.execute(name, arguments)
            return CallToolResult(content=[TextContent(type="text", text=text)])
        except Exception as error:
            self._uncertain = True
            logger.error("Tool failed: %s (%s)", name, type(error).__name__)
            code = "UNSUPPORTED_CAPABILITY" if isinstance(error, AttributeError) else "COM_ERROR"
            return failure(code, str(error), "execute", None, name)

    async def close(self) -> None:
        try:
            await asyncio.get_running_loop().run_in_executor(self._executor, self.connection.disconnect)
        finally:
            self._executor.shutdown(wait=True)

    async def run(self) -> None:
        logger.info("Starting CATIA V5 MCP Server: %d tools", len(self._tool_router))
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(read_stream, write_stream, self.server.create_initialization_options())
        finally:
            await self.close()


def main() -> None:
    asyncio.run(CATIAMCPServer().run())


if __name__ == "__main__":
    main()
