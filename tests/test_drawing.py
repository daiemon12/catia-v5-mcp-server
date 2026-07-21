"""Pure-Python tests for CATDrawing text annotation semantics."""

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


class FakeView:
    def __init__(self, name: str) -> None:
        self.Name = name
        self.Texts = FakeTexts()


class FakeViews:
    def __init__(self, view: FakeView) -> None:
        self.view = view
        self.Count = 1

    def Item(self, index: int) -> FakeView:
        assert index == 1
        return self.view


class FakeSheet:
    def __init__(self, view: FakeView) -> None:
        self.Views = FakeViews(view)


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
