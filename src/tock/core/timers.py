"""Countdown timer and stopwatch. Both take the time as an argument
(a monotonic seconds value), so tests never wait and the system clock
changing can't make them jump."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Countdown:
    duration: float  # seconds
    label: str = ""
    _started: float | None = None  # monotonic time of the last start/resume
    _banked: float = 0.0  # seconds already used before the last pause

    @property
    def running(self) -> bool:
        return self._started is not None

    @property
    def started(self) -> bool:
        return self.running or self._banked > 0

    def start(self, now: float) -> None:
        if not self.running:
            self._started = now

    def pause(self, now: float) -> None:
        if self.running:
            self._banked += now - self._started
            self._started = None

    def toggle(self, now: float) -> None:
        self.pause(now) if self.running else self.start(now)

    def reset(self) -> None:
        self._started = None
        self._banked = 0.0

    def add(self, seconds: float) -> None:
        self.duration += seconds

    def elapsed(self, now: float) -> float:
        return self._banked + (now - self._started if self.running else 0.0)

    def remaining(self, now: float) -> float:
        return max(0.0, self.duration - self.elapsed(now))

    def progress(self, now: float) -> float:
        return min(1.0, self.elapsed(now) / self.duration) if self.duration else 1.0

    def finished(self, now: float) -> bool:
        return self.started and self.remaining(now) <= 0


@dataclass
class Lap:
    number: int
    split: float  # this lap alone
    total: float  # since the start


@dataclass
class Stopwatch:
    _started: float | None = None
    _banked: float = 0.0
    laps: list[Lap] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return self._started is not None

    def elapsed(self, now: float) -> float:
        return self._banked + (now - self._started if self.running else 0.0)

    def toggle(self, now: float) -> None:
        if self.running:
            self._banked += now - self._started
            self._started = None
        else:
            self._started = now

    def lap(self, now: float) -> Lap | None:
        if not self.running:
            return None
        total = self.elapsed(now)
        previous = self.laps[-1].total if self.laps else 0.0
        lap = Lap(len(self.laps) + 1, total - previous, total)
        self.laps.append(lap)
        return lap

    def reset(self) -> None:
        self._started = None
        self._banked = 0.0
        self.laps.clear()

    def best_and_worst(self) -> tuple[int, int] | None:
        """Lap numbers of the fastest and slowest lap, once there are two laps to compare."""
        if len(self.laps) < 2:
            return None
        best = min(self.laps, key=lambda l: l.split).number
        worst = max(self.laps, key=lambda l: l.split).number
        return best, worst


def format_span(seconds: float, hundredths: bool = False) -> str:
    """'04:05', '1:02:03', '00:07.31'."""
    # Work in whole hundredths: (7.31 - 7) * 100 is 30.999... in floating point.
    whole, centis = divmod(int(round(seconds * 100)), 100) if hundredths else (int(seconds), 0)
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    text = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    if hundredths:
        text += f".{centis:02d}"
    return text
