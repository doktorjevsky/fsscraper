#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

VENV=".venv"
YEAR="${1:-2026}"

if [ ! -d "$VENV" ]; then
    echo "Virtual environment not found. Run: ./scripts/setup.sh"
    exit 1
fi

echo "Scraping preschool surveys for year $YEAR..."
"$VENV/bin/python" -m fsscraper.cli scrape --year "$YEAR"
