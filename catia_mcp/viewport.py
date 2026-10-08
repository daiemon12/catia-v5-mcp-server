"""Temporary CATIA tree/compass visibility with verified restoration on Windows."""

from __future__ import annotations

import time
from typing import Any


class ViewportError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _find_menu_window(caption: str) -> int:
    import win32gui

    matches = []

    def collect(hwnd: int, _unused: Any) -> None:
        if (
            win32gui.IsWindowVisible(hwnd)
            and win32gui.GetWindowText(hwnd).startswith(caption)
            and win32gui.GetMenu(hwnd)
        ):
            matches.append(hwnd)

    win32gui.EnumWindows(collect, None)
    if len(matches) != 1:
        raise ViewportError("VIEW_UI_UNAVAILABLE", "Cannot identify one CATIA menu window")
    return matches[0]


def _menu_states(hwnd: int) -> dict[int, bool]:
    import win32con
    import win32gui

    root = win32gui.GetMenu(hwnd)
    if not root:
        raise ViewportError("VIEW_UI_UNAVAILABLE", "CATIA menu is unavailable")
    win32gui.SendMessageTimeout(hwnd, win32con.WM_INITMENU, root, 0, win32con.SMTO_ABORTIFHUNG, 100)
    states = {}

    def scan(menu: int) -> None:
        for index in range(win32gui.GetMenuItemCount(menu)):
            submenu = win32gui.GetSubMenu(menu, index)
            if submenu:
                # CATIA's owner-drawn menus cache checkmarks until initialization.
                win32gui.SendMessageTimeout(
                    hwnd,
                    win32con.WM_INITMENUPOPUP,
                    submenu,
                    index,
                    win32con.SMTO_ABORTIFHUNG,
                    100,
                )
                scan(submenu)
            else:
                command = win32gui.GetMenuItemID(menu, index)
                if command > 0:
                    checked = bool(
                        win32gui.GetMenuState(menu, index, win32con.MF_BYPOSITION)
                        & win32con.MF_CHECKED
                    )
                    if command in states and states[command] != checked:
                        raise ViewportError("VIEW_UI_UNAVAILABLE", "Conflicting menu checkmarks")
                    states[command] = checked

    scan(root)
    return states


def _pump_messages() -> None:
    import pythoncom

    pythoncom.PumpWaitingMessages()


class ViewportUI:
    """Discover the Compass command from its checkmark change, never a fixed ID."""

    def __init__(self, app: Any, window: Any) -> None:
        self.app = app
        self.window = window
        self.original_layout = int(window.Layout)
        if self.original_layout not in {1, 2}:
            raise ViewportError("VIEW_UI_UNAVAILABLE", "A visible geometry viewer is required")
        self.hwnd = _find_menu_window(str(app.Caption))
        self.compass_command: int | None = None
        self.original_compass: bool | None = None
        self.baseline: dict[int, bool] = {}
        self.command_requested = False

    def _wait(self, predicate: Any) -> dict[int, bool]:
        deadline = time.monotonic() + 2.0
        while True:
            _pump_messages()
            states = _menu_states(self.hwnd)
            if predicate(states):
                return states
            if time.monotonic() >= deadline:
                raise ViewportError(
                    "VIEW_UI_STATE_UNKNOWN", "Viewport menu state change was not verified"
                )
            time.sleep(0.05)

    def _set_compass(self, visible: bool) -> None:
        states = _menu_states(self.hwnd)
        if self.compass_command not in states:
            raise ViewportError("VIEW_UI_STATE_UNKNOWN", "Compass menu item disappeared")
        if states[self.compass_command] != visible:
            self.app.StartCommand("Compass")
            self._wait(lambda values: values.get(self.compass_command) == visible)

    def hide(self) -> None:
        # Discover before changing Layout: its menu checkmark updates asynchronously
        # and must not be mistaken for the Compass command's state change.
        self.baseline = _menu_states(self.hwnd)
        self.command_requested = True
        self.app.StartCommand("Compass")

        def changed(values: dict[int, bool]) -> list[int]:
            return [
                key
                for key, value in self.baseline.items()
                if key in values and value != values[key]
            ]

        first = self._wait(lambda values: bool(changed(values)))
        # A delayed Layout update may change another checkmark during the first
        # toggle. Only Compass changes on BOTH toggles; Layout cannot reverse.
        self.app.StartCommand("Compass")

        def reversed_changes(values: dict[int, bool]) -> list[int]:
            return [key for key in changed(first) if values.get(key) != first[key]]

        states = self._wait(lambda values: len(reversed_changes(values)) == 1)
        self.compass_command = reversed_changes(states)[0]
        self.original_compass = self.baseline[self.compass_command]
        self._set_compass(False)
        self.window.Layout = 1  # catWindowGeomOnly
        self.window.ActiveViewer.Update()
        if int(self.window.Layout) != 1:
            raise ViewportError("VIEW_UI_UNAVAILABLE", "Geometry-only layout was not applied")

    def restore(self) -> None:
        errors = []
        try:
            if self.command_requested and self.compass_command is None:
                states = _menu_states(self.hwnd)
                changes = [
                    key
                    for key, value in self.baseline.items()
                    if key in states and value != states[key]
                ]
                if len(changes) != 1:
                    raise ViewportError(
                        "VIEW_UI_STATE_UNKNOWN", "Original compass state is unknown"
                    )
                self.compass_command = changes[0]
                self.original_compass = self.baseline[self.compass_command]
            if self.compass_command is not None:
                self._set_compass(bool(self.original_compass))
        except Exception as exc:  # noqa: BLE001 -- also restore layout after compass failure
            errors.append(str(exc))
        try:
            self.window.Layout = self.original_layout
            self.window.ActiveViewer.Update()
            if int(self.window.Layout) != self.original_layout:
                raise RuntimeError("Original tree layout was not restored")
        except Exception as exc:  # noqa: BLE001 -- report all restoration failures
            errors.append(str(exc))
        if errors:
            raise ViewportError("VIEW_UI_RESTORE_FAILED", "; ".join(errors))
