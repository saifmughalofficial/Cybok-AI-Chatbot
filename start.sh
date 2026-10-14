#!/usr/bin/env bash
# Cybok launcher for macOS / Linux:  bash start.sh
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if [ ! -x ".venv/bin/python" ]; then
  echo "  [1/3] Creating virtual environment (first run only)..."
  $PY -m venv .venv
fi
echo "  [2/3] Checking packages..."
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
echo "  [3/3] Starting Cybok..."
exec .venv/bin/python run.py "$@"
