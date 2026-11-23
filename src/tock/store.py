"""Save and load tock's state as one JSON file. No database.

- Writes go to a temp file in the same folder, then `os.replace` swaps it in.
  A crash mid-write leaves the old file whole, never a half-written one.
- The file carries a version number, so a later tock can migrate it.
- A file that won't parse is moved aside, not deleted, and the user is told where.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .core.models import Alarm

VERSION = 1


class StoreError(Exception):
    pass


@dataclass
class Settings:
    clock_24h: bool = True
    show_seconds: bool = True
    theme: str = "tokyo-night"


@dataclass
class State:
    alarms: list[Alarm] = field(default_factory=list)
    last_check: datetime | None = None
    settings: Settings = field(default_factory=Settings)
    recovered_from: Path | None = None  # set when a corrupt file was moved aside on load
    recovery_reason: str = ""


def default_path() -> Path:
    if home := os.environ.get("TOCK_HOME"):
        return Path(home).expanduser() / "state.json"
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "tock" / "state.json"


# ---- (de)serialising --------------------------------------------------

def alarm_to_dict(a: Alarm) -> dict:
    return {
        "id": a.id,
        "time": f"{a.hour:02d}:{a.minute:02d}:{a.second:02d}",
        "label": a.label,
        "days": sorted(a.days),
        "enabled": a.enabled,
        "snooze_minutes": a.snooze_minutes,
        "snoozed_until": a.snoozed_until.isoformat() if a.snoozed_until else None,
        "armed_at": a.armed_at.isoformat(),
    }


def alarm_from_dict(d: dict) -> Alarm:
    h, m, s = (int(x) for x in d["time"].split(":"))
    return Alarm(
        id=d["id"], hour=h, minute=m, second=s,
        label=d.get("label", ""),
        days=frozenset(d.get("days", [])),
        enabled=d.get("enabled", True),
        snooze_minutes=d.get("snooze_minutes", 9),
        snoozed_until=datetime.fromisoformat(d["snoozed_until"]) if d.get("snoozed_until") else None,
        armed_at=datetime.fromisoformat(d["armed_at"]),
    )


def to_json(state: State) -> str:
    return json.dumps({
        "version": VERSION,
        "last_check": state.last_check.isoformat() if state.last_check else None,
        "settings": vars(state.settings),
        "alarms": [alarm_to_dict(a) for a in state.alarms],
    }, indent=2)


def from_json(text: str) -> State:
    data = json.loads(text)
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise StoreError(f"unknown file version {data.get('version') if isinstance(data, dict) else None!r}")
    known = set(vars(Settings()))
    return State(
        alarms=[alarm_from_dict(a) for a in data.get("alarms", [])],
        last_check=datetime.fromisoformat(data["last_check"]) if data.get("last_check") else None,
        settings=Settings(**{k: v for k, v in data.get("settings", {}).items() if k in known}),
    )


# ---- files ------------------------------------------------------------

class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_path()

    def load(self) -> State:
        if not self.path.exists():
            return State()
        text = self.path.read_text()
        try:
            return from_json(text)
        except (ValueError, KeyError, TypeError, StoreError) as exc:
            aside = self.path.with_suffix(f".corrupt-{datetime.now():%Y%m%d-%H%M%S}.json")
            self.path.replace(aside)
            return State(recovered_from=aside, recovery_reason=str(exc))

    def save(self, state: State) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(to_json(state))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def mtime(self) -> float | None:
        try:
            return self.path.stat().st_mtime
        except FileNotFoundError:
            return None
