"""Command line: `tock` opens the app; subcommands script it.

  tock                                  open the app
  tock add 7:30am -l Standup -r weekdays
  tock add "in 20m" -l Tea
  tock list | tock next | tock rm 3f | tock off 3f | tock on 3f
  tock timer 25m -l Focus               a countdown right here in the shell
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .core.models import DEFAULT_SNOOZE_MINUTES, Alarm, format_time
from .core.parse import ParseError, parse_days, parse_duration, parse_when
from .core.schedule import due_time, humanize_until
from .core.timers import Countdown, format_span
from .session import Session, local_now


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tock", description="A terminal alarm clock.")
    p.add_argument("--file", type=Path, help="state file (default: ~/.config/tock/state.json, or $TOCK_HOME)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("ui", help="open the app (the default)")

    add = sub.add_parser("add", help="add an alarm")
    add.add_argument("when", help='a time like 7:30, 7:30pm, 19:30, or a delay like "in 20m"')
    add.add_argument("-l", "--label", default="")
    add.add_argument("-r", "--repeat", default="once", help="once, daily, weekdays, weekends, or mon,wed,fri")
    add.add_argument("-s", "--snooze", type=int, default=DEFAULT_SNOOZE_MINUTES, help="snooze minutes (default 9)")

    sub.add_parser("list", help="list alarms")
    sub.add_parser("next", help="show the next alarm")
    for name, text in (("rm", "delete an alarm"), ("on", "switch an alarm on"), ("off", "switch an alarm off")):
        sub.add_parser(name, help=text).add_argument("id", help="alarm id, or the start of it")

    timer = sub.add_parser("timer", help="run a countdown in this terminal")
    timer.add_argument("duration", help="25, 10m, 1h30m, 90s or 5:00")
    timer.add_argument("-l", "--label", default="")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd in (None, "ui"):
        from .tui.app import TockApp  # Textual loads only when the app opens
        TockApp(Session(args.file)).run()
        return 0
    try:
        return COMMANDS[args.cmd](Session(args.file), args)
    except (ParseError, ValueError, KeyError) as exc:
        print(f"tock: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return 2


def cmd_add(s: Session, args) -> int:
    now = local_now()
    h, m, sec = parse_when(args.when, now)
    alarm = s.engine.add(Alarm(hour=h, minute=m, second=sec, label=args.label, days=parse_days(args.repeat),
                               snooze_minutes=args.snooze, armed_at=now))
    s.save()
    due = due_time(alarm, now)
    print(f"Added {alarm.id}  {alarm.time_text(s.settings.clock_24h)}  {alarm.repeat_text()}"
          f"{'  ' + alarm.label if alarm.label else ''}  (rings {humanize_until(due, now)})")
    return 0


def cmd_list(s: Session, args) -> int:
    alarms = s.engine.alarms
    if not alarms:
        print("No alarms. Add one: tock add 7:30am -l Standup -r weekdays")
        return 0
    now = local_now()
    print(f"{'ID':<8}{'TIME':<12}{'REPEAT':<18}{'ON':<5}{'NEXT':<14}LABEL")
    for a in alarms:
        due = due_time(a, now)
        print(f"{a.id:<8}{a.time_text(s.settings.clock_24h):<12}{a.repeat_text():<18}{'yes' if a.enabled else 'no':<5}"
              f"{humanize_until(due, now) if due else '-':<14}{a.label}")
    return 0


def cmd_next(s: Session, args) -> int:
    now = local_now()
    nxt = s.engine.next_up(now)
    if not nxt:
        print("No alarms are on.")
        return 1
    alarm, due = nxt
    clock = format_time(due.hour, due.minute, due.second, s.settings.clock_24h)
    print(f"{alarm.label or 'Alarm'} at {due:%a} {clock}, {humanize_until(due, now)}")
    return 0


def cmd_rm(s: Session, args) -> int:
    alarm = s.engine.remove(s.engine.find(args.id).id)
    s.save()
    print(f"Deleted {alarm.id} ({alarm.time_text()} {alarm.label})".rstrip())
    return 0


def _set_enabled(s: Session, args, on: bool) -> int:
    alarm = s.engine.set_enabled(s.engine.find(args.id).id, on, local_now())
    s.save()
    print(f"{alarm.id} is {'on' if on else 'off'}")
    return 0


def cmd_timer(s: Session, args) -> int:
    from .alert import Ringer, notify
    countdown = Countdown(parse_duration(args.duration).total_seconds(), args.label)
    countdown.start(time.monotonic())
    name = args.label or "Timer"
    try:
        while not countdown.finished(now := time.monotonic()):
            bar_width = 30
            filled = int(countdown.progress(now) * bar_width)
            sys.stdout.write(f"\r{name}  {format_span(countdown.remaining(now) + 0.999)}  "
                             f"[{'#' * filled}{'.' * (bar_width - filled)}]  Ctrl-C to cancel ")
            sys.stdout.flush()
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    print(f"\r{name}  done.{' ' * 50}")
    notify("tock", f"{name} is done")
    ringer = Ringer()
    ringer.start()
    try:
        input("Press Enter to stop the sound. ")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        ringer.stop()
    return 0


COMMANDS = {
    "add": cmd_add,
    "list": cmd_list,
    "next": cmd_next,
    "rm": cmd_rm,
    "on": lambda s, a: _set_enabled(s, a, True),
    "off": lambda s, a: _set_enabled(s, a, False),
    "timer": cmd_timer,
}
