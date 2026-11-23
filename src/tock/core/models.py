"""Plain data. No I/O, no clocks: whoever creates an alarm passes `now` in."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field, replace
from datetime import datetime

# Monday = 0 ... Sunday = 6, the same as datetime.weekday().
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEKDAYS = frozenset(range(5))
WEEKENDS = frozenset({5, 6})
EVERY_DAY = frozenset(range(7))

DEFAULT_SNOOZE_MINUTES = 9  # the iOS default


def new_id() -> str:
    return secrets.token_hex(3)


@dataclass(frozen=True)
class Alarm:
    hour: int
    minute: int
    armed_at: datetime  # when it was created, edited or switched on; nothing before this counts as missed
    second: int = 0
    label: str = ""
    days: frozenset[int] = frozenset()  # empty means "once"
    enabled: bool = True
    snooze_minutes: int = DEFAULT_SNOOZE_MINUTES
    snoozed_until: datetime | None = None
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        if not (0 <= self.hour <= 23 and 0 <= self.minute <= 59 and 0 <= self.second <= 59):
            raise ValueError(f"invalid time {self.hour}:{self.minute}:{self.second}")
        if not self.days <= EVERY_DAY:
            raise ValueError(f"invalid days {sorted(self.days)}")
        if not 1 <= self.snooze_minutes <= 60:
            raise ValueError("snooze must be 1 to 60 minutes")
        if self.armed_at.tzinfo is None:
            raise ValueError("armed_at must be timezone-aware")

    @property
    def repeats(self) -> bool:
        return bool(self.days)

    def time_text(self, clock_24h: bool = True) -> str:
        return format_time(self.hour, self.minute, self.second, clock_24h)

    def repeat_text(self) -> str:
        return describe_days(self.days)

    def updated(self, now: datetime, **changes) -> Alarm:
        """Return an edited copy. Edits re-arm the alarm so old fire times are not reported as missed."""
        return replace(self, armed_at=now, **changes)


def format_time(hour: int, minute: int, second: int = 0, clock_24h: bool = True) -> str:
    sec = f":{second:02d}" if second else ""
    if clock_24h:
        return f"{hour:02d}:{minute:02d}{sec}"
    suffix = "am" if hour < 12 else "pm"
    return f"{(hour % 12) or 12}:{minute:02d}{sec} {suffix}"


def describe_days(days: frozenset[int]) -> str:
    if not days:
        return "Once"
    if days == EVERY_DAY:
        return "Every day"
    if days == WEEKDAYS:
        return "Weekdays"
    if days == WEEKENDS:
        return "Weekends"
    return " ".join(DAY_NAMES[d] for d in sorted(days))
