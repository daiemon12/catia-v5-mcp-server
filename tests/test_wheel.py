"""Pure-Python tests for wheel validation and new MCP interfaces."""

from __future__ import annotations

import os

import pytest

from catia_mcp.connection import CATIAConnection
from catia_mcp.server import CATIAMCPServer
from catia_mcp.tools._geometry import set_revolution_angle
from catia_mcp.tools.export import ExportTools
from catia_mcp.tools.sketcher import SketcherTools
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
    assert values["flange_lip_width"] == 8.0
    assert values["bead_seat_width"] == 20.0
    assert values["safety_hump_width"] == 10.0
    assert values["safety_hump_height"] == 5.0
    assert values["drop_center_depth"] == 14.0
    assert values["valve_hole_diameter"] == 11.3
    assert values["inner_radius"] == (
        values["rim_diameter"] / 2
        - values["flange_height"]
        - values["drop_center_depth"]
        - values["rim_thickness"]
    )
    assert values["inner_radius"] > values["hub_radius"]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"spoke_style": "turbine"}, "simple_lofted"),
        ({"offset": 200}, "offset"),
        ({"pcd": 70}, "PCD"),
        ({"spoke_count": 2}, "spoke_count"),
        ({"rim_diameter": -1}, "rim_diameter"),
        ({"safety_hump_height": 12}, "safety_hump_height"),
        ({"rim_width": 75}, "rim_width"),
        (
            {
                "rim_diameter": 60,
                "flange_height": 10,
                "drop_center_depth": 12,
                "rim_thickness": 8,
            },
            "positive inner radius",
        ),
        ({"rim_width": 120}, "valve_hole_diameter"),
        ({"valve_hole_diameter": 50}, "valve_hole_diameter"),
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

    by_name = {definition["name"]: definition for definition in definitions}
    wheel_properties = by_name["catia_design_wheel"]["inputSchema"]["properties"]
    assert {
        "flange_lip_width",
        "bead_seat_width",
        "safety_hump_width",
        "safety_hump_height",
        "drop_center_depth",
        "valve_hole_diameter",
    } <= wheel_properties.keys()
    for name in (
        "flange_lip_width",
        "bead_seat_width",
        "safety_hump_width",
        "safety_hump_height",
        "drop_center_depth",
        "valve_hole_diameter",
    ):
        assert wheel_properties[name]["default"] == WheelTools.validate(VALID)[name]
    line_properties = by_name["catia_sketch_line"]["inputSchema"]["properties"]
    assert line_properties["construction"]["default"] is False
    assert line_properties["centerline"]["default"] is False


def test_validation_does_not_connect_to_catia() -> None:
    connection = CATIAConnection()
    WheelTools(connection).validate(VALID)
    assert connection.app is None


def test_rim_profile_has_expected_landmarks_and_uniform_thickness() -> None:
    values = WheelTools.validate(VALID)
    points = WheelTools._rim_profile_points(values)
    half = values["rim_width"] / 2
    outer_count = len(points) // 2

    assert len(points) == 24
    assert points[0] == (values["rim_diameter"] / 2, -half)
    assert points[outer_count - 1] == (values["rim_diameter"] / 2, half)
    assert max(radius for radius, _ in points[:outer_count]) == values["rim_diameter"] / 2
    assert min(radius for radius, _ in points[:outer_count]) == values["drop_center_radius"]
    for outer_point, inner_point in zip(points[:outer_count], reversed(points[outer_count:])):
        assert outer_point[1] == inner_point[1]
        assert outer_point[0] - inner_point[0] == values["rim_thickness"]


def test_spoke_loft_sections_overlap_solids_and_form_a_crown() -> None:
    values = WheelTools.validate(VALID)
    sections = WheelTools._spoke_sections(values)

    assert len(sections) == 3
    assert sections[0]["radius"] < values["hub_radius"]
    assert sections[-1]["radius"] > values["inner_radius"]
    assert sections[0]["width"] > sections[1]["width"] > sections[2]["width"]
    assert sections[0]["depth"] > sections[1]["depth"] > sections[2]["depth"]
    assert sections[0]["crown"] == 0
    assert sections[1]["crown"] != 0

    left = WheelTools._spoke_guide_points(sections, -1)
    right = WheelTools._spoke_guide_points(sections, 1)
    assert len(left) == len(right) == len(sections)
    for section, left_point, right_point in zip(sections, left, right):
        assert left_point[0] == right_point[0] == section["radius"]
        assert left_point[1] == -right_point[1]
        assert left_point[2] == right_point[2]

    for section in sections:
        points = WheelTools._spoke_section_points(section)
        assert len(points) == 4
        assert {point[0] for point in points} == {section["radius"]}
        assert points[3] == WheelTools._spoke_guide_points([section], -1)[0]
        assert points[2] == WheelTools._spoke_guide_points([section], 1)[0]


def test_valve_hole_is_inside_flat_drop_center_and_clear_of_spoke() -> None:
    values = WheelTools.validate(VALID)
    half_width = values["rim_width"] / 2
    end_width = values["flange_lip_width"] + values["bead_seat_width"] + values["safety_hump_width"]
    transition = (values["rim_width"] - 2 * end_width) / 3
    flat_left = -half_width + end_width + transition
    flat_right = half_width - end_width - transition
    hole_radius = values["valve_hole_diameter"] / 2

    assert flat_left + hole_radius < values["valve_axial_position"]
    assert values["valve_axial_position"] < flat_right - hole_radius
    assert values["valve_plane_radius"] == (
        values["drop_center_radius"] - values["rim_thickness"] / 2
    )
    assert values["valve_pocket_depth"] == values["rim_thickness"] * 2

    rim_section = WheelTools._spoke_sections(values)[-1]
    hole_high = values["valve_axial_position"] + hole_radius
    spoke_low = rim_section["crown"] - rim_section["depth"] / 2
    assert hole_high + 2 <= spoke_low


def test_sketch_line_can_become_construction_centerline() -> None:
    class Line:
        Construction = False

    class Factory:
        def __init__(self) -> None:
            self.line = Line()

        def CreateLine(self, *coordinates: float) -> Line:
            assert coordinates == (0, -100, 0, 100)
            return self.line

    class Sketch:
        CenterLine = None

    tools = SketcherTools(CATIAConnection())
    tools._active_sketch = Sketch()
    tools._active_factory = Factory()

    result = tools.execute(
        "catia_sketch_line",
        {"x1": 0, "y1": -100, "x2": 0, "y2": 100, "centerline": True},
    )

    assert tools._active_factory.line.Construction is True
    assert tools._active_sketch.CenterLine is tools._active_factory.line
    assert "centerline" in result


def test_revolution_angle_uses_explicit_degree_units() -> None:
    class Angle:
        value = None

        def ValuateFromString(self, value: str) -> None:
            self.value = value

    class Revolution:
        FirstAngle = Angle()

    feature = Revolution()
    set_revolution_angle(feature, 135)

    assert feature.FirstAngle.value == "135deg"


def test_wheel_rejects_output_path_already_open_in_catia_session() -> None:
    class Document:
        def __init__(self, full_name: str) -> None:
            self.FullName = full_name

    class Documents:
        def __init__(self, docs: list[Document]) -> None:
            self._docs = docs
            self.Count = len(docs)

        def Item(self, index: int) -> Document:
            return self._docs[index - 1]

    target = os.path.abspath(r"C:\tmp\MCP_Wheel_Profile_Test.CATPart")
    active = Document("")
    already_open = Document(target)

    class Connection:
        def __init__(self) -> None:
            self.documents = Documents([active, already_open])
            self.active_document = active

    with pytest.raises(ValueError, match="already open in CATIA"):
        WheelTools(Connection())._ensure_output_path_is_not_already_open(target)  # type: ignore[arg-type]


def test_active_viewer_falls_back_to_active_window() -> None:
    class Viewer:
        pass

    class Window:
        ActiveViewer = Viewer()

    class App:
        ActiveWindow = Window()

        @property
        def ActiveEditor(self) -> object:
            raise RuntimeError("no active editor")

    connection = CATIAConnection()
    connection.app = App()
    connection.ensure_connected = lambda: None  # type: ignore[method-assign]

    assert connection.active_viewer is connection.app.ActiveWindow.ActiveViewer


def test_export_tools_use_connection_active_viewer() -> None:
    class Viewpoint:
        sight = None
        up = None

        def PutSightDirection(self, value: list[int]) -> None:
            self.sight = value

        def PutUpDirection(self, value: list[int]) -> None:
            self.up = value

    class Viewer:
        def __init__(self) -> None:
            self.Viewpoint3D = Viewpoint()
            self.captured = None
            self.reframe_calls = 0

        def CaptureToFile(self, fmt: int, path: str) -> None:
            self.captured = (fmt, path)

        def Reframe(self) -> None:
            self.reframe_calls += 1

    class Connection:
        def __init__(self) -> None:
            self.active_viewer = Viewer()

        def ensure_connected(self) -> None:
            return None

    conn = Connection()
    tools = ExportTools(conn)  # type: ignore[arg-type]

    shot = tools.execute("catia_screenshot", {"file_path": "C:/tmp/wheel.png"})
    view = tools.execute("catia_set_view", {"view": "right"})
    fit = tools.execute("catia_fit_all", {})

    assert conn.active_viewer.captured == (1, "C:\\tmp\\wheel.png")
    assert conn.active_viewer.Viewpoint3D.sight == [-1, 0, 0]
    assert conn.active_viewer.Viewpoint3D.up == [0, 1, 0]
    assert conn.active_viewer.reframe_calls == 2
    assert "Screenshot saved" in shot
    assert view == "View set to: right"
    assert fit == "View fitted to all geometry"
