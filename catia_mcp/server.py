"""CATIA V5 MCP Server.

Main entry point. Exposes all CATIA V5 automation tools via the
Model Context Protocol (MCP) for use with Claude Desktop or Claude Code.

Usage:
    python -m catia_mcp.server
    # or
    catia-mcp  (if installed via pip)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from catia_mcp.connection import CATIAConnection
from catia_mcp.tools.assembly import AssemblyTools
from catia_mcp.tools.document import DocumentTools
from catia_mcp.tools.export import ExportTools
from catia_mcp.tools.measurement import MeasurementTools
from catia_mcp.tools.part_design import PartDesignTools
from catia_mcp.tools.sketcher import SketcherTools

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("catia_mcp.log", encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("catia_mcp")


class CATIAMCPServer:
    """MCP Server that bridges Claude to CATIA V5 via COM Automation."""

    def __init__(self) -> None:
        self.server = Server("catia-v5-mcp")
        self.connection = CATIAConnection()

        # Initialize tool modules with shared connection
        self.document_tools = DocumentTools(self.connection)
        self.sketcher_tools = SketcherTools(self.connection)
        self.part_design_tools = PartDesignTools(self.connection)
        self.assembly_tools = AssemblyTools(self.connection)
        self.measurement_tools = MeasurementTools(self.connection)
        self.export_tools = ExportTools(self.connection)

        # All tool modules
        self._tool_modules = [
            self.document_tools,
            self.sketcher_tools,
            self.part_design_tools,
            self.assembly_tools,
            self.measurement_tools,
            self.export_tools,
        ]

        # Build tool name -> module routing table
        self._tool_router: dict[str, Any] = {}
        for module in self._tool_modules:
            for tool_def in module.get_tool_definitions():
                self._tool_router[tool_def["name"]] = module

        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Register MCP protocol handlers."""

        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            tools = []
            for module in self._tool_modules:
                for tool_def in module.get_tool_definitions():
                    tools.append(
                        Tool(
                            name=tool_def["name"],
                            description=tool_def["description"],
                            inputSchema=tool_def["inputSchema"],
                        )
                    )
            logger.info("Listed %d tools", len(tools))
            return tools

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: dict[str, Any] | None
        ) -> list[TextContent]:
            arguments = arguments or {}
            logger.info("Tool call: %s(%s)", name, arguments)

            try:
                module = self._tool_router.get(name)
                if module is None:
                    return [TextContent(
                        type="text",
                        text=f"Unknown tool: '{name}'. Use list_tools to see available tools.",
                    )]

                # Auto-connect for non-connect tools
                if name != "catia_connect" and name != "catia_disconnect":
                    if not self.connection.is_connected:
                        connect_msg = self.connection.connect()
                        logger.info("Auto-connected: %s", connect_msg)

                result = module.execute(name, arguments)
                logger.info("Tool result: %s", result[:200] if len(result) > 200 else result)
                return [TextContent(type="text", text=result)]

            except Exception as e:
                error_msg = f"Error in {name}: {e}"
                logger.error(error_msg, exc_info=True)
                return [TextContent(type="text", text=error_msg)]

    async def run(self) -> None:
        """Run the MCP server over stdio."""
        logger.info("Starting CATIA V5 MCP Server...")
        logger.info("Registered %d tools across %d modules",
                     len(self._tool_router), len(self._tool_modules))

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


def main() -> None:
    """Entry point for the CATIA V5 MCP Server."""
    server = CATIAMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
