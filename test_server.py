"""Quick test to verify the MCP server loads correctly.

This test does NOT require CATIA V5 — it only checks that:
1. All modules import correctly
2. All tools are registered
3. Tool definitions are valid
"""

import importlib
import sys


def test_imports():
    """Test that all modules import without errors."""
    print("Testing imports...")
    for module_name in (
        "catia_mcp.connection",
        "catia_mcp.tools.document",
        "catia_mcp.tools.sketcher",
        "catia_mcp.tools.part_design",
        "catia_mcp.tools.assembly",
        "catia_mcp.tools.measurement",
        "catia_mcp.tools.export",
        "catia_mcp.tools.geoset",
        "catia_mcp.tools.wireframe",
        "catia_mcp.tools.surface",
        "catia_mcp.tools.part_design_advanced",
        "catia_mcp.tools.knowledge",
        "catia_mcp.tools.wheel",
        "catia_mcp.tools.saw",
        "catia_mcp.tools.drawing",
        "catia_mcp.tools.contest",
    ):
        importlib.import_module(module_name)
    print("  All modules imported successfully")


def _tool_definitions_count() -> int:
    """Return the validated total number of registered tool definitions."""
    print("Testing tool definitions...")
    from catia_mcp.server import CATIAMCPServer

    modules = CATIAMCPServer()._tool_modules

    total_tools = 0
    all_tool_names = set()

    for module in modules:
        module_name = type(module).__name__
        tools = module.get_tool_definitions()
        print(f"  {module_name}: {len(tools)} tools")

        for tool in tools:
            # Verify required fields
            assert "name" in tool, f"Tool missing 'name' in {module_name}"
            assert "description" in tool, f"Tool '{tool['name']}' missing 'description'"
            assert "inputSchema" in tool, f"Tool '{tool['name']}' missing 'inputSchema'"
            assert tool["inputSchema"]["type"] == "object", (
                f"Tool '{tool['name']}' inputSchema must be type 'object'"
            )

            # Check for duplicate names
            assert tool["name"] not in all_tool_names, (
                f"Duplicate tool name: {tool['name']}"
            )
            all_tool_names.add(tool["name"])

            # Check naming convention
            assert tool["name"].startswith("catia_"), (
                f"Tool '{tool['name']}' should start with 'catia_'"
            )

            total_tools += 1

    print(f"\n  Total: {total_tools} tools registered")
    print("  All tool names unique: yes")
    print("  All tools follow 'catia_*' naming: yes")
    return total_tools


def test_tool_definitions():
    """Test that all tool modules return valid definitions."""
    assert _tool_definitions_count() > 0


def _server_tool_count() -> int:
    """Return the number of tools routed by a newly created MCP server."""
    print("Testing server creation...")
    from catia_mcp.server import CATIAMCPServer
    server = CATIAMCPServer()
    tool_count = len(server._tool_router)
    print(f"  Server created with {tool_count} tools in router")
    return tool_count


def test_server_creation():
    """Test that the MCP server can be created (without running)."""
    assert _server_tool_count() > 0


def main():
    print("=" * 60)
    print("CATIA V5 MCP Server — Verification Test")
    print("=" * 60)
    print()

    try:
        test_imports()
        print()

        total_tools = _tool_definitions_count()
        print()

        router_count = _server_tool_count()
        print()

        assert total_tools == router_count, (
            f"Mismatch: {total_tools} tools defined but {router_count} in router"
        )

        print("=" * 60)
        print(f"ALL TESTS PASSED — {total_tools} tools ready")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
