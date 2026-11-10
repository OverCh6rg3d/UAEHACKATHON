#!/usr/bin/env sh
# Start the DABAB demo: copies demo data if needed, starts the server, opens the browser.
cd "$(dirname "$0")/.." || exit 1
PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && { echo "Python 3.9+ is required"; exit 1; }
exec "$PY" final/start.py
