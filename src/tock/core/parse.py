"""Turn what people type into values: '7:30pm', 'in 20m', '1h30m', 'weekdays'.

Small on purpose. I need four shapes, not a natural-language engine.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .models import DAY_NAMES, EVERY_DAY, WEEKDAYS, WEEKENDS


class ParseError(ValueError):
    pass


_CLOCK = re.compile(r"^(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(am|pm|a|p)?$")
# Longest unit names first: regex alternation takes the first that matches, so "h" would eat "hours".
_DURATION_PART = re.compile(r"(\d+)\s*(hours|hour|hrs|hr|h|minutes|minute|mins|min|m|seconds|second|secs|sec|s)")
_UNIT_SECONDS = {"h": 3600, "m": 60, "s": 1}


def parse_clock(text: str) -> tuple[int, int, int]:
    """'7:30' -> (7, 30, 0); '7pm' -> (19, 0, 0); '19:30:15' -> (19, 30, 15); 'noon'."""
    t = text.strip().lower().replace(".", "")
    if t == "noon":
        return 12, 0, 0
    if t == "midnight":
        return 0, 0, 0
    m = _CLOCK.match(t)
    if not m:
        raise ParseError(f"can't read {text!r} as a time; try 7:30, 7:30pm or 19:30")
    hour, minute, second = int(m[1]), int(m[2] or 0), int(m[3] or 0)
    meridiem = m[4]
    if meridiem:
        if not 1 <= hour <= 12:
            raise ParseError(f"{text!r}: with am/pm the hour must be 1 to 12")
        hour = hour % 12 + (12 if meridiem.startswith("p") else 0)
    if hour > 23 or minute > 59 or second > 59:
        raise ParseError(f"{text!r} is not a real time")
    return hour, minute, second


def parse_duration(text: str) -> timedelta:
    """'25' (minutes), '10m', '1h30m', '90s', '1h 5m', '5:00' (m:ss), '1:05:00' (h:mm:ss)."""
    t = text.strip().lower()
    if not t:
        raise ParseError("empty duration")
    if t.isdigit():
        seconds = int(t) * 60
    elif re.fullmatch(r"\d+(:\d{2}){1,2}", t):
        parts = [int(p) for p in t.split(":")]
        if any(p > 59 for p in parts[1:]):
            raise ParseError(f"{text!r} is not a real duration")
        seconds = 0
        for p in parts:
            seconds = seconds * 60 + p
    else:
        compact = t.replace(" ", "")
        parts = _DURATION_PART.findall(compact)
        if not parts or "".join(n + u for n, u in parts) != compact:
            raise ParseError(f"can't read {text!r} as a duration; try 10m, 1h30m or 90s")
        seconds = sum(int(n) * _UNIT_SECONDS[u[0]] for n, u in parts)
    if seconds <= 0:
        raise ParseError("duration must be more than zero")
    if seconds > 24 * 3600:
        raise ParseError("duration must be 24 hours or less")
    return timedelta(seconds=seconds)


def parse_when(text: str, now: datetime) -> tuple[int, int, int]:
    """An alarm time: a clock time ('7:30am') or a delay from now ('in 20m', '+90s')."""
    t = text.strip().lower()
    for prefix in ("in ", "+"):
        if t.startswith(prefix):
            target = now + parse_duration(t[len(prefix):])
            return target.hour, target.minute, target.second
    return parse_clock(t)


_DAY_ALIASES = {
    "once": frozenset(), "never": frozenset(), "": frozenset(),
    "daily": EVERY_DAY, "everyday": EVERY_DAY, "every day": EVERY_DAY,
    "weekdays": WEEKDAYS, "weekday": WEEKDAYS,
    "weekends": WEEKENDS, "weekend": WEEKENDS,
}


def parse_days(text: str) -> frozenset[int]:
    """'weekdays', 'daily', 'once', or a list like 'mon,wed,fri' / 'mon-fri'."""
    t = text.strip().lower()
    if t in _DAY_ALIASES:
        return _DAY_ALIASES[t]
    names = [n.lower() for n in DAY_NAMES]
    days: set[int] = set()
    for chunk in re.split(r"[,\s]+", t):
        if "-" in chunk:
            lo, hi = (_day_index(p, names, text) for p in chunk.split("-", 1))
            span = range(lo, hi + 1) if lo <= hi else [*range(lo, 7), *range(0, hi + 1)]
            days.update(span)
        elif chunk:
            days.add(_day_index(chunk, names, text))
    return frozenset(days)


def _day_index(token: str, names: list[str], original: str) -> int:
    key = token[:3]
    if key not in names:
        raise ParseError(f"can't read {original!r} as days; try weekdays, daily or mon,wed,fri")
    return names.index(key)
