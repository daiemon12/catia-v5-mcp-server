"""Quick test to verify the MCP server loads correctly.

This test does NOT require CATIA V5 — it only checks that:
1. All modules import correctly
2. All tools are registered
3. Tool definitions are valid
"""

import sys


def test_imports():
    """Test that all modules import without errors."""
    print("Testing imports...")
    from catia_mcp.connection import CATIAConnection
    from catia_mcp.tools.document import DocumentTools
    from catia_mcp.tools.sketcher import SketcherTools
    from catia_mcp.tools.part_design import PartDesignTools
    from catia_mcp.tools.assembly import AssemblyTools
    from catia_mcp.tools.measurement import MeasurementTools
    from catia_mcp.tools.export import ExportTools
    from catia_mcp.tools.geoset import GeosetTools
    from catia_mcp.tools.wireframe import WireframeTools
    from catia_mcp.tools.surface import SurfaceTools
    from catia_mcp.tools.part_design_advanced import AdvancedPartDesignTools
    from catia_mcp.tools.knowledge import KnowledgeTools
    from catia_mcp.tools.wheel import WheelTools
    print("  All modules imported successfully")


def test_tool_definitions():
    """Test that all tool modules return valid definitions."""
    print("Testing tool definitions...")
    from catia_mcp.connection import CATIAConnection
    from catia_mcp.tools.document import DocumentTools
    from catia_mcp.tools.sketcher import SketcherTools
    from catia_mcp.tools.part_design import PartDesignTools
    from catia_mcp.tools.assembly import AssemblyTools
    from catia_mcp.tools.measurement import MeasurementTools
    from catia_mcp.tools.export import ExportTools
    from catia_mcp.tools.geoset import GeosetTools
    from catia_mcp.tools.wireframe import WireframeTools
    from catia_mcp.tools.surface import SurfaceTools
    from catia_mcp.tools.part_design_advanced import AdvancedPartDesignTools
    from catia_mcp.tools.knowledge import KnowledgeTools
    from catia_mcp.tools.wheel import WheelTools

    conn = CATIAConnection()
    modules = {
        "Document": DocumentTools(conn),
        "Sketcher": SketcherTools(conn),
        "Part Design": PartDesignTools(conn),
        "Assembly": AssemblyTools(conn),
        "Measurement": MeasurementTools(conn),
        "Export": ExportTools(conn),
        "Geoset": GeosetTools(conn),
        "Wireframe": WireframeTools(conn),
        "Surface": SurfaceTools(conn),
        "Advanced Part Design": AdvancedPartDesignTools(conn),
        "Knowledgeware": KnowledgeTools(conn),
        "Wheel": WheelTools(conn),
    }

    total_tools = 0
    all_tool_names = set()

    for module_name, module in modules.items():
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
    print(f"  All tool names unique: yes")
    print(f"  All tools follow 'catia_*' naming: yes")
    return total_tools


def test_server_creation():
    """Test that the MCP server can be created (without running)."""
    print("Testing server creation...")
    from catia_mcp.server import CATIAMCPServer
    server = CATIAMCPServer()
    tool_count = len(server._tool_router)
    print(f"  Server created with {tool_count} tools in router")
    return tool_count


def main():
    print("=" * 60)
    print("CATIA V5 MCP Server — Verification Test")
    print("=" * 60)
    print()

    try:
        test_imports()
        print()

        total_tools = test_tool_definitions()
        print()

        router_count = test_server_creation()
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
