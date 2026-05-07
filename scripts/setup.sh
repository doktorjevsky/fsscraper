#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

VENV=".venv"

if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV"
fi

echo "Installing dependencies..."
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r requirements.txt

echo "Done. Virtual environment ready at $VENV/"
