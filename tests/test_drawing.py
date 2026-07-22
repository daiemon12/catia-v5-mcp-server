"""Pure-Python tests for CATDrawing annotation semantics."""

from __future__ import annotations

import json

from catia_mcp.tools.drawing import DrawingTools


class FakeText:
    def __init__(self, value: str, x: float, y: float) -> None:
        self.Name = "Text.1"
        self.Text = value
        self.x = x
        self.y = y


class FakeTexts:
    def __init__(self) -> None:
        self.items: list[FakeText] = []

    def Add(self, value: str, x: float, y: float) -> FakeText:
        text = FakeText(value, x, y)
        self.items.append(text)
        return text


class FakeDimValue:
    def __init__(self, value: float) -> None:
        self.Value = value


class FakeDimension:
    def __init__(self, name: str, value: float) -> None:
        self.Name = name
        self.DimType = 0
        self.DimStatus = 0
        self._value = FakeDimValue(value)

    def GetValue(self) -> FakeDimValue:
        return self._value


class FakeDimensions:
    def __init__(self) -> None:
        self.items: list[FakeDimension] = []

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int) -> FakeDimension:
        return self.items[index - 1]


class FakeView:
    def __init__(self, name: str) -> None:
        self.Name = name
        self.Texts = FakeTexts()
        self.Dimensions = FakeDimensions()


class FakeViews:
    def __init__(self, view: FakeView) -> None:
        self.view = view
        self.Count = 1

    def Item(self, index: int) -> FakeView:
        assert index == 1
        return self.view


class FakeSheet:
    def __init__(self, view: FakeView) -> None:
        self.Name = "Sheet.1"
        self.Views = FakeViews(view)

    def GenerateDimensions(self) -> None:
        self.Views.view.Dimensions.items.extend(
            [FakeDimension("Dimension.1", 25.0), FakeDimension("Dimension.2", 50.0)]
        )


class FakeSheets:
    def __init__(self, sheet: FakeSheet) -> None:
        self.ActiveSheet = sheet


class FakeRoot:
    def __init__(self, sheet: FakeSheet) -> None:
        self.Sheets = FakeSheets(sheet)


class FakeDocument:
    def __init__(self, root: FakeRoot) -> None:
        self.DrawingRoot = root
        self.Name = "Drawing1.CATDrawing"
        self.updated = False

    def Update(self) -> None:
        self.updated = True


class FakeConnection:
    def __init__(self) -> None:
        self.view = FakeView("Front")
        self.active_document = FakeDocument(FakeRoot(FakeSheet(self.view)))
        self.connected = False
        self.refreshed = False

    def ensure_connected(self) -> None:
        self.connected = True

    def refresh_display(self) -> None:
        self.refreshed = True


def test_drawing_add_text_creates_and_names_annotation() -> None:
    connection = FakeConnection()
    tools = DrawingTools(connection)

    output = tools.execute(
        "catia_drawing_add_text",
        {"view": "Front", "text": "SECTION A-A", "x": 42, "y": 17.5, "name": "Title"},
    )

    payload = json.loads(output)
    assert payload == {
        "tool": "catia_drawing_add_text",
        "view": "Front",
        "name": "Title",
        "text": "SECTION A-A",
        "x": 42.0,
        "y": 17.5,
    }
    assert connection.connected
    assert connection.refreshed
    assert connection.active_document.updated
    assert connection.view.Texts.items[0].Name == "Title"


def test_drawing_add_text_is_registered_with_required_fields() -> None:
    definition = next(
        item
        for item in DrawingTools(FakeConnection()).get_tool_definitions()
        if item["name"] == "catia_drawing_add_text"
    )

    assert definition["inputSchema"]["required"] == ["view", "text", "x", "y"]


def test_drawing_generate_dimensions_reports_created_dimensions() -> None:
    connection = FakeConnection()
    tools = DrawingTools(connection)

    output = tools.execute("catia_drawing_generate_dimensions", {})

    assert json.loads(output) == {
        "tool": "catia_drawing_generate_dimensions",
        "sheet": "Sheet.1",
        "before": {"Front": 0},
        "after": {"Front": 2},
        "generated_by_view": {"Front": 2},
        "generated_total": 2,
    }
    assert connection.connected
    assert connection.refreshed
    assert connection.active_document.updated


def test_drawing_generate_dimensions_is_registered_without_arguments() -> None:
    definition = next(
        item
        for item in DrawingTools(FakeConnection()).get_tool_definitions()
        if item["name"] == "catia_drawing_generate_dimensions"
    )

    assert definition["inputSchema"]["properties"] == {}
    assert "required" not in definition["inputSchema"]


def test_dimension_diagnostics_include_type_status_and_value() -> None:
    view = FakeView("Front")
    view.Dimensions.items.append(FakeDimension("Overall width", 50.0))

    assert DrawingTools._dimension_diagnostics(view) == [
        {
            "index": 1,
            "name": "Overall width",
            "type": 0,
            "status": 0,
            "value": 50.0,
        }
    ]
