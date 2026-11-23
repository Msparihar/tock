"""Pop-up screens: the ringing alert and the add/edit alarm form."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from ..alert import Ringer, notify
from ..core.models import DAY_NAMES, DEFAULT_SNOOZE_MINUTES, EVERY_DAY, WEEKDAYS, WEEKENDS, Alarm, describe_days
from ..core.parse import ParseError, parse_when
from ..core.schedule import due_time, humanize_until
from ..session import local_now
from .widgets import BigDigits


class RingScreen(ModalScreen[str]):
    """Full-screen alert. Returns "snooze", "dismiss", or for timers "again"."""

    BINDINGS = [
        Binding("s", "choose('snooze')", "Snooze", show=True),
        Binding("d,enter,escape", "choose('dismiss')", "Dismiss", show=True),
    ]

    def __init__(self, title: str, subtitle: str, *, snooze_minutes: int | None, clock_24h: bool):
        super().__init__()
        self.title_text = title
        self.subtitle = subtitle
        self.snooze_minutes = snooze_minutes
        self.clock_24h = clock_24h
        self.ringer = Ringer()

    def compose(self) -> ComposeResult:
        with Vertical(id="ring-box"):
            yield Label("⏰  RINGING", id="ring-kicker")
            yield Center(BigDigits(self._clock(), id="ring-clock"))
            yield Label(self.title_text, id="ring-title")
            yield Label(self.subtitle, id="ring-subtitle")
            with Horizontal(id="ring-buttons"):
                if self.snooze_minutes:
                    yield Button(f"Snooze {self.snooze_minutes} min  \\[s]", id="snooze", variant="warning")
                yield Button("Dismiss  \\[d]", id="dismiss", variant="primary")

    def _clock(self) -> str:
        now = local_now()
        return f"{now:%H:%M}" if self.clock_24h else f"{(now.hour % 12) or 12}:{now:%M}"

    def on_mount(self) -> None:
        self.ringer.start()
        notify("tock", f"{self.title_text} · {self.subtitle}")
        self.set_interval(0.5, self._flash)
        self.query_one("#dismiss", Button).focus()

    def _flash(self) -> None:
        self.query_one("#ring-box").toggle_class("-flash")
        self.query_one("#ring-clock", BigDigits).value = self._clock()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_choose(event.button.id or "dismiss")

    def action_choose(self, choice: str) -> None:
        if choice == "snooze" and not self.snooze_minutes:
            return
        self.ringer.stop()
        self.dismiss(choice)

    def on_unmount(self) -> None:
        self.ringer.stop()


SNOOZE_CHOICES = [(f"{m} min", m) for m in (1, 5, 9, 10, 15, 20, 30)]
PRESETS = [("Once", frozenset()), ("Weekdays", WEEKDAYS), ("Weekends", WEEKENDS), ("Every day", EVERY_DAY)]


class AlarmForm(ModalScreen[Alarm | None]):
    """Add or edit an alarm. Shows a live preview of when it will ring."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, alarm: Alarm | None = None, *, clock_24h: bool = True):
        super().__init__()
        self.original = alarm
        self.clock_24h = clock_24h
        self.days: set[int] = set(alarm.days) if alarm else set()

    def compose(self) -> ComposeResult:
        a = self.original
        with Vertical(id="form-box"):
            yield Label("Edit alarm" if a else "New alarm", id="form-title")
            yield Label("Time", classes="field-label")
            yield Input(a.time_text(self.clock_24h) if a else "", placeholder="7:30am, 19:30, or in 10m", id="f-time")
            yield Label("Label", classes="field-label")
            yield Input(a.label if a else "", placeholder="Standup, Gym, Tea…", id="f-label", max_length=40)
            yield Label("Repeat", classes="field-label")
            with Horizontal(id="f-presets"):
                for name, _ in PRESETS:
                    yield Button(name, id=f"preset-{name.replace(' ', '-').lower()}", classes="preset", compact=True)
            with Grid(id="f-days"):
                for i, name in enumerate(DAY_NAMES):
                    yield Button(name, id=f"day-{i}", classes="day", compact=True)
            yield Label("Snooze", classes="field-label")
            yield Select(SNOOZE_CHOICES, value=a.snooze_minutes if a else DEFAULT_SNOOZE_MINUTES,
                         allow_blank=False, id="f-snooze")
            yield Static("", id="f-preview")
            with Horizontal(id="form-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Save  \\[ctrl+s]", id="save", variant="primary")

    def on_mount(self) -> None:
        self._paint_days()
        self._preview()
        self.query_one("#f-time", Input).focus()

    # ---- repeat days ---------------------------------------------------
    def _paint_days(self) -> None:
        for i in range(7):
            self.query_one(f"#day-{i}", Button).set_class(i in self.days, "-on")
        for name, days in PRESETS:
            self.query_one(f"#preset-{name.replace(' ', '-').lower()}", Button).set_class(set(days) == self.days, "-on")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("day-"):
            self.days ^= {int(bid[4:])}
        elif bid.startswith("preset-"):
            self.days = set(dict((n.replace(" ", "-").lower(), d) for n, d in PRESETS)[bid[7:]])
        elif bid == "save":
            self.action_save()
            return
        elif bid == "cancel":
            self.action_cancel()
            return
        self._paint_days()
        self._preview()

    # ---- validation and preview -----------------------------------------
    def on_input_changed(self, event: Input.Changed) -> None:
        self._preview()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_save()

    def on_select_changed(self, event: Select.Changed) -> None:
        self._preview()

    def _build(self, now: datetime) -> Alarm:
        h, m, s = parse_when(self.query_one("#f-time", Input).value, now)
        fields = dict(hour=h, minute=m, second=s, label=self.query_one("#f-label", Input).value.strip(),
                      days=frozenset(self.days), snooze_minutes=int(self.query_one("#f-snooze", Select).value),
                      enabled=True, snoozed_until=None)
        if self.original:
            return self.original.updated(now, **fields)
        return Alarm(armed_at=now, **fields)

    def _preview(self) -> bool:
        preview = self.query_one("#f-preview", Static)
        if not self.query_one("#f-time", Input).value.strip():
            preview.update("[dim]Type a time to see when it rings.[/]")
            preview.set_class(False, "-error")
            return False
        now = local_now()
        try:
            alarm = self._build(now)
        except (ParseError, ValueError) as exc:
            preview.update(f"✗ {exc}")
            preview.set_class(True, "-error")
            return False
        due = due_time(alarm, now)
        preview.update(f"✓ Rings {due:%a} {alarm.time_text(self.clock_24h)} · {humanize_until(due, now)}"
                       f" · {describe_days(alarm.days)}")
        preview.set_class(False, "-error")
        return True

    def action_save(self) -> None:
        if self._preview():
            self.dismiss(self._build(local_now()))
        else:
            self.query_one("#f-time", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)
