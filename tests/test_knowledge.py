"""Pure-Python tests for Knowledgeware design-table COM call semantics."""

from __future__ import annotations

import json

from catia_mcp.tools.knowledge import KnowledgeTools


class FakeDesignTable:
    Name = "WheelVariants"

    def __init__(self) -> None:
        self.associations: list[object] = []

    def AddAssociation(self, parameter: object, sheet_column: str) -> None:
        self.associations.append((parameter, sheet_column))


class FakeRelations:
    def __init__(self, table: FakeDesignTable) -> None:
        self.table = table
        self.calls: list[tuple[object, ...]] = []

    def CreateDesignTable(self, *args: object) -> FakeDesignTable:
        self.calls.append(args)
        return self.table


class FakeParameters:
    def __init__(self) -> None:
        self.items = {"Wheel_Diameter": object(), "Spoke_Count": object()}

    def Item(self, name: str) -> object:
        return self.items[name]


class FakePart:
    def __init__(self) -> None:
        self.table = FakeDesignTable()
        self.Parameters = FakeParameters()
        self.Relations = FakeRelations(self.table)
        self.updated: list[object] = []

    def UpdateObject(self, item: object) -> None:
        self.updated.append(item)


class FakeConnection:
    def __init__(self, part: FakePart) -> None:
        self.part = part

    def get_active_part(self) -> FakePart:
        return self.part


def test_create_design_table_creates_and_associates_requested_parameters() -> None:
    part = FakePart()
    tools = KnowledgeTools(FakeConnection(part))

    output = tools.execute(
        "catia_create_design_table",
        {
            "name": "WheelVariants",
            "file_path": "C:/CATIA/WheelVariants.txt",
            "parameters": ["Wheel_Diameter", "Spoke_Count"],
            "copy_mode": False,
        },
    )

    assert part.Relations.calls == [
        ("WheelVariants", "Created by CATIA MCP", False, "C:/CATIA/WheelVariants.txt")
    ]
    assert part.table.associations == [
        (part.Parameters.items["Wheel_Diameter"], "Wheel_Diameter"),
        (part.Parameters.items["Spoke_Count"], "Spoke_Count"),
    ]
    assert part.updated == [part.table]
    assert json.loads(output) == {
        "name": "WheelVariants",
        "file_path": "C:/CATIA/WheelVariants.txt",
        "parameters": ["Wheel_Diameter", "Spoke_Count"],
    }
