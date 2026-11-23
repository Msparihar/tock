from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tock.core.engine import AlarmEngine
from tock.core.models import EVERY_DAY, Alarm

IST = ZoneInfo("Asia/Kolkata")


def at(*args):
    return datetime(*args, tzinfo=IST)


ARMED = at(2026, 11, 23, 0, 0)


def make(h, m, s=0, days=frozenset(), **kw):
    return Alarm(hour=h, minute=m, second=s, days=frozenset(days), armed_at=ARMED, **kw)


def run_seconds(engine, start, seconds):
    """Tick once a second, like the UI does, and collect what rang."""
    rang = []
    for i in range(1, seconds + 1):
        rang += engine.check(start + timedelta(seconds=i)).ringing
    return rang


def test_rings_once_on_time():
    a = make(7, 30)
    engine = AlarmEngine([a], last_check=at(2026, 11, 23, 7, 29, 50))
    rang = run_seconds(engine, at(2026, 11, 23, 7, 29, 50), 30)
    assert [r.id for r in rang] == [a.id]


def test_one_time_alarm_switches_off_after_ringing():
    a = make(7, 30)
    engine = AlarmEngine([a], last_check=at(2026, 11, 23, 7, 29))
    engine.check(at(2026, 11, 23, 7, 30))
    assert engine.get(a.id).enabled is False


def test_repeating_alarm_stays_on_and_rings_next_day():
    a = make(7, 30, days=EVERY_DAY)
    engine = AlarmEngine([a], last_check=at(2026, 11, 23, 7, 29))
    assert engine.check(at(2026, 11, 23, 7, 30)).ringing
    assert engine.get(a.id).enabled
    assert not engine.check(at(2026, 11, 23, 23, 0)).ringing
    assert engine.check(at(2026, 11, 24, 7, 30)).ringing


def test_a_missed_tick_still_rings():
    # The UI loop stalled for 40 s (laptop lid, busy CPU). "due <= now" still catches it.
    a = make(7, 30)
    engine = AlarmEngine([a], last_check=at(2026, 11, 23, 7, 29, 40))
    assert engine.check(at(2026, 11, 23, 7, 30, 20)).ringing


def test_hours_late_is_reported_missed_not_rung():
    a = make(7, 30, label="Standup")
    engine = AlarmEngine([a], last_check=at(2026, 11, 23, 6, 0))  # tock closed at 6:00
    result = engine.check(at(2026, 11, 23, 9, 0))  # opened at 9:00
    assert result.ringing == []
    assert [(m.label, due) for m, due in result.missed] == [("Standup", at(2026, 11, 23, 7, 30))]
    # Reported once only
    assert not engine.check(at(2026, 11, 23, 9, 0, 1)).changed


def test_snooze_rings_again_after_its_interval():
    a = make(7, 30, snooze_minutes=5)
    engine = AlarmEngine([a], last_check=at(2026, 11, 23, 7, 29))
    engine.check(at(2026, 11, 23, 7, 30))
    engine.snooze(a.id, at(2026, 11, 23, 7, 30, 3))
    assert not engine.check(at(2026, 11, 23, 7, 35, 2)).ringing
    assert engine.check(at(2026, 11, 23, 7, 35, 3)).ringing
    assert engine.get(a.id).snoozed_until is None


def test_snooze_works_for_one_time_alarm_already_switched_off():
    a = make(7, 30)
    engine = AlarmEngine([a], last_check=at(2026, 11, 23, 7, 29))
    engine.check(at(2026, 11, 23, 7, 30))
    engine.snooze(a.id, at(2026, 11, 23, 7, 30))
    assert engine.check(at(2026, 11, 23, 7, 39)).ringing


def test_switching_off_clears_snooze():
    a = make(7, 30)
    engine = AlarmEngine([a], last_check=at(2026, 11, 23, 7, 29))
    engine.check(at(2026, 11, 23, 7, 30))
    engine.snooze(a.id, at(2026, 11, 23, 7, 30))
    engine.set_enabled(a.id, False, at(2026, 11, 23, 7, 31))
    assert not engine.check(at(2026, 11, 23, 7, 45)).changed


def test_new_alarm_is_not_missed_from_before_it_existed():
    # Closed yesterday; today at 8:00 `tock add 7:30` from the CLI; open tock at 8:01.
    engine = AlarmEngine([], last_check=at(2026, 11, 22, 22, 0))
    engine.add(Alarm(hour=7, minute=30, armed_at=at(2026, 11, 23, 8, 0)))
    assert not engine.check(at(2026, 11, 23, 8, 1)).changed


def test_next_up_and_upcoming_order():
    late, early = make(22, 0, label="Bed"), make(18, 0, label="Gym")
    off = make(12, 0, enabled=False)
    engine = AlarmEngine([late, early, off], last_check=at(2026, 11, 23, 9, 0))
    now = at(2026, 11, 23, 9, 0)
    assert [a.label for a, _ in engine.upcoming(now)] == ["Gym", "Bed"]
    assert engine.next_up(now)[0].label == "Gym"


def test_find_by_prefix():
    a = make(7, 0)
    engine = AlarmEngine([a], last_check=ARMED)
    assert engine.find(a.id[:3]) == a
