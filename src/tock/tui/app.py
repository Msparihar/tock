"""The Textual app. It draws state and forwards clicks and keys to the core;
the rules (when alarms ring, snooze, missed alarms) all live in tock.core."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Input, Label, ProgressBar, Static, TabbedContent, TabPane

from ..core.models import Alarm, format_time
from ..core.parse import ParseError, parse_duration
from ..core.schedule import due_time, humanize_until
from ..core.timers import Countdown, Stopwatch, format_span
from ..session import Session, local_now
from .screens import AlarmForm, RingScreen
from .widgets import BigDigits

SAVE_EVERY = timedelta(seconds=30)  # how often to record "last checked" when nothing else changes
TIMER_PRESETS = ["1m", "3m", "5m", "10m", "25m", "1h"]


def clock_text(now: datetime, clock_24h: bool, colon_on: bool) -> tuple[str, str]:
    sep = ":" if colon_on else " "
    hour = now.hour if clock_24h else (now.hour % 12) or 12
    suffix = "" if clock_24h else ("AM" if now.hour < 12 else "PM")
    return f"{hour:02d}{sep}{now:%M}{sep}{now:%S}", suffix


class TockApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "tock"

    BINDINGS = [
        Binding("1", "tab('clock')", "Clock"),
        Binding("2", "tab('alarms')", "Alarms"),
        Binding("3", "tab('timer')", "Timer"),
        Binding("4", "tab('stopwatch')", "Stopwatch"),
        Binding("n", "new_alarm", "New alarm"),
        Binding("space", "primary", "Start/Stop", show=False),
        Binding("e", "edit_alarm", "Edit", show=False),
        Binding("x", "delete_alarm", "Delete", show=False),
        Binding("u", "undo_delete", "Undo", show=False),
        Binding("l", "lap", "Lap", show=False),
        Binding("r", "reset", "Reset", show=False),
        Binding("plus,equals_sign", "add_minute", "+1 min", show=False),
        Binding("h", "toggle_24h", "12/24h"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self.countdown = Countdown(5 * 60)
        self.stopwatch = Stopwatch()
        self._timer_rang = False
        self._ring_queue: list[tuple[str, Alarm | None]] = []
        self._ringing = False
        self._last_save = local_now()
        self._deleted: Alarm | None = None

    # ---- layout --------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Label("◷ tock", id="brand")
            yield Label("", id="top-next")
            yield Label("", id="top-date")
        with TabbedContent(initial="clock", id="tabs"):
            with TabPane("Clock", id="clock"):
                with Vertical(id="clock-pane"):
                    with Center():
                        with Horizontal(id="clock-row"):
                            yield BigDigits("00:00:00", dim_from=5, id="big-clock")
                            yield Label("", id="ampm")
                    yield Label("", id="clock-date")
                    yield Label("", id="clock-next")
                    yield Label("Coming up", id="soon-title")
                    yield Center(Static("", id="soon-list"), id="soon-wrap")
            with TabPane("Alarms", id="alarms"):
                with Vertical(id="alarms-pane"):
                    with Horizontal(classes="toolbar"):
                        yield Button("＋ New  \\[n]", id="a-new", variant="primary")
                        yield Button("Edit  \\[e]", id="a-edit")
                        yield Button("On / Off  \\[space]", id="a-toggle")
                        yield Button("Delete  \\[x]", id="a-delete", variant="error")
                    yield DataTable(id="alarm-table", cursor_type="row", zebra_stripes=True)
                    yield Label("No alarms yet. Press n or click ＋ New.", id="alarms-empty")
            with TabPane("Timer", id="timer"):
                with Vertical(id="timer-pane"):
                    yield Center(BigDigits("05:00", id="timer-digits"))
                    yield Center(ProgressBar(total=1.0, show_eta=False, show_percentage=False, id="timer-bar"))
                    yield Label("", id="timer-status")
                    with Center():
                        with Horizontal(classes="toolbar", id="timer-presets"):
                            for p in TIMER_PRESETS:
                                yield Button(p, id=f"t-{p}", classes="preset", compact=True)
                            yield Input(placeholder="or type 7m30s ⏎", id="t-custom")
                    with Center():
                        with Horizontal(classes="toolbar"):
                            yield Button("Start  \\[space]", id="t-start", variant="success")
                            yield Button("+1 min  \\[+]", id="t-plus")
                            yield Button("Reset  \\[r]", id="t-reset")
            with TabPane("Stopwatch", id="stopwatch"):
                with Vertical(id="sw-pane"):
                    yield Center(BigDigits("00:00.00", dim_from=5, id="sw-digits"))
                    with Center():
                        with Horizontal(classes="toolbar"):
                            yield Button("Start  \\[space]", id="sw-start", variant="success")
                            yield Button("Lap  \\[l]", id="sw-lap")
                            yield Button("Reset  \\[r]", id="sw-reset")
                    with Center(id="lap-wrap"):
                        yield DataTable(id="lap-table", cursor_type="none", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        s = self.session
        if s.settings.theme in self.available_themes:
            self.theme = s.settings.theme
        alarms = self.query_one("#alarm-table", DataTable)
        for label, key in (("On", "on"), ("Time", "time"), ("Label", "label"), ("Repeat", "repeat"),
                           ("Snooze", "snooze"), ("Next ring", "next")):
            alarms.add_column(label, key=key)
        self.query_one("#lap-table", DataTable).add_columns("Lap", "Lap time", "Total", "")
        # Main-screen buttons are for the mouse; the keyboard uses the shortcuts on them.
        # If they took focus, space would press whichever button was clicked last.
        for button in self.query("TabPane Button"):
            button.can_focus = False
        if s.loaded.recovered_from:
            self.notify(f"The alarm file could not be read ({s.loaded.recovery_reason}). "
                        f"I kept it at {s.loaded.recovered_from} and started fresh.", severity="error", timeout=20)
        self.refresh_alarms()
        self.set_interval(0.5, self.tick)
        self.set_interval(1 / 20, self.fast_tick)
        self.tick()

    # ---- the heartbeat -------------------------------------------------
    def tick(self) -> None:
        s = self.session
        now = local_now()
        if s.changed_on_disk():
            s.reload()
            self.refresh_alarms()
            self.notify("Alarms changed in another terminal; reloaded.", timeout=4)
        result = s.engine.check(now)
        for alarm, due in result.missed:
            when = format_time(due.hour, due.minute, due.second, s.settings.clock_24h)
            self.notify(f"Missed while tock was closed: {alarm.label or 'Alarm'} at {due:%a} {when}",
                        title="Missed alarm", severity="warning", timeout=15)
        for alarm in result.ringing:
            self._ring_queue.append(("alarm", alarm))
        if result.changed or now - self._last_save >= SAVE_EVERY:
            self.save()
        if result.changed:
            self.refresh_alarms()
        self._paint_clock(now)
        self._drain_ring_queue()

    def fast_tick(self) -> None:
        mono = time.monotonic()
        if self.countdown.running or self.countdown.started:
            self._paint_timer(mono)
        if self.countdown.finished(mono) and not self._timer_rang:
            self._timer_rang = True
            self.countdown.pause(mono)
            self._ring_queue.append(("timer", None))
            self._drain_ring_queue()
        if self.stopwatch.running:
            self._paint_stopwatch(mono)

    def save(self) -> None:
        self.session.save()
        self._last_save = local_now()

    # ---- painting ------------------------------------------------------
    def _paint_clock(self, now: datetime) -> None:
        s = self.session
        text, suffix = clock_text(now, s.settings.clock_24h, colon_on=now.microsecond < 500_000)
        self.query_one("#big-clock", BigDigits).value = text
        self.query_one("#ampm", Label).update(suffix)
        self.query_one("#clock-date", Label).update(f"{now:%A, %-d %B %Y}  ·  {now.tzname()}")
        self.query_one("#top-date", Label).update(f"{now:%a %-d %b}  {format_time(now.hour, now.minute, 0, s.settings.clock_24h)}")
        upcoming = s.engine.upcoming(now)
        if upcoming:
            alarm, due = upcoming[0]
            line = f"⏰ {alarm.label or 'Alarm'} · {due:%a} {self._fmt(due)} · {humanize_until(due, now)}"
            snoozed = " (snoozed)" if alarm.snoozed_until else ""
            self.query_one("#clock-next", Label).update(f"Next: {line}{snoozed}")
            self.query_one("#top-next", Label).update(line)
        else:
            self.query_one("#clock-next", Label).update("No alarms on. Press n to add one.")
            self.query_one("#top-next", Label).update("")
        soon = Table.grid(padding=(0, 3))
        for justify in ("left", "right", "left", "right"):
            soon.add_column(justify=justify)
        for alarm, due in upcoming[:5]:
            soon.add_row(f"{due:%a}", Text(self._fmt(due), style="bold"), alarm.label or "Alarm",
                         Text(humanize_until(due, now), style="dim"))
        self.query_one("#soon-list", Static).update(soon if upcoming else "Nothing scheduled.")
        self._paint_next_column(now)

    def _fmt(self, d: datetime) -> str:
        return format_time(d.hour, d.minute, d.second, self.session.settings.clock_24h)

    def refresh_alarms(self) -> None:
        table = self.query_one("#alarm-table", DataTable)
        keep = table.cursor_row
        table.clear()
        now = local_now()
        for a in self.session.engine.alarms:
            on = Text("● on", style="bold green") if a.enabled or a.snoozed_until else Text("○ off", style="dim")
            table.add_row(on, Text(a.time_text(self.session.settings.clock_24h), style="bold"), a.label or "—",
                          a.repeat_text(), f"{a.snooze_minutes} min", self._next_text(a, now), key=a.id)
        empty = not self.session.engine.alarms
        table.display = not empty
        self.query_one("#alarms-empty").display = empty
        if not empty:
            table.move_cursor(row=min(keep, table.row_count - 1))

    def _next_text(self, a: Alarm, now: datetime) -> str:
        due = due_time(a, now)
        return (humanize_until(due, now) + (" (snoozed)" if a.snoozed_until else "")) if due else "—"

    def _paint_next_column(self, now: datetime) -> None:
        """Keep the countdown column live without rebuilding the table (which would reset scroll)."""
        table = self.query_one("#alarm-table", DataTable)
        rows = {str(k.value) for k in table.rows}
        for a in self.session.engine.alarms:
            if a.id in rows:
                table.update_cell(a.id, "next", self._next_text(a, now))

    def _paint_timer(self, mono: float) -> None:
        c = self.countdown
        remaining = c.remaining(mono)
        self.query_one("#timer-digits", BigDigits).value = format_span(remaining + (0.999 if remaining else 0))
        self.query_one("#timer-bar", ProgressBar).update(progress=c.progress(mono))
        state = "running" if c.running else ("done" if c.finished(mono) else "paused" if c.started else "ready")
        self.query_one("#timer-status", Label).update(f"{format_span(c.duration)} timer · {state}")
        self.query_one("#t-start", Button).label = "Pause  \\[space]" if c.running else (
            "Resume  \\[space]" if c.started and not c.finished(mono) else "Start  \\[space]")

    def _paint_stopwatch(self, mono: float) -> None:
        self.query_one("#sw-digits", BigDigits).value = format_span(self.stopwatch.elapsed(mono), hundredths=True)

    # ---- ringing -------------------------------------------------------
    def _drain_ring_queue(self) -> None:
        if self._ringing or not self._ring_queue:
            return
        kind, alarm = self._ring_queue.pop(0)
        self._ringing = True
        s = self.session
        if kind == "alarm":
            screen = RingScreen(alarm.label or "Alarm", f"{alarm.time_text(s.settings.clock_24h)} · {alarm.repeat_text()}",
                                snooze_minutes=alarm.snooze_minutes, clock_24h=s.settings.clock_24h)
            self.push_screen(screen, lambda choice: self._after_alarm(alarm, choice))
        else:
            label = self.countdown.label or f"{format_span(self.countdown.duration)} timer"
            screen = RingScreen(label, "Time's up", snooze_minutes=None, clock_24h=s.settings.clock_24h)
            self.push_screen(screen, lambda choice: self._after_timer())

    def _after_alarm(self, alarm: Alarm, choice: str | None) -> None:
        s = self.session
        if choice == "snooze":
            snoozed = s.engine.snooze(alarm.id, local_now())
            self.notify(f"Snoozed {alarm.label or 'alarm'} until {self._fmt(snoozed.snoozed_until)}", timeout=5)
        else:
            s.engine.dismiss(alarm.id)
        self.save()
        self.refresh_alarms()
        self._ringing = False
        self.call_later(self._drain_ring_queue)

    def _after_timer(self) -> None:
        self.countdown.reset()
        self._timer_rang = False
        self._paint_timer(time.monotonic())
        self._ringing = False
        self.call_later(self._drain_ring_queue)

    # ---- actions -------------------------------------------------------
    @property
    def active_tab(self) -> str:
        return self.query_one("#tabs", TabbedContent).active

    def action_tab(self, tab: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab
        if tab == "alarms":
            self.query_one("#alarm-table").focus()

    def action_primary(self) -> None:
        {"alarms": self.action_toggle_alarm, "timer": self.action_timer_toggle,
         "stopwatch": self.action_sw_toggle}.get(self.active_tab, lambda: None)()

    def action_reset(self) -> None:
        if self.active_tab == "timer":
            self.countdown.reset()
            self._timer_rang = False
            self._paint_timer(time.monotonic())
        elif self.active_tab == "stopwatch":
            self.stopwatch.reset()
            self.query_one("#lap-table", DataTable).clear()
            self._paint_stopwatch(time.monotonic())
            self.query_one("#sw-start", Button).label = "Start  \\[space]"

    def action_toggle_24h(self) -> None:
        s = self.session
        s.settings.clock_24h = not s.settings.clock_24h
        self.save()
        self.refresh_alarms()
        self._paint_clock(local_now())

    def watch_theme(self, theme: str) -> None:
        if self.session.settings.theme != theme:
            self.session.settings.theme = theme
            self.save()

    # alarms
    def _selected(self) -> Alarm | None:
        table = self.query_one("#alarm-table", DataTable)
        if not self.session.engine.alarms or table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return self.session.engine.get(key)

    def action_new_alarm(self) -> None:
        self.action_tab("alarms")
        self.push_screen(AlarmForm(clock_24h=self.session.settings.clock_24h), self._saved_alarm)

    def action_edit_alarm(self) -> None:
        if self.active_tab == "alarms" and (alarm := self._selected()):
            self.push_screen(AlarmForm(alarm, clock_24h=self.session.settings.clock_24h), self._saved_alarm)

    def _saved_alarm(self, alarm: Alarm | None) -> None:
        if alarm is None:
            return
        engine = self.session.engine
        is_new = alarm.id not in {a.id for a in engine.alarms}
        (engine.add if is_new else engine.update)(alarm)
        self.save()
        self.refresh_alarms()
        due = due_time(alarm, local_now())
        self.notify(f"{'Added' if is_new else 'Updated'} {alarm.label or 'alarm'} · rings {humanize_until(due, local_now())}",
                    timeout=4)
        table = self.query_one("#alarm-table", DataTable)
        table.move_cursor(row=table.get_row_index(alarm.id))

    def action_toggle_alarm(self) -> None:
        if alarm := self._selected():
            on = not (alarm.enabled or alarm.snoozed_until)
            self.session.engine.set_enabled(alarm.id, on, local_now())
            self.save()
            self.refresh_alarms()

    def action_delete_alarm(self) -> None:
        if self.active_tab == "alarms" and (alarm := self._selected()):
            self._deleted = self.session.engine.remove(alarm.id)
            self.save()
            self.refresh_alarms()
            self.notify(f"Deleted {alarm.label or 'alarm'}. Press u to undo.", timeout=6)

    def action_undo_delete(self) -> None:
        if self._deleted:
            self.session.engine.add(self._deleted)
            self.notify(f"Restored {self._deleted.label or 'alarm'}.", timeout=4)
            self._deleted = None
            self.save()
            self.refresh_alarms()

    @on(DataTable.RowSelected, "#alarm-table")
    def _row_chosen(self) -> None:
        self.action_edit_alarm()

    # timer
    def load_countdown(self, text: str) -> bool:
        try:
            seconds = parse_duration(text).total_seconds()
        except ParseError as exc:
            self.notify(str(exc), severity="error", timeout=5)
            return False
        self.countdown = Countdown(seconds)
        self._timer_rang = False
        self._paint_timer(time.monotonic())
        return True

    def action_timer_toggle(self) -> None:
        mono = time.monotonic()
        if self.countdown.finished(mono):
            self.countdown.reset()
        self.countdown.toggle(mono)
        self._paint_timer(mono)

    def action_add_minute(self) -> None:
        if self.active_tab == "timer":
            self.countdown.add(60)
            self._timer_rang = False
            self._paint_timer(time.monotonic())

    # stopwatch
    def action_sw_toggle(self) -> None:
        mono = time.monotonic()
        self.stopwatch.toggle(mono)
        self.query_one("#sw-start", Button).label = "Stop  \\[space]" if self.stopwatch.running else "Start  \\[space]"
        self._paint_stopwatch(mono)

    def action_lap(self) -> None:
        if self.active_tab != "stopwatch" or not (lap := self.stopwatch.lap(time.monotonic())):
            return
        table = self.query_one("#lap-table", DataTable)
        table.clear()
        marks = self.stopwatch.best_and_worst()
        for l in reversed(self.stopwatch.laps):
            tag = Text("")
            if marks and l.number == marks[0]:
                tag = Text("fastest", style="bold green")
            elif marks and l.number == marks[1]:
                tag = Text("slowest", style="bold red")
            table.add_row(f"#{l.number}", format_span(l.split, hundredths=True), format_span(l.total, hundredths=True), tag)

    # ---- buttons -------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        actions = {
            "a-new": self.action_new_alarm, "a-edit": self.action_edit_alarm,
            "a-toggle": self.action_toggle_alarm, "a-delete": self.action_delete_alarm,
            "t-start": self.action_timer_toggle, "t-plus": self.action_add_minute, "t-reset": self.action_reset,
            "sw-start": self.action_sw_toggle, "sw-lap": self.action_lap, "sw-reset": self.action_reset,
        }
        if bid in actions:
            actions[bid]()
        elif bid.startswith("t-") and bid[2:] in TIMER_PRESETS:
            if self.load_countdown(bid[2:]):
                self.action_timer_toggle()

    @on(Input.Submitted, "#t-custom")
    def _custom_timer(self, event: Input.Submitted) -> None:
        if self.load_countdown(event.value):
            event.input.value = ""
            self.action_timer_toggle()
            self.query_one("#t-start").focus()

    def on_unmount(self) -> None:
        self.session.save()
