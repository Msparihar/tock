#!/bin/zsh -f
# A clean shell for recording the demo: tock on PATH, demo alarms, short prompt, sound muted.
cd "$(dirname "$0")/.."
export TOCK_HOME="$PWD/demo/out/home" TOCK_MUTE=1 TERM=xterm-256color COLORTERM=truecolor
export PATH="$PWD/.venv/bin:$PATH" ZDOTDIR="$PWD/demo/zdot"
clear
exec zsh -i
