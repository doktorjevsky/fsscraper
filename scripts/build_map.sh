#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

VENV=".venv"

if [ ! -d "$VENV" ]; then
    echo "Virtual environment not found. Run: ./scripts/setup.sh"
    exit 1
fi

echo "Building docs/preschool_map_2026.html..."
"$VENV/bin/python" build_map.py

echo "Done. Open docs/preschool_map_2026.html in your browser."
