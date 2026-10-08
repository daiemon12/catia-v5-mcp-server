"""Visibility-state tests independent of Windows menu or CATIA implementations."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from catia_mcp import viewport


@pytest.fixture
def fake_menu(monkeypatch):
    states = {9001: True, 9002: True}
    app = SimpleNamespace(Caption="CATIA V5", StartCommand=Mock())

    class Window:
        def __init__(self):
            self._layout = 2
            self.ActiveViewer = SimpleNamespace(Update=Mock())

        @property
        def Layout(self):
            return self._layout

        @Layout.setter
        def Layout(self, value):
            self._layout = value
            states[9002] = value == 2

    window = Window()

    def toggle(name):
        assert name == "Compass"
        states[9001] = not states[9001]

    app.StartCommand.side_effect = toggle
    monkeypatch.setattr(viewport, "_find_menu_window", lambda caption: 123)
    monkeypatch.setattr(viewport, "_menu_states", lambda hwnd: dict(states))
    monkeypatch.setattr(viewport, "_pump_messages", lambda: None)
    return app, window, states


@pytest.mark.parametrize("visible", [True, False])
@pytest.mark.parametrize("layout", [1, 2])
def test_hide_and_restore_original_state(fake_menu, visible, layout):
    app, window, states = fake_menu
    states[9001] = visible
    window.Layout = layout
    ui = viewport.ViewportUI(app, window)
    ui.hide()
    assert not states[9001] and window.Layout == 1
    assert ui.compass_command == 9001  # discovered rather than a hardcoded native ID
    assert ui.original_compass == visible
    ui.restore()
    assert states[9001] == visible and window.Layout == layout
    assert app.StartCommand.call_count == (4 if visible else 2)


def test_invalid_initial_layout_does_not_change_ui(fake_menu):
    app, window, states = fake_menu
    window.Layout = 0
    with pytest.raises(viewport.ViewportError, match="visible geometry"):
        viewport.ViewportUI(app, window)
    app.StartCommand.assert_not_called()
    assert states[9001]


def test_compass_discovery_precedes_layout_change(fake_menu):
    app, window, states = fake_menu
    original_toggle = app.StartCommand.side_effect

    def toggle(name):
        assert window.Layout == 2
        original_toggle(name)

    app.StartCommand.side_effect = toggle
    ui = viewport.ViewportUI(app, window)
    ui.hide()
    assert window.Layout == 1 and not states[9001]
    app.StartCommand.side_effect = original_toggle
    ui.restore()
    assert window.Layout == 2 and states[9001]


def test_delayed_tree_checkmark_is_not_mistaken_for_compass(fake_menu):
    app, window, states = fake_menu
    calls = 0

    def toggle(name):
        nonlocal calls
        assert name == "Compass"
        calls += 1
        if calls == 1:
            states[9002] = False  # delayed menu refresh from a previous layout change
        states[9001] = not states[9001]

    app.StartCommand.side_effect = toggle
    ui = viewport.ViewportUI(app, window)
    ui.hide()
    assert ui.compass_command == 9001
    assert not states[9001]
    ui.restore()
    assert states[9001] and window.Layout == 2


def test_unverified_command_fails_and_still_restores_tree(fake_menu, monkeypatch):
    app, window, states = fake_menu
    app.StartCommand.side_effect = None
    ticks = iter([0.0, 3.0])
    monkeypatch.setattr(viewport.time, "monotonic", lambda: next(ticks))
    ui = viewport.ViewportUI(app, window)
    with pytest.raises(viewport.ViewportError) as error:
        ui.hide()
    assert error.value.code == "VIEW_UI_STATE_UNKNOWN"
    with pytest.raises(viewport.ViewportError) as error:
        ui.restore()
    assert error.value.code == "VIEW_UI_RESTORE_FAILED"
    assert window.Layout == 2 and states[9001]


def test_restore_compass_failure_does_not_skip_tree_restore(fake_menu):
    app, window, _states = fake_menu
    ui = viewport.ViewportUI(app, window)
    ui.hide()
    app.StartCommand.side_effect = RuntimeError("Compass unavailable")
    with pytest.raises(viewport.ViewportError) as error:
        ui.restore()
    assert error.value.code == "VIEW_UI_RESTORE_FAILED"
    assert window.Layout == 2
