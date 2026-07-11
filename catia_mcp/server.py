"""CATIA V5 MCP Server.

Main entry point. Exposes all CATIA V5 automation tools via the
Model Context Protocol (MCP) for use with Claude Desktop or Claude Code.

Usage:
    python -m catia_mcp.server
    # or
    catia-mcp  (if installed via pip)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
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
from catia_mcp.tools.geoset import GeosetTools
from catia_mcp.tools.knowledge import KnowledgeTools
from catia_mcp.tools.measurement import MeasurementTools
from catia_mcp.tools.part_design import PartDesignTools
from catia_mcp.tools.part_design_advanced import AdvancedPartDesignTools
from catia_mcp.tools.sketcher import SketcherTools
from catia_mcp.tools.surface import SurfaceTools
from catia_mcp.tools.wheel import WheelTools
from catia_mcp.tools.wireframe import WireframeTools

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
        self.geoset_tools = GeosetTools(self.connection)
        self.wireframe_tools = WireframeTools(self.connection)
        self.surface_tools = SurfaceTools(self.connection)
        self.advanced_part_design_tools = AdvancedPartDesignTools(self.connection)
        self.knowledge_tools = KnowledgeTools(self.connection)
        self.wheel_tools = WheelTools(self.connection)

        # All tool modules
        self._tool_modules = [
            self.document_tools,
            self.sketcher_tools,
            self.part_design_tools,
            self.assembly_tools,
            self.measurement_tools,
            self.export_tools,
            self.geoset_tools,
            self.wireframe_tools,
            self.surface_tools,
            self.advanced_part_design_tools,
            self.knowledge_tools,
            self.wheel_tools,
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

    async def run_http(
        self, host: str, port: int, allowed_hosts: list[str] | None = None
    ) -> None:
        """Run the MCP server over Streamable HTTP.

        Used when the server must live in the same interactive Windows session
        as CATIA (so COM GetActiveObject can see it) while the MCP client
        connects across the network. A stdio-over-SSH transport can't do this:
        SSH lands in a separate logon session and the per-session COM Running
        Object Table wouldn't contain the interactive CATIA instance.

        This endpoint executes CATIA automation and file operations, so it is
        hardened: it binds to an explicit address (never 0.0.0.0 by default),
        keeps the DNS-rebinding Host allow-list enabled, and — when the
        CATIA_MCP_TOKEN env var is set — requires a matching bearer token on
        every request. Pair it with a firewall rule limiting the port to the
        client's source IP.
        """
        import os

        import uvicorn
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from mcp.server.transport_security import TransportSecuritySettings
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Mount

        # Keep DNS-rebinding protection ON, scoped to the addresses the client
        # legitimately uses in the Host header.
        host_allow = allowed_hosts or [f"{host}:{port}"]
        session_manager = StreamableHTTPSessionManager(
            app=self.server,
            json_response=False,
            stateless=False,
            security_settings=TransportSecuritySettings(allowed_hosts=host_allow),
        )

        token = os.environ.get("CATIA_MCP_TOKEN", "")
        if not token:
            logger.warning(
                "CATIA_MCP_TOKEN is not set — the HTTP endpoint has NO auth. "
                "Set a token and restrict the port by firewall."
            )

        async def handle_mcp(scope: Any, receive: Any, send: Any) -> None:
            if token:
                headers = dict(scope.get("headers") or [])
                if headers.get(b"authorization", b"").decode() != f"Bearer {token}":
                    await PlainTextResponse("Unauthorized", status_code=401)(
                        scope, receive, send
                    )
                    return
            await session_manager.handle_request(scope, receive, send)

        @contextlib.asynccontextmanager
        async def lifespan(_app: Starlette) -> Any:
            async with session_manager.run():
                logger.info("StreamableHTTP session manager started")
                yield

        app = Starlette(routes=[Mount("/mcp", app=handle_mcp)], lifespan=lifespan)
        # Client connects to the /mcp/ endpoint (trailing slash avoids a 307).
        logger.info("CATIA V5 MCP HTTP server listening on http://%s:%d/mcp/", host, port)
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        await uvicorn.Server(config).serve()


def main() -> None:
    """Entry point for the CATIA V5 MCP Server."""
    parser = argparse.ArgumentParser(prog="catia_mcp", description="CATIA V5 MCP Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve over Streamable HTTP instead of stdio (run inside CATIA's session).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind address (default 127.0.0.1; set the LAN/VPN IP to expose).",
    )
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default 8000).")
    parser.add_argument(
        "--allowed-host",
        action="append",
        dest="allowed_hosts",
        help="Host:port value(s) accepted in the Host header (repeatable).",
    )
    args = parser.parse_args()

    server = CATIAMCPServer()
    if args.http:
        asyncio.run(server.run_http(args.host, args.port, args.allowed_hosts))
    else:
        asyncio.run(server.run())


if __name__ == "__main__":
    main()
