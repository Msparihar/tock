from datetime import datetime
from zoneinfo import ZoneInfo

from tock.core.models import WEEKDAYS, Alarm
from tock.store import Settings, State, Store

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 23, 9, 0, tzinfo=IST)


def test_round_trip(tmp_path):
    store = Store(tmp_path / "state.json")
    alarms = [
        Alarm(hour=7, minute=30, label="Standup", days=WEEKDAYS, armed_at=NOW, snooze_minutes=5),
        Alarm(hour=22, minute=0, second=15, enabled=False, armed_at=NOW, snoozed_until=NOW),
    ]
    store.save(State(alarms=alarms, last_check=NOW, settings=Settings(clock_24h=False)))
    loaded = store.load()
    assert loaded.alarms == alarms
    assert loaded.last_check == NOW
    assert loaded.settings.clock_24h is False


def test_missing_file_is_empty_state(tmp_path):
    state = Store(tmp_path / "nope" / "state.json").load()
    assert state.alarms == [] and state.last_check is None


def test_save_leaves_no_temp_files(tmp_path):
    store = Store(tmp_path / "state.json")
    for _ in range(3):
        store.save(State(alarms=[Alarm(hour=7, minute=0, armed_at=NOW)]))
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_corrupt_file_is_moved_aside_not_lost(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"version": 1, "alarms": [{"time": ')  # cut off mid-write
    state = Store(path).load()
    assert state.alarms == []
    assert state.recovered_from is not None and state.recovered_from.exists()
    assert state.recovered_from.read_text().startswith('{"version": 1')
    assert not path.exists()


def test_unknown_version_is_not_silently_misread(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"version": 99, "alarms": []}')
    state = Store(path).load()
    assert state.recovered_from is not None
    assert "version" in state.recovery_reason


def test_unknown_settings_keys_are_ignored(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"version": 1, "alarms": [], "settings": {"clock_24h": false, "from_the_future": 1}}')
    assert Store(path).load().settings.clock_24h is False
