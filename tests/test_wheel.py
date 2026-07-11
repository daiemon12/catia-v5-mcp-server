"""Pure-Python tests for wheel validation and new MCP interfaces."""

from __future__ import annotations

import pytest

from catia_mcp.connection import CATIAConnection
from catia_mcp.server import CATIAMCPServer
from catia_mcp.tools.wheel import WheelTools


VALID = {
    "rim_diameter": 457.2,
    "rim_width": 203.2,
    "offset": 35.0,
    "pcd": 114.3,
    "bolt_count": 5,
    "center_bore": 67.1,
    "spoke_count": 10,
    "spoke_style": "simple_lofted",
}


def test_wheel_defaults_and_derived_dimensions() -> None:
    values = WheelTools.validate(VALID)
    assert values["material_density"] == 2700.0
    assert values["inner_radius"] > values["hub_radius"]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"spoke_style": "turbine"}, "simple_lofted"),
        ({"offset": 200}, "offset"),
        ({"pcd": 70}, "PCD"),
        ({"spoke_count": 2}, "spoke_count"),
        ({"rim_diameter": -1}, "rim_diameter"),
    ],
)
def test_invalid_wheel_inputs_are_rejected(override: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        WheelTools.validate({**VALID, **override})


def test_new_tools_have_unique_routes_and_strict_schemas() -> None:
    server = CATIAMCPServer()
    expected = {
        "catia_new_geoset",
        "catia_select_reference",
        "catia_spline_3d",
        "catia_loft",
        "catia_close_surface",
        "catia_create_formula",
        "catia_design_wheel",
    }
    assert expected <= server._tool_router.keys()
    definitions = [
        definition
        for module in server._tool_modules
        for definition in module.get_tool_definitions()
    ]
    assert len(definitions) == len({definition["name"] for definition in definitions})
    for definition in definitions:
        assert definition["inputSchema"]["type"] == "object"


def test_validation_does_not_connect_to_catia() -> None:
    connection = CATIAConnection()
    WheelTools(connection).validate(VALID)
    assert connection.app is None
