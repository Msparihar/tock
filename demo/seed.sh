#!/bin/sh
# Fill a fresh demo state with everyday alarms, using the real CLI.
set -e
export TOCK_HOME="${TOCK_HOME:-$(dirname "$0")/out/home}"
rm -rf "$TOCK_HOME"
uv run tock add 6:30am  -l "Gym"           -r mon,wed,fri
uv run tock add 9:45am  -l "Daily standup" -r weekdays -s 5
uv run tock add 1:30pm  -l "Lunch"         -r weekdays
uv run tock add 9:00pm  -l "Medicine"      -r daily
uv run tock add 10:30pm -l "Wind down"     -r daily
uv run tock add 7:00am  -l "Flight to Bangalore" -s 5
