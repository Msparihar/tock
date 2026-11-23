"""When does an alarm fire next? Everything else in tock trusts this one function.

Rules:
- Alarms keep local wall time ("07:30 on weekdays"), not a fixed instant, so they
  stay at 07:30 when daylight saving starts or ends.
- A wall time that doesn't exist that day (clocks jump 02:00 -> 03:00) fires at
  the first real minute after it.
- A wall time that happens twice (clocks fall back 02:00 -> 01:00) fires once,
  at its first occurrence.
- All comparisons happen in UTC. Python compares two datetimes that share a
  tzinfo by wall time and ignores `fold`, which is wrong around a fall-back.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta, tzinfo

from .models import Alarm

MAX_LOOKAHEAD_DAYS = 8  # a weekly alarm always fires within 7 days; 8 covers DST edge days


def next_fire(alarm: Alarm, after: datetime) -> datetime | None:
    """The first time strictly after `after` that this alarm should ring, ignoring snooze.

    Returns an aware datetime in `after`'s time zone, or None for a disabled alarm.
    """
    if not alarm.enabled:
        return None
    if after.tzinfo is None:
        raise ValueError("`after` must be timezone-aware")
    tz = after.tzinfo
    after_utc = after.astimezone(UTC)
    wall = time(alarm.hour, alarm.minute, alarm.second)
    start = after.date()
    for offset in range(MAX_LOOKAHEAD_DAYS):
        day = start + timedelta(days=offset)
        if alarm.days and day.weekday() not in alarm.days:
            continue
        candidate = resolve_wall_time(datetime.combine(day, wall), tz)
        if candidate.astimezone(UTC) > after_utc:
            return candidate
    return None  # unreachable for valid alarms; kept so the type is honest


def resolve_wall_time(naive: datetime, tz: tzinfo) -> datetime:
    """Attach `tz` to a wall time, applying the DST rules above."""
    local = naive.replace(tzinfo=tz, fold=0)  # fold=0 picks the first of two repeated times
    if exists(local):
        return local
    probe = naive.replace(second=0)
    for _ in range(24 * 60):  # gaps are an hour at most in practice; a day is a safe bound
        probe += timedelta(minutes=1)
        candidate = probe.replace(tzinfo=tz, fold=0)
        if exists(candidate):
            return candidate
    raise ValueError(f"no valid local time after {naive} in {tz}")


def exists(local: datetime) -> bool:
    """False for a wall time inside a spring-forward gap."""
    round_trip = local.astimezone(UTC).astimezone(local.tzinfo)
    return round_trip.replace(tzinfo=None) == local.replace(tzinfo=None)


def due_time(alarm: Alarm, since: datetime) -> datetime | None:
    """The time this alarm is waiting for: its snooze if snoozed, else its next fire after `since`."""
    if alarm.snoozed_until is not None:
        return alarm.snoozed_until
    anchor = max(since, alarm.armed_at, key=lambda d: d.astimezone(UTC))
    return next_fire(alarm, anchor.astimezone(since.tzinfo))


def humanize_until(target: datetime, now: datetime) -> str:
    """'in 9h 12m', 'in 45s'."""
    secs = int((target.astimezone(UTC) - now.astimezone(UTC)).total_seconds())
    if secs <= 0:
        return "now"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        return f"in {days}d {hours}h"
    if hours:
        return f"in {hours}h {minutes}m"
    if minutes:
        return f"in {minutes}m {seconds:02d}s" if minutes < 10 else f"in {minutes}m"
    return f"in {seconds}s"
