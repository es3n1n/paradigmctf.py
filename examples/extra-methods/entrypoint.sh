#!/usr/bin/env sh
set -ex

MODE="${LAUNCHER_MODE:-nc}"

if [ "$MODE" = "nc" ]; then
    /app/pow &
    exec socat TCP-LISTEN:${FORWARD_PORT:-1338},reuseaddr,fork exec:"/challenge/challenge.py"
else
    exec /challenge/challenge.py
fi
