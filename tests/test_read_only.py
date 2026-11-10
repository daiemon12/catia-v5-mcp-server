"""Read-only mode: only inspection and measurement tools are reachable."""

import asyncio

from catia_mcp.server import READ_ONLY_TOOLS, CATIAMCPServer, parse_args

MUTATING_MARKERS = (
    "_new_", "_create", "_add", "_set_", "_delete", "_save", "_close_document", "_export",
    "_pad", "_pocket", "_hole", "_fillet", "_move_", "_update", "_screenshot", "_sketch_line",
)


def test_read_only_tools_exist_and_look_read_only():
    full = CATIAMCPServer()
    try:
        assert READ_ONLY_TOOLS <= set(full._tool_router)
        for name in READ_ONLY_TOOLS:
            assert not any(marker in name for marker in MUTATING_MARKERS), name
    finally:
        asyncio.run(full.close())


def test_read_only_server_lists_and_runs_only_read_tools(monkeypatch):
    async def run():
        server = CATIAMCPServer(read_only=True)
        monkeypatch.setattr(server.connection, "ensure_connected", lambda: None)
        monkeypatch.setattr(server.document_tools, "execute", lambda name, args: "listed")
        try:
            assert set(server._tool_router) == READ_ONLY_TOOLS
            refused = await server.call_tool("catia_pad", {"height": 10})
            assert refused.isError is True
            assert refused.structuredContent["code"] == "READ_ONLY_MODE"
            assert refused.structuredContent["effects"]["modified"] is False
            for name in ("catia_save_document", "catia_export", "catia_close_document"):
                assert (await server.call_tool(name, {})).structuredContent["code"] == "READ_ONLY_MODE"
            allowed = await server.call_tool("catia_list_documents", {})
            assert not allowed.isError and allowed.content[0].text == "listed"
        finally:
            await server.close()

    asyncio.run(run())


def test_flag_and_env(monkeypatch):
    assert parse_args([]).read_only is False
    assert parse_args(["--read-only"]).read_only is True
    monkeypatch.setenv("CATIA_MCP_READ_ONLY", "1")
    assert parse_args([]).read_only is True
