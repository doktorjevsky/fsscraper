# Förskolekollen Göteborg

> A scraper, database, and interactive map for Göteborg's municipal preschool parent satisfaction surveys.

**Disclaimer:** This project was heavily "vibe coded" — built iteratively through conversation with an AI assistant rather than being meticulously architected from the ground up. It works well for its intended purpose, but don't expect enterprise-grade software engineering patterns throughout. 

Each year, the City of Göteborg publishes PDF survey results for every preschool. This tool crawls those PDFs, extracts structured data, geocodes the addresses, and produces a **standalone interactive HTML map** that works anywhere — no server required.

---

## What you get

- **Scraped data** from all 11 administrative areas (~300 main preschools, 2026)
- **SQLite database** (`surveys.db`) with response rates, scores, and geocoded coordinates
- **Standalone map** (`preschool_map_2026.html`) — a single file with embedded data + Leaflet map
- **CLI tool** for ranking, filtering, and exporting

---

## Quick start

Everything runs in a local Python venv. No global packages required.

### Linux / macOS

```bash
# 1. Install deps and create venv
./scripts/setup.sh

# 2. Scrape all PDFs (creates surveys.db)
./scripts/scrape.sh

# 3. Geocode addresses via Nominatim (free, rate-limited)
./scripts/geocode.sh

# 4. Build the map
./scripts/build_map.sh
```

### Windows

```cmd
# 1. Install deps and create venv
scripts\setup.bat

# 2. Scrape all PDFs
scripts\scrape.bat

# 3. Geocode addresses
scripts\geocode.bat

# 4. Build the map
scripts\build_map.bat
```

Open the artifact:
```bash
firefox preschool_map_2026.html
```

---

## Prerequisites

- **Python 3.12+**
- Internet connection (for crawling and geocoding)

---

## Manual setup

```bash
# Create venv
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# Install deps
pip install -r requirements.txt

# Scrape
python -m fsscraper.cli scrape

# Geocode
python -m fsscraper.cli geocode

# Build map
python build_map.py
```

---

## The map artifact

`preschool_map_2026.html` is a **build artifact** — it is generated from `surveys.db` and should not be edited by hand.

- It is a **single self-contained HTML file** (~200–600 KB)
- It embeds all preschool data as JSON and loads Leaflet from CDN
- It works from `file://` URLs — no web server needed
- Share it, email it, or host it on any static site

The dots on the map are color-coded by overall satisfaction (`Helhetsomdöme`):

| Color | Score | Meaning |
|-------|-------|---------|
| 🟢 Green | 4.5+ | Utmärkt |
| 🔵 Blue | 4.0–4.5 | Bra |
| 🟡 Yellow | 3.5–4.0 | Godkänt |
| 🔴 Red | <3.5 | Underkänt |
| ⚪ Gray | — | Ingen data |

Hover a dot to see the preschool card with all category scores. Click a dot to open the original PDF.

---

## CLI commands

```bash
# List all areas
python -m fsscraper.cli list-areas

# Scrape specific areas only
python -m fsscraper.cli scrape --areas "Centrum 1,Centrum 2"

# Rank preschools by overall score
python -m fsscraper.cli rank
python -m fsscraper.cli rank --area "Sydväst 1" --min-response-rate 30

# Find preschools near your address
python -m fsscraper.cli nearby "Stigbergsliden 5, Göteborg" --radius 2.0

# Export raw data
python -m fsscraper.cli export --format json > data.json
python -m fsscraper.cli export --format csv > data.csv
```

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Crawler   │────▶│  Extractor  │────▶│    DB       │
│  (ASPX/PDF) │     │ (pdfplumber)│     │ (SQLite)    │
└─────────────┘     └─────────────┘     └───────┬─────┘
                                                │
                                         ┌──────┴──────┐
                                         │   Geocoder  │
                                         │  (Nominatim)│
                                         └──────┬──────┘
                                                │
                                         ┌──────┴──────────┐
                                         │  build_map.py   │
                                         │ (HTML artifact) │
                                         └─────────────────┘
```

- **`fsscraper/crawler.py`** — ASPX folder tree crawler and PDF discovery
- **`fsscraper/extractor.py`** — Deterministic PDF table extraction using `pdfplumber`
- **`fsscraper/db.py`** — SQLite schema and queries
- **`fsscraper/geocoder.py`** — Nominatim geocoding, address normalization, haversine distance
- **`fsscraper/cli.py`** — CLI entry point
- **`build_map.py`** — Generates the standalone HTML map from the database

---

## Data model

The scraper stores:
- **Surveys** — year, area, preschool name, sub-unit, PDF URL, response rate
- **Scores** — category, question, value (for preschool, area, GR, Göteborg averages)
- **Addresses** — raw name, normalized query, lat/lng, geocode status

Category means are computed on the fly from the per-question scores to match the PDF summary tables.

---

## Notes

- **Rate limiting:** Geocoding uses Nominatim with a 1-second sleep between requests. This is slow (~5 min for 300 preschools) but free and polite.
- **Address failures:** Some independent preschools and unusual addresses fail geocoding and appear as gray dots.
- **Deterministic parsing:** No AI or vision models are used. All extraction is rule-based via `pdfplumber`.

---

## License

MIT
