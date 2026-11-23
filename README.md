# tock

An alarm clock for the terminal, written in Python.

`tock` opens a full-screen app with a big clock, your alarms, a timer and a
stopwatch. Everything works with the mouse or the keyboard. Plain commands
(`tock add 7:30am -l Standup -r weekdays`) cover scripts and quick changes.

```
uv run tock                                        # open the app
uv run tock add 7:30am -l Standup -r weekdays      # add an alarm
uv run tock add "in 20m" -l Tea                    # or a delay
uv run tock list                                   # see them
uv run tock next                                   # what rings next
uv run tock off 3f / on 3f / rm 3f                 # by id prefix
uv run tock timer 25m -l Focus                     # a countdown right in the shell
uv run pytest                                      # 85 tests, under 10 s
```

Needs Python 3.12+ and [uv](https://docs.astral.sh/uv/). The only runtime dependency is Textual.

## What it does

| Area | Features |
|---|---|
| Clock | Big live clock, date and time zone, next alarm with a countdown, the next five alarms, 12/24-hour toggle (`h`) |
| Alarms | Add, edit, switch on/off, delete with undo. Labels. Once, every day, weekdays, weekends or any days you pick. Snooze length per alarm (9 min by default). |
| Typing times | `7:30`, `7:30pm`, `19:30`, `noon`, `in 20m`, `+90s`. The form checks the time as you type and says when it will ring. |
| Ringing | Full-screen flashing alert, a looping sound, a desktop notification, Snooze or Dismiss. Several alarms at once queue up. |
| Missed alarms | If tock was closed (or the laptop asleep) when an alarm was due, it tells you once on the next start instead of ringing hours late. |
| Timer | Presets (1m to 1h) or any duration, pause/resume, +1 minute, progress bar, rings when done. |
| Stopwatch | Hundredths of a second, laps, fastest and slowest lap marked. |
| Look | Any built-in Textual theme from the command palette (`ctrl+p`); the choice is saved. |

Keys: `1`–`4` switch tabs, `n` new alarm, `e` edit, `space` on/off or start/stop,
`x` delete, `u` undo, `l` lap, `r` reset, `+` add a minute, `q` quit.

## How I approached it

I wrote [docs/PLAN.md](docs/PLAN.md) before any code; the first commit holds
it alone. It has the questions I put to the AI, the options it offered and what
I chose. The short version:

1. **The job that must not fail is "the alarm rings on time and survives a
   restart".** I built and tested that core first, before any screen.
2. **Pure core, thin UI.** `tock/core` has no I/O and never reads the clock;
   every function takes `now`. Tests set any time instantly, so 85 tests run
   in under ten seconds without waiting or mocking.
3. **Fire on `due <= now`, never `== now`.** The app checks twice a second. A
   tick that is late (a busy CPU, a laptop lid) still catches the alarm.
4. **Alarms keep wall time.** "07:30 on weekdays" stays 07:30 when daylight
   saving changes. A time that doesn't exist that day fires at the first real
   minute after it; a time that happens twice fires once. Both cases have tests.
   Comparisons go through UTC, because Python ignores `fold` when two
   datetimes share a `tzinfo`.
5. **One JSON file, written safely.** Write to a temp file, then rename over
   the old one, so a crash can't leave half a file. A file that won't parse is
   moved aside and kept, not deleted, and the app says where it went.
6. **No extra libraries for sound, notifications or parsing.** `afplay` and
   `osascript` on macOS, `paplay`/`notify-send` on Linux, the terminal bell
   anywhere else. A 60-line parser covers the four time formats I need.

### Where I corrected the AI

- It named a method `set_timer` on the app. That hid Textual's own
  `set_timer`, and the app crashed the first time the window resized. The
  headless tests didn't resize, so I added a test that does.
- It put "h" before "hours" in a regex, so `2 hours` failed to parse. A
  parametrised test caught it.
- Its first stopwatch format used `(7.31 - 7) * 100`, which is 30.99 in
  floating point and printed `.30`. It now works in whole hundredths.
- It left the main-screen buttons focusable (Textual's default), so `space`
  pressed whichever button was clicked last instead of starting the timer.
  Those buttons are for the mouse now, and the keys go to the app.

## Layout

```
src/tock/
  core/            pure logic, fully tested
    models.py        Alarm, day sets, formatting
    schedule.py      next_fire(alarm, after) and the DST rules
    engine.py        check(now) -> ringing / missed; snooze; dismiss
    parse.py         "7:30pm", "in 20m", "weekdays"
    timers.py        Countdown and Stopwatch on monotonic time
  store.py         atomic JSON save/load, versioned
  session.py       store + engine, shared by CLI and app
  alert.py         sound and notifications with fallbacks
  cli.py           argparse commands
  tui/             Textual app, screens, big-digit widget, styles
tests/             schedule, engine, parse, timers, store, and the app end to end
```

## Limits, on purpose

- **Alarms ring only while tock is open.** A background service (launchd,
  systemd) is OS-specific and I could not test it well in the time. Missed
  alarms are reported on the next start, so nothing is lost silently.
- One time zone: the system's.
- Two tock windows can both edit the file. The app notices outside changes and
  reloads, but the last writer wins.
- System sounds only; no custom sound files.

## Next steps

1. `tock daemon` with a launchd/systemd unit, so alarms ring with the app closed.
2. A file lock for concurrent writers.
3. Countdown to a date, and several timers at once.
