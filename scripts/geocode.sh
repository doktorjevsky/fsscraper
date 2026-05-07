#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

VENV=".venv"
YEAR="${1:-2026}"

if [ ! -d "$VENV" ]; then
    echo "Virtual environment not found. Run: ./scripts/setup.sh"
    exit 1
fi

echo "Geocoding preschool addresses for year $YEAR..."
"$VENV/bin/python" -m fsscraper.cli geocode --year "$YEAR"
