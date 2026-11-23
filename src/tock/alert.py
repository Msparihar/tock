"""Make noise and post a desktop notification, using tools the OS already has.

macOS: `afplay` with a system sound, `osascript` for the notification.
Linux: `paplay`/`aplay` and `notify-send` when present.
Anywhere else: the terminal bell. Nothing here ever raises; an alarm that
can't play a sound must still show on screen.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

MAC_SOUNDS = Path("/System/Library/Sounds")
LINUX_SOUND = Path("/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga")


def muted() -> bool:
    return bool(os.environ.get("TOCK_MUTE"))


def _sound_command(sound: str) -> list[str] | None:
    if sys.platform == "darwin" and shutil.which("afplay"):
        path = MAC_SOUNDS / f"{sound}.aiff"
        return ["afplay", str(path if path.exists() else MAC_SOUNDS / "Glass.aiff")]
    for player in ("paplay", "aplay"):
        if shutil.which(player) and LINUX_SOUND.exists():
            return [player, str(LINUX_SOUND)]
    return None


def notify(title: str, body: str) -> None:
    if muted():
        return
    try:
        if sys.platform == "darwin" and shutil.which("osascript"):
            script = f"display notification {_applescript_str(body)} with title {_applescript_str(title)}"
            subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "-u", "critical", title, body],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def _applescript_str(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Ringer:
    """Plays a sound on a loop until stopped. One per ringing alarm or timer."""

    def __init__(self, sound: str = "Glass", gap: float = 0.6):
        self._cmd = _sound_command(sound)
        self._gap = gap
        self._stop = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if muted() or self._thread:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._cmd is None:
                sys.__stdout__.write("\a")
                sys.__stdout__.flush()
            else:
                try:
                    self._proc = subprocess.Popen(self._cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self._proc.wait()
                except OSError:
                    self._cmd = None
            self._stop.wait(self._gap)

    def stop(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
