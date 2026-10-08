"""Lossless capture and conservative white-border trimming for CATIA views."""

from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

import cv2
import numpy as np

from catia_mcp.viewport import ViewportError, ViewportUI


class BackgroundError(RuntimeError):
    """A requested view-background change or restoration could not be verified."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def read_viewer_background(connection: Any, viewer: Any) -> tuple[float, ...]:
    """Read CATIA's output SAFEARRAY using its VBScript Automation boundary."""
    script = (
        "Function ReadBackground(viewer)\n"
        "Dim color(2)\n"
        "viewer.GetBackgroundColor color\n"
        "ReadBackground = color\n"
        "End Function"
    )
    values = connection.app.SystemService.Evaluate(script, 0, "ReadBackground", [viewer])
    color = tuple(float(value) for value in values)
    if len(color) != 3 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in color):
        raise BackgroundError("BACKGROUND_READ_FAILED", "CATIA returned an invalid RGB background")
    return color


def _capture_on_white(connection: Any, viewer: Any, raw: Path, result: dict[str, Any]) -> None:
    original = read_viewer_background(connection, viewer)
    result["data"]["original_background_rgb"] = list(original)
    result["effects"]["background_restored"] = False
    capture_error = None
    restore_error = None
    try:
        viewer.PutBackgroundColor((1.0, 1.0, 1.0))
        viewer.Update()
        if any(abs(v - 1.0) > 1e-6 for v in read_viewer_background(connection, viewer)):
            raise BackgroundError(
                "WHITE_BACKGROUND_FAILED", "CATIA did not apply a white background"
            )
        viewer.CaptureToFile(4, str(raw))
    except Exception as exc:  # noqa: BLE001 -- restore even when capture fails
        capture_error = exc
    finally:
        try:
            viewer.PutBackgroundColor(original)
            viewer.Update()
            restored = read_viewer_background(connection, viewer)
            if any(abs(a - b) > 1e-6 for a, b in zip(original, restored)):
                raise RuntimeError("Restored background does not match the original RGB")
            result["effects"]["background_restored"] = True
        except Exception as exc:  # noqa: BLE001 -- expose restoration failure separately
            restore_error = exc
    if restore_error is not None:
        if capture_error is not None:
            result["diagnostics"].append({"stage": "capture", "message": str(capture_error)})
        result["recovery"] = {
            "retry_safe": False,
            "original_background_rgb": list(original),
            "next_actions": ["Restore the viewer background before retrying"],
        }
        raise BackgroundError("BACKGROUND_RESTORE_FAILED", str(restore_error))
    if capture_error is not None:
        raise capture_error


def _capture_focused_view(connection: Any, viewer: Any, raw: Path, result: dict[str, Any]) -> None:
    ui = ViewportUI(connection.app, connection.active_window)
    result["data"]["original_layout"] = ui.original_layout
    result["effects"]["viewport_restored"] = False
    capture_error = None
    restore_error = None
    try:
        ui.hide()
        result["data"]["original_compass_visible"] = ui.original_compass
        _capture_on_white(connection, viewer, raw, result)
    except Exception as exc:  # noqa: BLE001 -- restore UI on every capture outcome
        capture_error = exc
    finally:
        try:
            ui.restore()
            result["effects"]["viewport_restored"] = True
        except Exception as exc:  # noqa: BLE001 -- expose incomplete UI recovery
            restore_error = exc
    if restore_error is not None:
        if capture_error is not None:
            result["diagnostics"].append({"stage": "capture", "message": str(capture_error)})
        result["recovery"].update(
            {
                "retry_safe": False,
                "original_layout": ui.original_layout,
                "original_compass_visible": ui.original_compass,
                "next_actions": ["Restore the viewer UI and background before retrying"],
            }
        )
        raise restore_error
    if capture_error is not None:
        raise capture_error


def crop_white_border(
    image: np.ndarray, padding: int, white_tolerance: int
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Keep all non-white pixels; return a crop and its half-open source box.

    Near-white means every BGR channel is >= 255 - white_tolerance.
    No component filtering, erosion, resizing or largest-contour selection.
    """
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Expected a non-empty uint8 BGR image")
    if not image.size:
        raise ValueError("Expected a non-empty uint8 BGR image")
    for name, value, maximum in (
        ("padding", padding, 4096),
        ("white_tolerance", white_tolerance, 32),
    ):
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f"{name} must be an integer between 0 and {maximum}")

    lower = (255 - white_tolerance,) * 3
    foreground = cv2.bitwise_not(cv2.inRange(image, lower, (255, 255, 255)))
    x, y, width, height = cv2.boundingRect(foreground)
    if width == 0 or height == 0:
        raise ValueError("EMPTY_VIEW: no pixels outside the white threshold")
    source_height, source_width = image.shape[:2]
    left, top = max(0, x - padding), max(0, y - padding)
    right = min(source_width, x + width + padding)
    bottom = min(source_height, y + height + padding)
    return image[top:bottom, left:right], (left, top, right, bottom)


def capture_cropped_screenshot(connection: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """Capture on temporary white background, restore it, trim, and create PNG.

    Validates before COM access, never overwrites an existing output, and cleans
    temporary capture files on success or failure. The caller owns COM execution.
    """
    result: dict[str, Any] = {
        "ok": False,
        "code": "INVALID_ARGUMENT",
        "operation_id": str(uuid4()),
        "tool": "catia_screenshot",
        "message": "",
        "data": {},
        "effects": {"model_changed": False, "file_created": False},
        "diagnostics": [],
        "warnings": [],
        "recovery": {"retry_safe": True},
    }
    stage = "validation"
    try:
        if set(arguments) - {"file_path", "padding", "white_tolerance", "region"}:
            raise ValueError(
                "Unknown argument; allowed: file_path, padding, white_tolerance, region"
            )
        file_path = arguments.get("file_path")
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("file_path must be a non-empty absolute PNG path")
        output = Path(file_path)
        if not output.is_absolute() or output.suffix.lower() != ".png":
            raise ValueError("file_path must be an absolute path ending in .png")
        output = output.resolve()
        padding = arguments.get("padding", 16)
        tolerance = arguments.get("white_tolerance", 0)
        for name, value, maximum in (
            ("padding", padding, 4096),
            ("white_tolerance", tolerance, 32),
        ):
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError(f"{name} must be an integer between 0 and {maximum}")
        region = arguments.get("region")
        if "region" in arguments:
            keys = {"left", "top", "right", "bottom"}
            if not isinstance(region, dict) or set(region) != keys:
                raise ValueError("region must contain exactly left, top, right and bottom")
            if any(type(region[key]) is not int or region[key] < 0 for key in keys):
                raise ValueError("region coordinates must be non-negative integers")
            if region["right"] <= region["left"] or region["bottom"] <= region["top"]:
                raise ValueError("region must have positive width and height")
        if output.exists():
            result.update(code="OUTPUT_EXISTS", message="Choose a new path; output already exists")
            return result

        stage = "file"
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="catia-capture-", dir=output.parent) as temporary:
            raw = Path(temporary) / "capture.bmp"
            stage = "capture"
            connection.ensure_connected()
            viewer = connection.active_window.ActiveViewer
            _capture_focused_view(connection, viewer, raw, result)
            stage = "image"
            # Byte-based I/O supports Unicode paths on Windows.
            if not raw.is_file() or not raw.stat().st_size:
                result.update(code="CAPTURE_FAILED", message="CATIA did not produce a BMP image")
                return result
            image = cv2.imdecode(np.frombuffer(raw.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                result.update(code="IMAGE_DECODE_FAILED", message="Cannot decode CATIA capture")
                return result
            source_height, source_width = image.shape[:2]
            if region is None:
                region = {"left": 0, "top": 0, "right": source_width, "bottom": source_height}
                result["warnings"].append(
                    "Navigation reference axis is retained; supply region to exclude that corner"
                )
            if region["right"] > source_width or region["bottom"] > source_height:
                result.update(code="INVALID_ARGUMENT", message="region exceeds the captured image")
                return result
            left, top, right, bottom = (region[key] for key in ("left", "top", "right", "bottom"))
            try:
                cropped, local_box = crop_white_border(
                    image[top:bottom, left:right], padding, tolerance
                )
                box = (
                    left + local_box[0],
                    top + local_box[1],
                    left + local_box[2],
                    top + local_box[3],
                )
            except ValueError as exc:
                result.update(code="EMPTY_VIEW", message=str(exc))
                return result
            encoded_ok, encoded = cv2.imencode(".png", cropped)
            if not encoded_ok:
                result.update(code="IMAGE_ENCODE_FAILED", message="Cannot encode cropped PNG")
                return result

            # Encode fully before opening the destination. Exclusive creation
            # also protects files created by another request during capture.
            stage = "file"
            created = False
            try:
                with output.open("xb") as stream:
                    created = True
                    stream.write(encoded.tobytes())
            except FileExistsError:
                result.update(code="OUTPUT_EXISTS", message="Output appeared during capture")
                return result
            except BaseException:
                if created:
                    output.unlink(missing_ok=True)
                raise

            result["effects"]["file_created"] = True
            result["data"].update(
                {
                    "file_path": str(output),
                    "original_width": source_width,
                    "original_height": source_height,
                    "width": int(cropped.shape[1]),
                    "height": int(cropped.shape[0]),
                    "crop_box": dict(zip(("left", "top", "right", "bottom"), box)),
                    "padding": padding,
                    "white_tolerance": tolerance,
                    "cropped": box != (0, 0, source_width, source_height),
                    "capture_background_rgb": [1.0, 1.0, 1.0],
                    "region": region,
                    "ui_removed": ["specification_tree", "compass"],
                }
            )
            if not result["data"]["cropped"]:
                result["warnings"].append("No removable white border at the requested padding")
            if tolerance:
                result["warnings"].append("Near-white pixels within tolerance count as background")
            result.update(ok=True, code="OK", message="Cropped screenshot saved as PNG")
    except Exception as exc:  # noqa: BLE001 -- classify failures at the tool boundary
        codes = {
            "validation": "INVALID_ARGUMENT",
            "capture": "COM_ERROR",
            "image": "IMAGE_PROCESSING_FAILED",
            "file": "FILE_IO_ERROR",
        }
        code = codes[stage]
        if isinstance(exc, (BackgroundError, ViewportError)):
            code = exc.code
        elif stage == "capture" and isinstance(exc, AttributeError):
            code = "UNSUPPORTED_CAPABILITY"
        result.update(code=code, message=str(exc))
    return result
