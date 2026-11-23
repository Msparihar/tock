"""Glue between the store and the engine, shared by the CLI and the TUI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .core.engine import AlarmEngine
from .store import Settings, State, Store


def local_now() -> datetime:
    return datetime.now().astimezone()


class Session:
    def __init__(self, path: Path | None = None):
        self.store = Store(path)
        self.reload()

    def reload(self) -> None:
        state = self.store.load()
        self.loaded: State = state
        self.settings: Settings = state.settings
        # First run: nothing before now can count as missed.
        last_check = state.last_check or local_now()
        # Reloading after `tock add` in another terminal: that file carries our own last_check
        # from the last save, which may be older than what we have checked since. Never go
        # backwards, or an alarm that just rang would ring again.
        if hasattr(self, "engine") and self.engine.last_check > last_check:
            last_check = self.engine.last_check
        self.engine = AlarmEngine(state.alarms, last_check=last_check)
        self._mtime = self.store.mtime()

    def save(self) -> None:
        self.store.save(State(alarms=self.engine.alarms, last_check=self.engine.last_check, settings=self.settings))
        self._mtime = self.store.mtime()

    def changed_on_disk(self) -> bool:
        """True when another tock (say `tock add` in a second terminal) wrote the file."""
        return self.store.mtime() != self._mtime
