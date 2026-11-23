from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tock.core.models import EVERY_DAY, WEEKDAYS, WEEKENDS
from tock.core.parse import ParseError, parse_clock, parse_days, parse_duration, parse_when


@pytest.mark.parametrize("text,want", [
    ("7:30", (7, 30, 0)), ("07:30", (7, 30, 0)), ("19:30", (19, 30, 0)),
    ("7:30pm", (19, 30, 0)), ("7:30 PM", (19, 30, 0)), ("7pm", (19, 0, 0)), ("7 a.m.", (7, 0, 0)),
    ("12am", (0, 0, 0)), ("12pm", (12, 0, 0)), ("noon", (12, 0, 0)), ("midnight", (0, 0, 0)),
    ("6:05:30", (6, 5, 30)),
])
def test_clock(text, want):
    assert parse_clock(text) == want


@pytest.mark.parametrize("text", ["25:00", "7:60", "13pm", "0am", "seven", "", "7:3"])
def test_clock_rejects(text):
    with pytest.raises(ParseError):
        parse_clock(text)


@pytest.mark.parametrize("text,secs", [
    ("25", 1500), ("10m", 600), ("1h30m", 5400), ("1h 5m", 3900), ("90s", 90),
    ("2 hours", 7200), ("5:00", 300), ("1:05:00", 3900), ("10 min", 600),
])
def test_duration(text, secs):
    assert parse_duration(text) == timedelta(seconds=secs)


@pytest.mark.parametrize("text", ["0", "0m", "abc", "10x", "25h", "5:75", "10m junk"])
def test_duration_rejects(text):
    with pytest.raises(ParseError):
        parse_duration(text)


def test_when_relative():
    now = datetime(2026, 11, 23, 9, 58, 50, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert parse_when("in 20m", now) == (10, 18, 50)
    assert parse_when("+15s", now) == (9, 59, 5)
    assert parse_when("in 2h", now) == (11, 58, 50)


def test_when_clock():
    now = datetime(2026, 11, 23, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert parse_when("6:30am", now) == (6, 30, 0)


@pytest.mark.parametrize("text,want", [
    ("weekdays", WEEKDAYS), ("weekends", WEEKENDS), ("daily", EVERY_DAY), ("once", frozenset()),
    ("mon,wed,fri", frozenset({0, 2, 4})), ("Mon Wed", frozenset({0, 2})),
    ("mon-fri", WEEKDAYS), ("fri-mon", frozenset({4, 5, 6, 0})), ("tuesday", frozenset({1})),
])
def test_days(text, want):
    assert parse_days(text) == want


def test_days_rejects():
    with pytest.raises(ParseError):
        parse_days("funday")
