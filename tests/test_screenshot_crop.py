"""Pixel, capture, failure and MCP transport contracts; no CATIA required."""

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from mcp.types import CallToolRequest, CallToolRequestParams

from catia_mcp.screenshot import capture_cropped_screenshot, crop_white_border
from catia_mcp.tools.export import ExportTools


@pytest.fixture(autouse=True)
def offline_viewport(monkeypatch):
    class FakeViewportUI:
        def __init__(self, app, window):
            self.original_layout = 2
            self.original_compass = True

        def hide(self):
            pass

        def restore(self):
            pass

    monkeypatch.setattr("catia_mcp.screenshot.ViewportUI", FakeViewportUI)


def white_image(width=100, height=80):
    return np.full((height, width, 3), 255, dtype=np.uint8)


def connection_for(image):
    background = [0.2, 0.2, 0.4]

    def put_background(color):
        background[:] = color

    def capture(fmt, path):
        assert fmt == 4  # lossless CATIA BMP, not JPEG
        assert background == [1.0, 1.0, 1.0]
        ok, buffer = cv2.imencode(".bmp", image)
        assert ok
        Path(path).write_bytes(buffer.tobytes())

    viewer = SimpleNamespace(
        CaptureToFile=Mock(side_effect=capture),
        PutBackgroundColor=Mock(side_effect=put_background),
        Update=Mock(),
        background=background,
    )
    return SimpleNamespace(
        ensure_connected=Mock(),
        connect=Mock(side_effect=AssertionError("Do not auto-connect before validation")),
        is_connected=False,
        active_window=SimpleNamespace(ActiveViewer=viewer),
        app=SimpleNamespace(
            SystemService=SimpleNamespace(
                Evaluate=Mock(
                    side_effect=lambda script, language, method, params: tuple(background)
                ),
            )
        ),
    )


def test_disconnected_points_and_one_pixel_lines_are_preserved():
    image = white_image()
    image[30:50, 40:60] = (10, 100, 200)
    image[8, 12] = 0
    image[65, 20:85] = 254  # very pale one-pixel line must survive at tolerance 0
    cropped, box = crop_white_border(image, 3, 0)
    assert box == (9, 5, 88, 69)
    np.testing.assert_array_equal(cropped, image[5:69, 9:88])


def test_tolerance_requires_all_channels_to_be_near_white():
    image = white_image()
    image[4, 4] = 252
    image[30, 40] = (249, 255, 255)
    cropped, box = crop_white_border(image, 0, 5)
    assert box == (40, 30, 41, 31)
    np.testing.assert_array_equal(cropped[0, 0], (249, 255, 255))


@pytest.mark.parametrize("location", [(0, 0), (79, 99)])
def test_padding_clamped_at_edges(location):
    image = white_image()
    image[location] = 0
    cropped, box = crop_white_border(image, 16, 0)
    assert cropped.shape == (17, 17, 3)
    assert box == ((0, 0, 17, 17) if location == (0, 0) else (83, 63, 100, 80))


def test_all_white_is_not_an_empty_success():
    with pytest.raises(ValueError, match="EMPTY_VIEW"):
        crop_white_border(white_image(), 16, 0)


def test_full_frame_retained_when_content_touches_both_corners():
    image = white_image()
    image[0, 0] = 0
    image[-1, -1] = 0
    cropped, box = crop_white_border(image, 0, 0)
    assert box == (0, 0, 100, 80)
    np.testing.assert_array_equal(image, cropped)


def test_capture_png_unicode_path_and_measured_dimensions(tmp_path):
    image = white_image()
    image[25:35, 40:50] = 0
    conn = connection_for(image)
    output = tmp_path / "观察图片" / "裁剪.png"
    result = ExportTools(conn).execute(
        "catia_screenshot",
        {
            "file_path": str(output),
            "padding": 2,
        },
    )
    assert result["ok"] and result["code"] == "OK"
    assert result["effects"] == {
        "file_created": True,
        "model_changed": False,
        "background_restored": True,
        "viewport_restored": True,
    }
    assert conn.active_window.ActiveViewer.background == [0.2, 0.2, 0.4]
    assert result["data"]["original_width"] == 100
    assert result["data"]["original_height"] == 80
    assert (result["data"]["width"], result["data"]["height"]) == (14, 14)
    assert result["data"]["crop_box"] == {"left": 38, "top": 23, "right": 52, "bottom": 37}
    assert list(output.parent.iterdir()) == [output]
    decoded = cv2.imdecode(np.frombuffer(output.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    np.testing.assert_array_equal(decoded, image[23:37, 38:52])
    conn.ensure_connected.assert_called_once()


@pytest.mark.parametrize(
    "changes",
    [
        {"file_path": "relative.png"},
        {"file_path": ""},
        {"file_path": None},
        {"padding": -1},
        {"padding": 4097},
        {"padding": True},
        {"padding": 1.5},
        {"white_tolerance": -1},
        {"white_tolerance": 33},
        {"white_tolerance": True},
        {"width": 1920},
    ],
)
def test_invalid_inputs_rejected_before_capture(tmp_path, changes):
    conn = connection_for(white_image())
    arguments = {"file_path": str(tmp_path / "crop.png"), **changes}
    result = capture_cropped_screenshot(conn, arguments)
    assert not result["ok"] and result["code"] == "INVALID_ARGUMENT"
    conn.ensure_connected.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_wrong_output_format_rejected_before_capture(tmp_path):
    conn = connection_for(white_image())
    result = capture_cropped_screenshot(conn, {"file_path": str(tmp_path / "crop.jpg")})
    assert result["code"] == "INVALID_ARGUMENT"
    conn.ensure_connected.assert_not_called()


def test_existing_file_is_preserved(tmp_path):
    output = tmp_path / "crop.png"
    output.write_bytes(b"previous file")
    conn = connection_for(white_image())
    result = capture_cropped_screenshot(conn, {"file_path": str(output)})
    assert result["code"] == "OUTPUT_EXISTS"
    assert output.read_bytes() == b"previous file"
    conn.ensure_connected.assert_not_called()


@pytest.mark.parametrize(
    "failure,code",
    [
        ("missing", "CAPTURE_FAILED"),
        ("invalid", "IMAGE_DECODE_FAILED"),
        ("white", "EMPTY_VIEW"),
        ("com", "COM_ERROR"),
    ],
)
def test_capture_failures_leave_no_output_or_temporary_files(tmp_path, failure, code):
    conn = connection_for(white_image())
    capture = conn.active_window.ActiveViewer.CaptureToFile
    if failure == "missing":
        capture.side_effect = None
    elif failure == "invalid":
        capture.side_effect = lambda fmt, path: Path(path).write_bytes(b"not an image")
    elif failure == "com":
        capture.side_effect = RuntimeError("Capture blocked")
    result = capture_cropped_screenshot(conn, {"file_path": str(tmp_path / "crop.png")})
    assert result["code"] == code and not result["ok"]
    assert not result["effects"]["file_created"]
    assert result["effects"]["background_restored"]
    assert conn.active_window.ActiveViewer.background == [0.2, 0.2, 0.4]
    assert list(tmp_path.iterdir()) == []


def test_output_created_during_capture_is_not_overwritten(tmp_path):
    image = white_image()
    image[40, 50] = 0
    conn = connection_for(image)
    output = tmp_path / "crop.png"
    original_capture = conn.active_window.ActiveViewer.CaptureToFile.side_effect

    def competing_capture(fmt, path):
        original_capture(fmt, path)
        output.write_bytes(b"another writer")

    conn.active_window.ActiveViewer.CaptureToFile.side_effect = competing_capture
    result = capture_cropped_screenshot(conn, {"file_path": str(output)})
    assert result["code"] == "OUTPUT_EXISTS"
    assert output.read_bytes() == b"another writer"
    assert list(tmp_path.iterdir()) == [output]


def test_unchanged_crop_has_warning(tmp_path):
    conn = connection_for(np.zeros((80, 100, 3), dtype=np.uint8))
    result = capture_cropped_screenshot(conn, {"file_path": str(tmp_path / "crop.png")})
    assert result["ok"] and not result["data"]["cropped"]
    assert result["warnings"]


def test_encoding_failure_leaves_no_files(tmp_path, monkeypatch):
    image = white_image()
    image[40, 50] = 0
    conn = connection_for(image)
    original_encode = cv2.imencode
    monkeypatch.setattr(
        cv2,
        "imencode",
        lambda ext, pixels: (False, None) if ext == ".png" else original_encode(ext, pixels),
    )
    result = capture_cropped_screenshot(conn, {"file_path": str(tmp_path / "crop.png")})
    assert result["code"] == "IMAGE_ENCODE_FAILED"
    assert list(tmp_path.iterdir()) == []


def test_parent_is_a_file_rejected_without_com(tmp_path):
    parent = tmp_path / "parent"
    parent.write_bytes(b"keep")
    conn = connection_for(white_image())
    result = capture_cropped_screenshot(conn, {"file_path": str(parent / "crop.png")})
    assert result["code"] == "FILE_IO_ERROR"
    assert parent.read_bytes() == b"keep"
    conn.ensure_connected.assert_not_called()


def test_missing_com_api_is_classified(tmp_path):
    conn = connection_for(white_image())
    conn.active_window.ActiveViewer.CaptureToFile.side_effect = AttributeError("CaptureToFile")
    result = capture_cropped_screenshot(conn, {"file_path": str(tmp_path / "crop.png")})
    assert result["code"] == "UNSUPPORTED_CAPABILITY"
    assert list(tmp_path.iterdir()) == []


def test_partial_write_is_cleaned_up(tmp_path, monkeypatch):
    image = white_image()
    image[40, 50] = 0
    conn = connection_for(image)
    output = tmp_path / "crop.png"
    original_open = Path.open

    class FailingWriter:
        def __enter__(self):
            self.stream = original_open(output, "xb")
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, data):
            self.stream.write(data[:10])
            raise OSError("Disk full")

    def failing_open(path, mode="r", *args, **kwargs):
        if path == output and mode == "xb":
            return FailingWriter()
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    result = capture_cropped_screenshot(conn, {"file_path": str(output)})
    assert result["code"] == "FILE_IO_ERROR" and not result["effects"]["file_created"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("color", [(0.2, 0.3), (float("nan"), 0.2, 0.3), (2, 0, 0)])
def test_invalid_original_background_never_changes_view(tmp_path, color):
    conn = connection_for(white_image())
    conn.app.SystemService.Evaluate.side_effect = None
    conn.app.SystemService.Evaluate.return_value = color
    result = capture_cropped_screenshot(conn, {"file_path": str(tmp_path / "crop.png")})
    assert result["code"] == "BACKGROUND_READ_FAILED"
    conn.active_window.ActiveViewer.PutBackgroundColor.assert_not_called()
    conn.active_window.ActiveViewer.CaptureToFile.assert_not_called()


def test_white_setting_failure_still_restores_original(tmp_path):
    conn = connection_for(white_image())
    viewer = conn.active_window.ActiveViewer
    original_setter = viewer.PutBackgroundColor.side_effect

    def fail_after_change(color):
        original_setter(color)
        if tuple(color) == (1, 1, 1):
            raise RuntimeError("Failed after setting white")

    viewer.PutBackgroundColor.side_effect = fail_after_change
    result = capture_cropped_screenshot(conn, {"file_path": str(tmp_path / "crop.png")})
    assert result["code"] == "COM_ERROR" and result["effects"]["background_restored"]
    assert viewer.background == [0.2, 0.2, 0.4]
    viewer.CaptureToFile.assert_not_called()


def test_unapplied_white_background_is_not_captured(tmp_path):
    conn = connection_for(white_image())
    viewer = conn.active_window.ActiveViewer
    viewer.PutBackgroundColor.side_effect = None
    result = capture_cropped_screenshot(conn, {"file_path": str(tmp_path / "crop.png")})
    assert result["code"] == "WHITE_BACKGROUND_FAILED"
    assert result["effects"]["background_restored"]
    viewer.CaptureToFile.assert_not_called()


@pytest.mark.parametrize("silent,capture_failure", [(False, False), (True, False), (False, True)])
def test_restore_failure_is_not_hidden(tmp_path, silent, capture_failure):
    image = white_image()
    image[40, 50] = 0
    conn = connection_for(image)
    viewer = conn.active_window.ActiveViewer
    original_setter = viewer.PutBackgroundColor.side_effect

    def fail_restore(color):
        if tuple(color) == (1, 1, 1):
            original_setter(color)
        elif not silent:
            raise RuntimeError("Restore failed")

    viewer.PutBackgroundColor.side_effect = fail_restore
    if capture_failure:
        viewer.CaptureToFile.side_effect = RuntimeError("Capture also failed")
    result = capture_cropped_screenshot(conn, {"file_path": str(tmp_path / "crop.png")})
    assert result["code"] == "BACKGROUND_RESTORE_FAILED" and not result["ok"]
    assert not result["effects"]["background_restored"]
    assert not result["recovery"]["retry_safe"]
    assert result["recovery"]["original_background_rgb"] == [0.2, 0.2, 0.4]
    assert bool(result["diagnostics"]) == capture_failure
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("empty", [False, True])
def test_mcp_result_preserves_structured_success_and_failure(tmp_path, empty):
    from catia_mcp.server import CATIAMCPServer

    image = white_image()
    if not empty:
        image[40, 50] = 0
    server = CATIAMCPServer()
    conn = connection_for(image)
    server.connection = conn
    server.export_tools.conn = conn
    request = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(
            name="catia_screenshot",
            arguments={"file_path": str(tmp_path / "crop.png")},
        ),
    )
    response = asyncio.run(server.server.request_handlers[CallToolRequest](request)).root
    assert response.isError == empty
    assert response.structuredContent["ok"] == (not empty)
    assert response.structuredContent["code"] == ("EMPTY_VIEW" if empty else "OK")
    assert json.loads(response.content[0].text) == response.structuredContent
    conn.connect.assert_not_called()


def test_mcp_invalid_path_does_not_launch_catia():
    from catia_mcp.server import CATIAMCPServer

    server = CATIAMCPServer()
    conn = connection_for(white_image())
    server.connection = conn
    server.export_tools.conn = conn
    request = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(
            name="catia_screenshot",
            arguments={"file_path": "relative.png"},
        ),
    )
    response = asyncio.run(server.server.request_handlers[CallToolRequest](request)).root
    assert response.isError and response.structuredContent["code"] == "INVALID_ARGUMENT"
    conn.connect.assert_not_called()
    conn.ensure_connected.assert_not_called()


def test_only_original_screenshot_tool_is_registered():
    names = [
        tool["name"] for tool in ExportTools(connection_for(white_image())).get_tool_definitions()
    ]
    assert names.count("catia_screenshot") == 1
    assert "catia_screenshot_cropped" not in names
    assert len(names) == 4


def test_removed_dimension_arguments_are_rejected(tmp_path):
    conn = connection_for(white_image())
    result = ExportTools(conn).execute(
        "catia_screenshot",
        {
            "file_path": str(tmp_path / "crop.png"),
            "height": 1080,
        },
    )
    assert result["code"] == "INVALID_ARGUMENT"
    conn.ensure_connected.assert_not_called()


def test_smoke_script_does_not_mark_structured_screenshot_error_as_pass():
    path = Path(__file__).resolve().parents[1] / "scripts" / "gsd_smoke_test.py"
    spec = importlib.util.spec_from_file_location("gsd_smoke_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert not module.step(
        "screenshot",
        lambda: {
            "ok": False,
            "code": "BACKGROUND_RESTORE_FAILED",
            "message": "Restore failed",
        },
    )
    assert module.results[-1][0] == "FAIL"


def test_ui_restoration_failure_is_not_published_as_a_png(tmp_path, monkeypatch):
    image = white_image()
    image[40, 50] = 0
    conn = connection_for(image)
    from catia_mcp.viewport import ViewportError

    class FailingRestore:
        original_layout = 2
        original_compass = True

        def __init__(self, app, window):
            pass

        def hide(self):
            pass

        def restore(self):
            raise ViewportError("VIEW_UI_RESTORE_FAILED", "Restore failed")

    monkeypatch.setattr("catia_mcp.screenshot.ViewportUI", FailingRestore)
    result = capture_cropped_screenshot(conn, {"file_path": str(tmp_path / "crop.png")})
    assert result["code"] == "VIEW_UI_RESTORE_FAILED" and not result["ok"]
    assert result["effects"]["background_restored"]
    assert not result["effects"]["viewport_restored"]
    assert not result["recovery"]["retry_safe"]
    assert list(tmp_path.iterdir()) == []


def test_region_excludes_axis_but_keeps_all_content_inside(tmp_path):
    image = white_image()
    image[25:35, 40:50] = 0
    image[20, 15] = 254  # isolated pale point in the selected region
    image[70:75, 90:95] = 0  # navigation-axis stand-in, deliberately outside region
    conn = connection_for(image)
    output = tmp_path / "crop.png"
    result = capture_cropped_screenshot(
        conn,
        {
            "file_path": str(output),
            "padding": 2,
            "region": {"left": 10, "top": 10, "right": 80, "bottom": 60},
        },
    )
    assert result["ok"]
    assert result["data"]["crop_box"] == {"left": 13, "top": 18, "right": 52, "bottom": 37}
    pixels = cv2.imdecode(np.frombuffer(output.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    np.testing.assert_array_equal(pixels, image[18:37, 13:52])


@pytest.mark.parametrize(
    "region",
    [
        None,
        [],
        {},
        {"left": 0, "top": 0, "right": 1},
        {"left": 0, "top": 0, "right": 1, "bottom": 1, "width": 1},
        {"left": -1, "top": 0, "right": 10, "bottom": 10},
        {"left": True, "top": 0, "right": 10, "bottom": 10},
        {"left": 0, "top": 0, "right": 0, "bottom": 10},
        {"left": 0, "top": 10, "right": 10, "bottom": 9},
    ],
)
def test_invalid_region_rejected_before_capture(tmp_path, region):
    conn = connection_for(white_image())
    result = capture_cropped_screenshot(
        conn,
        {
            "file_path": str(tmp_path / "crop.png"),
            "region": region,
        },
    )
    assert result["code"] == "INVALID_ARGUMENT"
    conn.ensure_connected.assert_not_called()


def test_region_beyond_capture_bounds_rejected_after_restoring_view(tmp_path):
    conn = connection_for(white_image())
    result = capture_cropped_screenshot(
        conn,
        {
            "file_path": str(tmp_path / "crop.png"),
            "region": {"left": 0, "top": 0, "right": 101, "bottom": 80},
        },
    )
    assert result["code"] == "INVALID_ARGUMENT"
    assert result["effects"]["background_restored"] and result["effects"]["viewport_restored"]
    assert list(tmp_path.iterdir()) == []
