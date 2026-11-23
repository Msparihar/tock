#!/bin/sh
# Fill a fresh demo state with everyday alarms, using the real CLI.
# Times are kept away from the recording hour so nothing rings by surprise.
set -e
export TOCK_HOME="${TOCK_HOME:-$(cd "$(dirname "$0")" && pwd)/out/home}"
rm -rf "$TOCK_HOME"
uv run tock add 6:30am  -l "Gym"                 -r mon,wed,fri
uv run tock add 7:00am  -l "Flight to Bangalore" -s 5
uv run tock add 5:00pm  -l "Weekly review"       -r fri
uv run tock add 9:00pm  -l "Medicine"            -r daily
uv run tock add 10:30pm -l "Wind down"           -r daily
