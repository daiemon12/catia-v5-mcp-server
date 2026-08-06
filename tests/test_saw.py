"""Pure-Python tests for the circular saw builder."""

from __future__ import annotations

import math

from catia_mcp.connection import CATIAConnection
from catia_mcp.server import CATIAMCPServer
from catia_mcp.tools.saw import SawTools


def test_saw_validation_derives_expected_dimensions() -> None:
    values = SawTools.validate(
        {
            "document_path": r"C:\Users\sup02\Documents\CATIA_2026_LADUGA\08\08.CATPart",
            "R": 36,
            "N": 22,
        }
    )

    assert values["r"] == 12
    assert values["h"] == 4.5
    assert math.isclose(values["l"], 2 * math.pi * 36 / 22)
    assert values["R1"] == 13.5
    assert math.isclose(values["R2"], values["l"] * 5)
    assert values["T"] == 3.6
    assert values["outer_radius"] == 40.5


def test_saw_outline_point_count_and_rotation() -> None:
    values = SawTools.validate(
        {
            "document_path": r"C:\Users\sup02\Documents\CATIA_2026_LADUGA\08\08.CATPart",
            "R": 36,
            "N": 22,
        }
    )
    points = SawTools._tooth_outline_points(values)

    assert len(points) == 44
    first = points[0]
    second = points[1]
    assert first[0] == 0
    assert first[1] == -values["outer_radius"]
    assert math.isclose(math.hypot(*second), values["R"], abs_tol=1e-4)


def test_saw_tool_is_registered() -> None:
    server = CATIAMCPServer()
    assert "catia_design_circular_saw" in server._tool_router


def test_validation_does_not_connect_to_catia() -> None:
    connection = CATIAConnection()
    SawTools(connection).validate(
        {
            "document_path": r"C:\Users\sup02\Documents\CATIA_2026_LADUGA\08\08.CATPart",
            "R": 36,
            "N": 22,
        }
    )
    assert connection.app is None
