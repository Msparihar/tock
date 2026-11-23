# Plan: tock, a terminal alarm clock

I wrote this before any code. The git history shows it as the first commit.

## 1. The problem

The brief says: "Build an alarm clock as a Python CLI application. CLI only, no
web UI, no database. There's no detailed spec."

So I first decide who uses it and what "works" means.

- **Who:** a developer who lives in the terminal and wants an alarm, a timer or
  a stopwatch without leaving it.
- **The one job that must never fail:** an alarm set for 07:30 rings at 07:30,
  and still exists after the app restarts.
- **Everything else** (timer, stopwatch, themes) is useful only if that job is solid.

## 2. Questions I asked the AI, and what I decided

| Question | Options the AI gave | My decision and why |
|---|---|---|
| Does it have to ring while the app is closed? | launchd/cron service, a daemon, in-app only | **In-app only.** A background service is OS-specific and can't be tested in the time I have. The README states the limit plainly, and missed alarms are reported on the next launch. |
| How do alarms fire? | `sleep(until)`, check `now == target`, check `now >= due` every tick | **`now >= due` every tick.** A laptop that sleeps through the target skips an equality check and wakes late from a long sleep. |
| How are repeating alarms stored? | a fixed UTC instant, local wall time plus weekdays | **Local wall time plus weekdays.** "07:30 on weekdays" should stay 07:30 across daylight-saving changes. |
| What about clock changes? | ignore, raise, define a rule | **A rule, with tests.** A time that doesn't exist (spring forward) fires at the next real minute. A time that happens twice (fall back) fires once. |
| Parse "7:30pm" with `dateparser`? | `dateparser`, `parsedatetime`, a small parser | **A small parser.** I need four shapes (`7:30`, `7:30pm`, `in 20m`, `1h30m`). `dateparser` loads slowly and has had day-skip bugs; `parsedatetime` is unmaintained. Mine is 60 lines with tests. |
| Sound and notifications? | `playsound3`, `simpleaudio`, `desktop-notifier`, system tools | **System tools.** `afplay` and `osascript` on macOS, `paplay`/`notify-send` on Linux, the terminal bell everywhere else. `desktop-notifier` needs a signed Python, and `simpleaudio` is abandoned. |
| Where is data kept, with no database? | SQLite, JSON, TOML | **One JSON file**, written to a temp file and renamed into place so a crash can't half-write it. It has a schema version, and a corrupt file gives a clear message. |
| How do I test time without waiting? | `freezegun`, monkeypatching, pass the clock in | **Pass `now` in.** The scheduling core is pure functions of `(alarm, now)`, so tests set any time instantly. |
| What UI? | argparse only, curses, Textual | **Both.** Plain commands (`tock add 7:30 --repeat weekdays`) for scripting, and a Textual app for daily use. Both call the same core, so the UI stays thin. |

## 3. Features, ranked

I had the AI survey open-source terminal clocks: termdown (1.6k stars),
tty-clock, peaclock, caarlos0/timer, pomo, timr-tui and clock-tui. The finding
that shaped the plan: **none of them has real alarms**. They are timers,
stopwatches and big clocks. Repeating alarms, labels, an on/off toggle and
snooze come from the phone clock apps (iOS defaults snooze to 9 minutes).
So I take the timer and stopwatch ideas from the terminal tools and the alarm
model from the phone apps. In build order:

Must ship:
1. Add, list, edit, enable/disable and delete alarms.
2. Labels on alarms ("Standup", "Gym").
3. One-time alarms and repeating alarms (every day, weekdays, weekends, picked days).
4. An alarm rings on time: a full-screen alert, a sound and a desktop notification.
5. Snooze (per-alarm length, 9 minutes by default) and dismiss.
6. Alarms survive a restart.
7. Missed alarms are reported once on the next launch.
8. Times typed the way people say them: `7:30`, `7:30pm`, `19:30`, `in 20m`.
9. Tests for the scheduling core.

Then:
10. A big live clock with the date and the next alarm.
11. Countdown timer with presets, pause/resume, "+1 min" while running and a progress bar.
12. Stopwatch with laps.
13. 12/24-hour toggle.
14. Mouse and keyboard for everything; a key-help footer.
15. Commands for scripts: `tock add`, `tock list`, `tock rm`, `tock next`, `tock timer 5m`.

Cut, on purpose:
- A background service (see section 2).
- Custom sound files and themes beyond Textual's built-in ones.
- World clocks and time zones other than the system one.
- Sync across devices.

## 4. Design

```
src/tock/
  core/        pure logic, no I/O, no Textual
    models.py    Alarm, Weekday sets
    parse.py     "7:30pm", "in 20m", "weekdays" -> values
    schedule.py  next_fire(alarm, now)  <- the one function everything trusts
    engine.py    AlarmEngine.tick(now) -> alarms that are due; snooze; missed
    timers.py    Countdown and Stopwatch state machines driven by monotonic time
  store.py     atomic JSON load/save
  alert.py     sound + notification, with fallbacks
  cli.py       argparse commands
  tui/         Textual app; calls the core, holds no rules of its own
```

## 5. How I will check it

- Unit tests: next fire later today, already passed today, weekday rollover,
  one-time alarms, both daylight-saving cases, snooze, missed alarms,
  parsing, save/load round trip, corrupt file.
- By hand: set an alarm 10 seconds out, let it ring, snooze it, let it ring
  again, dismiss it, quit and reopen, and check that the alarm is still there.
