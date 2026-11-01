# Förskolekollen Göteborg

No database and no runtime map service:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python scrape.py  # writes data/schools.json
.venv/bin/python build.py   # embeds surveys + Göteborg geometry in public/index.html
```

`public/index.html` is ready for GitLab Pages or any other static host and opens directly from disk. The custom SVG renderer, Göteborg roads/water/coastline, address search, scores, and markers are all embedded. Opening the original survey PDF is the only feature that requires internet access.

If a browser restricts `file://` pages, serve the same static files locally—still fully offline:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory public
```

Then open <http://127.0.0.1:8765/map.html>.

`data/basemap.json` and `data/addresses.json` are compact checked-in extracts generated from OpenStreetMap data. To regenerate both from a fresh BBBike Göteborg GeoJSON extract:

```bash
.venv/bin/python make_basemap.py /path/to/Goeteborg.osm.geojson.xz
```
