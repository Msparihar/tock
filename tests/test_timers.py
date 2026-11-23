from tock.core.timers import Countdown, Stopwatch, format_span


def test_countdown_runs_pauses_and_finishes():
    c = Countdown(60)
    assert not c.finished(0) and c.remaining(0) == 60
    c.start(100)
    assert c.remaining(130) == 30
    c.pause(130)
    assert c.remaining(500) == 30  # paused time doesn't count
    c.start(500)
    assert not c.finished(529)
    assert c.finished(530) and c.remaining(600) == 0


def test_countdown_add_time_while_running():
    c = Countdown(60)
    c.start(0)
    c.add(60)
    assert c.remaining(30) == 90
    assert round(c.progress(30), 2) == 0.25


def test_countdown_reset():
    c = Countdown(10)
    c.start(0)
    c.reset()
    assert not c.started and c.remaining(99) == 10


def test_stopwatch_laps_and_best_worst():
    s = Stopwatch()
    assert s.lap(0) is None  # no laps while stopped
    s.toggle(0)
    s.lap(10)
    s.lap(15)  # 5 s, the fastest
    s.lap(30)  # 15 s, the slowest
    assert [(l.split, l.total) for l in s.laps] == [(10, 10), (5, 15), (15, 30)]
    assert s.best_and_worst() == (2, 3)
    s.toggle(30)
    assert s.elapsed(1000) == 30
    s.reset()
    assert s.elapsed(0) == 0 and s.laps == []


def test_format_span():
    assert format_span(245) == "04:05"
    assert format_span(3723) == "1:02:03"
    assert format_span(7.31, hundredths=True) == "00:07.31"
