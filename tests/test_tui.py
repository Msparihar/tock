"""One end-to-end pass through the app, headless. It caught a real bug: a method
named `set_timer` hid Textual's own and crashed the app on the first resize."""

import pytest

from tock.session import Session
from tock.tui.app import TockApp
from tock.tui.screens import RingScreen


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setenv("TOCK_MUTE", "1")


async def test_add_ring_snooze_and_persist(tmp_path):
    path = tmp_path / "state.json"
    app = TockApp(Session(path))
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.resize_terminal(150, 44)
        await pilot.pause(0.2)
        await pilot.press("n")
        await pilot.press(*"in 2s")
        await pilot.press("tab", *"Tea")
        await pilot.press("ctrl+s")
        await pilot.pause(3.5)
        assert isinstance(app.screen, RingScreen)
        await pilot.press("s")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, RingScreen)
        [tea] = app.session.engine.alarms
        assert tea.label == "Tea" and tea.snoozed_until is not None

    reopened = Session(path)
    [tea] = reopened.engine.alarms
    assert tea.snoozed_until is not None  # the snooze survived a restart


async def test_tabs_timer_and_stopwatch(tmp_path):
    app = TockApp(Session(tmp_path / "state.json"))
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("3")
        await pilot.click("#t-1m")
        await pilot.pause(0.3)
        assert app.countdown.running and app.countdown.duration == 60
        await pilot.press("plus")
        assert app.countdown.duration == 120
        await pilot.press("4", "space")
        await pilot.pause(0.2)
        await pilot.press("l", "l")
        assert len(app.stopwatch.laps) == 2
