from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tock.core.models import WEEKDAYS, Alarm
from tock.core.schedule import due_time, humanize_until, next_fire

IST = ZoneInfo("Asia/Kolkata")
NY = ZoneInfo("America/New_York")  # 2026: clocks spring forward Mar 8, fall back Nov 1


def at(*args, tz=IST, fold=0):
    return datetime(*args, tzinfo=tz, fold=fold)


def alarm(h, m, s=0, days=frozenset(), armed=None, **kw):
    return Alarm(hour=h, minute=m, second=s, days=frozenset(days), armed_at=armed or at(2026, 1, 1), **kw)


# Monday 23 Nov 2026
MON_9AM = at(2026, 11, 23, 9, 0)


def test_later_today():
    assert next_fire(alarm(18, 30), MON_9AM) == at(2026, 11, 23, 18, 30)


def test_already_passed_today_rolls_to_tomorrow():
    assert next_fire(alarm(7, 30), MON_9AM) == at(2026, 11, 24, 7, 30)


def test_exactly_now_is_not_next():
    # "strictly after": an alarm that just rang must not be its own next fire
    assert next_fire(alarm(9, 0), MON_9AM) == at(2026, 11, 24, 9, 0)


def test_weekdays_skip_the_weekend():
    friday_evening = at(2026, 11, 27, 20, 0)
    assert next_fire(alarm(7, 0, days=WEEKDAYS), friday_evening) == at(2026, 11, 30, 7, 0)  # Monday


def test_single_weekday_wraps_a_whole_week():
    # Monday 9:00, alarm on Mondays at 8:00 -> next Monday
    assert next_fire(alarm(8, 0, days={0}), MON_9AM) == at(2026, 11, 30, 8, 0)


def test_disabled_never_fires():
    assert next_fire(alarm(18, 30, enabled=False), MON_9AM) is None


def test_seconds_are_respected():
    assert next_fire(alarm(9, 0, 10), MON_9AM) == at(2026, 11, 23, 9, 0, 10)


def test_naive_time_is_rejected():
    with pytest.raises(ValueError):
        next_fire(alarm(7, 0), datetime(2026, 11, 23, 9, 0))


# ---- daylight saving ------------------------------------------------------

def test_spring_forward_gap_fires_at_first_real_minute():
    # 8 Mar 2026 in New York: 02:00 jumps to 03:00, so 02:30 never happens
    got = next_fire(alarm(2, 30), at(2026, 3, 8, 0, 0, tz=NY))
    assert got.replace(tzinfo=None) == datetime(2026, 3, 8, 3, 0)
    assert got.astimezone(UTC) == datetime(2026, 3, 8, 7, 0, tzinfo=UTC)


def test_fall_back_repeat_fires_once():
    # 1 Nov 2026 in New York: 01:00-02:00 happens twice
    first = next_fire(alarm(1, 30), at(2026, 11, 1, 0, 0, tz=NY))
    assert first.astimezone(UTC) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)  # 01:30 EDT
    # Right after it rings, the second 01:30 (EST, one hour later) must not count
    after_ring = first + timedelta(seconds=1)
    second = next_fire(alarm(1, 30), after_ring)
    assert second.astimezone(UTC) == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)  # next day, 01:30 EST


def test_wall_time_stays_put_across_dst():
    # A daily 07:00 alarm is still 07:00 local after the clocks change
    before = next_fire(alarm(7, 0), at(2026, 10, 31, 0, 0, tz=NY))  # Sat 07:00 EDT
    after = next_fire(alarm(7, 0), at(2026, 10, 31, 8, 0, tz=NY))  # Sun 07:00 EST
    assert (before.hour, after.hour) == (7, 7)
    assert after.astimezone(UTC) - before.astimezone(UTC) == timedelta(hours=25)


# ---- due_time -------------------------------------------------------------

def test_snooze_wins_over_schedule():
    snoozed = alarm(7, 0, snoozed_until=at(2026, 11, 23, 9, 9))
    assert due_time(snoozed, MON_9AM) == at(2026, 11, 23, 9, 9)


def test_due_time_ignores_times_before_the_alarm_was_armed():
    # Made at 8:00 for 7:30 -> tomorrow, even if we look back from last night
    made = alarm(7, 30, armed=at(2026, 11, 23, 8, 0))
    assert due_time(made, at(2026, 11, 22, 23, 0)) == at(2026, 11, 24, 7, 30)


def test_humanize():
    assert humanize_until(at(2026, 11, 23, 18, 12), MON_9AM) == "in 9h 12m"
    assert humanize_until(at(2026, 11, 23, 9, 0, 45), MON_9AM) == "in 45s"
    assert humanize_until(at(2026, 11, 23, 9, 3, 5), MON_9AM) == "in 3m 05s"
    assert humanize_until(MON_9AM, MON_9AM) == "now"
