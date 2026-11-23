"""The alarm engine: given the alarms and the time now, which alarms ring?

The engine never reads the clock. The UI calls `check(now)` about once a second
and tests call it with any time they like. It checks "is the due time at or
before now", never "is it exactly now", so a laptop that sleeps through 07:30
still notices the alarm when it wakes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from .models import Alarm
from .schedule import due_time

# An alarm that comes due while tock is running rings if we notice it within
# this window. Later than that (the laptop was asleep, or tock was closed) it
# is reported as missed instead of ringing hours late.
RING_GRACE = timedelta(minutes=5)


@dataclass
class CheckResult:
    ringing: list[Alarm] = field(default_factory=list)
    missed: list[tuple[Alarm, datetime]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.ringing or self.missed)


def _utc(d: datetime) -> datetime:
    return d.astimezone(UTC)


class AlarmEngine:
    def __init__(self, alarms: list[Alarm], last_check: datetime):
        self._alarms: dict[str, Alarm] = {a.id: a for a in alarms}
        self.last_check = last_check

    # ---- reading -------------------------------------------------------
    @property
    def alarms(self) -> list[Alarm]:
        return sorted(self._alarms.values(), key=lambda a: (a.hour, a.minute, a.second, a.label))

    def get(self, alarm_id: str) -> Alarm:
        try:
            return self._alarms[alarm_id]
        except KeyError:
            raise KeyError(f"no alarm with id {alarm_id!r}") from None

    def find(self, prefix: str) -> Alarm:
        """Look an alarm up by id prefix, as the CLI does (`tock rm 3f`)."""
        matches = [a for a in self._alarms.values() if a.id.startswith(prefix)]
        if len(matches) != 1:
            raise KeyError(f"{'no' if not matches else 'more than one'} alarm matches {prefix!r}")
        return matches[0]

    def upcoming(self, now: datetime) -> list[tuple[Alarm, datetime]]:
        """Every alarm that will ring, soonest first."""
        out = []
        for alarm in self._alarms.values():
            due = due_time(alarm, now)
            if due is not None:
                out.append((alarm, due))
        return sorted(out, key=lambda pair: _utc(pair[1]))

    def next_up(self, now: datetime) -> tuple[Alarm, datetime] | None:
        upcoming = self.upcoming(now)
        return upcoming[0] if upcoming else None

    # ---- the clock tick ------------------------------------------------
    def check(self, now: datetime) -> CheckResult:
        result = CheckResult()
        for alarm in list(self._alarms.values()):
            due = due_time(alarm, self.last_check)
            if due is None or _utc(due) > _utc(now):
                continue
            if _utc(now) - _utc(due) <= RING_GRACE:
                result.ringing.append(alarm)
            else:
                result.missed.append((alarm, due))
            self._alarms[alarm.id] = self._after_fire(alarm)
        self.last_check = now
        return result

    @staticmethod
    def _after_fire(alarm: Alarm) -> Alarm:
        # A one-time alarm switches itself off once it rings; a snooze is used up.
        return replace(alarm, snoozed_until=None, enabled=alarm.enabled and alarm.repeats)

    # ---- actions -------------------------------------------------------
    def add(self, alarm: Alarm) -> Alarm:
        self._alarms[alarm.id] = alarm
        return alarm

    def update(self, alarm: Alarm) -> Alarm:
        self.get(alarm.id)
        self._alarms[alarm.id] = alarm
        return alarm

    def remove(self, alarm_id: str) -> Alarm:
        return self._alarms.pop(self.get(alarm_id).id)

    def set_enabled(self, alarm_id: str, enabled: bool, now: datetime) -> Alarm:
        alarm = self.get(alarm_id).updated(now, enabled=enabled, snoozed_until=None)
        self._alarms[alarm_id] = alarm
        return alarm

    def snooze(self, alarm_id: str, now: datetime) -> Alarm:
        alarm = self.get(alarm_id)
        alarm = replace(alarm, snoozed_until=now + timedelta(minutes=alarm.snooze_minutes))
        self._alarms[alarm_id] = alarm
        return alarm

    def dismiss(self, alarm_id: str) -> Alarm:
        alarm = replace(self.get(alarm_id), snoozed_until=None)
        self._alarms[alarm_id] = alarm
        return alarm
