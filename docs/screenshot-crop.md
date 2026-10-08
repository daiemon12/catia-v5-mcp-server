# Cropped CATIA screenshots

`catia_screenshot` temporarily hides the specification tree and compass, sets the
current CATIA view background to white, captures the view, then restores and
verifies the original UI and background. It crops the requested region, removes
outer white margins and saves a lossless PNG. It uses CATIA's BMP capture and
`opencv-python-headless`; it does not require an OpenCV GUI or a CAA DLL.

## Call

```json
{
  "name": "catia_screenshot",
  "arguments": {
    "file_path": "C:/screenshots/part-cropped.png",
    "padding": 16,
    "white_tolerance": 0,
    "region": {"left": 0, "top": 0, "right": 1044, "bottom": 595}
  }
}
```

| Input | Contract |
| --- | --- |
| `file_path` | Required absolute path ending in `.png`. Parent directories are created. Existing files are rejected, including files appearing during capture. |
| `padding` | Integer 0–4096, default 16. Pixels retained around content; limited by original image edges. |
| `white_tolerance` | Integer 0–32, default 0. A pixel counts as background only if **all** RGB channels are at least `255 - white_tolerance`. |
| `region` | Optional source-pixel rectangle with exactly `left`, `top`, `right`, `bottom`. Non-negative integers, positive width/height, within the captured image. Left/top inclusive; right/bottom exclusive. Default: whole capture. |

The example region fits the verified 1044×695 view: all desired model content is
above row 595, while the lower-right navigation reference axis is below it.
Choose coordinates for the actual current view; these values are not defaults.
**Everything outside `region` is discarded, including any geometry there.**
Padding stays inside the region. No region means the reference axis is retained
and can limit trimming; the result includes a warning. This tool does not hide
the reference axis or infer which disconnected pixels belong to the model.

This replaces the original screenshot implementation. There is one screenshot
tool: `catia_screenshot`. Only PNG output is accepted; the old JPEG/BMP/TIFF output
path and silently ignored width/height arguments are removed.

Unknown arguments are rejected. There are no width/height inputs: the tool does
not resize or claim a requested capture resolution. Use a new filename for every
capture. Dependencies are included in both `pyproject.toml` and `requirements.txt`.
Install the project normally with `python -m pip install -e .` and restart the MCP
server so the new tool is listed.

## Result

The MCP response includes `structuredContent` and the same JSON as text.
`ok` and `code` determine operation success; failures set MCP `isError=true`.
Schema-invalid calls can be rejected earlier by the MCP SDK with its own error text.
Image pixels are saved locally; the tool returns their path, not inline image content.

`data` reports `file_path`, `original_width`, `original_height`, final `width` and
`height`, `crop_box`, `padding`, `white_tolerance`, `region`, `ui_removed` and `cropped`.
`crop_box` uses original pixel coordinates: left/top are inclusive; right/bottom
are exclusive. No scaling or camera change occurs. `effects` reports file
creation, `model_changed=false`, verified `background_restored` and
`viewport_restored` after capture
begins; `operation_id` identifies the call. Original and capture background RGB
values (0–1), original window layout and compass visibility are reported in `data`.

| Code | Meaning |
| --- | --- |
| `OK` | PNG saved. An unchanged crop is successful with a warning. |
| `INVALID_ARGUMENT` | Invalid path, range, type or unknown input. These are rejected before COM access, except region bounds relative to capture size, which are checked after capture and restoration. |
| `OUTPUT_EXISTS` | Output already exists; choose a new filename. |
| `EMPTY_VIEW` | All pixels fall within the white threshold; no output is created. |
| `CAPTURE_FAILED` | CATIA returned without producing a non-empty capture. |
| `IMAGE_DECODE_FAILED` / `IMAGE_ENCODE_FAILED` | Capture cannot be decoded or PNG cannot be encoded. |
| `COM_ERROR` / `UNSUPPORTED_CAPABILITY` | CATIA connection/capture failed or the Automation API is unavailable. |
| `BACKGROUND_READ_FAILED` / `WHITE_BACKGROUND_FAILED` | Original color is invalid or setting white could not be verified; no PNG is created. |
| `BACKGROUND_RESTORE_FAILED` | Restoration or redraw/readback failed. No PNG is created; recovery includes the original RGB and retry is unsafe until the view is restored. |
| `VIEW_UI_UNAVAILABLE` | Cannot identify one visible CATIA menu window, or the geometry viewer/layout is unavailable. |
| `VIEW_UI_STATE_UNKNOWN` | A requested menu state change could not be verified. No PNG is created. |
| `VIEW_UI_RESTORE_FAILED` | Original UI state could not be restored or verified. No PNG is created; recovery reports known original state and marks retry unsafe. |
| `FILE_IO_ERROR` / `IMAGE_PROCESSING_FAILED` | Filesystem or image-processing operation failed. |

Temporary BMP files are removed on success and failure. The tool does not retry
automatically or change CATIA document/model state. Resolve a reported error
before retrying; if an output was created, use another filename.

## Limits and validation

- No manual background setup is required. The tool reads the original RGB, sets
  white, redraws and verifies it, captures, then restores and verifies the original
  before image processing. It attempts restoration even if white setup or capture
  fails. It does not save global visualization preferences or move the camera.
- Tree visibility uses `SpecsAndGeomWindow.Layout`; compass visibility uses
  `StartCommand("Compass")` and Windows menu checkmark readback. The command ID
  is discovered from two reversals, never hardcoded. This distinguishes delayed
  tree menu updates from compass changes and preserves an initially hidden compass.
  Both original layout and compass visibility are restored on failure as well.
- Requires an interactive Windows desktop and exactly one visible CATIA menu
  window matching the connected application's caption. The `Compass` command
  must be available. Do not change the view or menus while a capture is running.
  Modal dialogs, other sessions and localized command behavior are not validated.
- Every foreground pixel contributes to the bounding box. Independent points,
  one-pixel lines, annotations and model axes inside the region are retained.
  Edge annotations can prevent further trimming.
- No largest-contour selection or small-component filtering is used. Stray pixels
  are retained, as removing them could remove a real point or fine line.
- Default tolerance 0 removes exact white only. A larger tolerance can remove
  very pale content; use it deliberately. The temporary BMP avoids JPEG artifacts.
- All-white capture is an error. This also includes genuinely white-only geometry
  that cannot be distinguished from the white background from pixels alone.
- This feature inherits upstream's synchronous COM execution. It does not add a
  dedicated STA worker, modal-dialog handling or COM timeout cancellation.
  UI-state waits are bounded, but a timeout does not cancel a queued CATIA command.
  **Experimental: live-validated on one CATIA P3 V5-6R2020 / B30 installation;
  not accepted across CATIA releases or locales.**

Run offline tests: `python -m pytest tests test_server.py -q`.
On 2026-10-08, 68 offline tests passed. A real MCP stdio call produced a 277×293
PNG from a 1044×695 view with the example region. Pixel comparison against an
independent white-background capture confirmed identical retained pixels and
only white pixels removed inside the region. Original background, layout,
compass visibility and document saved state were restored; an initially hidden
tree/compass remained hidden. Existing output and relative output paths were
rejected without overwriting the PNG. CATIA locale was not verified.

Before broader production acceptance, use a real colored-background view containing a
model, separate point, fine lines and annotations. Verify the saved PNG preserves
all foreground, reported dimensions match the file, model/camera/background are
unchanged after capture, the image background is white, and an empty view and
existing output path fail as documented. Record
CATIA release/build, locale, source branch/commit/dirty state and the tool result.

Background methods and normalized RGB values follow the [CATIA Viewer Automation
reference](https://catiadesign.org/_doc/V5Automation/generated/interfaces/InfInterfaces/interface_Viewer_13459.htm).
