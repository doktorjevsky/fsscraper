# Förskolekollen Göteborg

No database and no runtime map service:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python scrape.py  # writes data/schools.json
.venv/bin/python build.py   # builds hosted and single-file versions
```

`public/index.html` is the efficient hosted version. Map and school data are rendered immediately; the large address index in `public/addresses.json` is fetched only when address search is opened and can be cached separately by the browser.

`public/map.html` is the self-contained offline version. The custom SVG renderer, Göteborg roads/water/coastline, address search, scores, markers, and addresses are embedded in that one file. Opening the original survey page is the only feature that requires internet access.

If a browser restricts `file://` pages, serve the same static files locally—still fully offline:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory public
```

Then open <http://127.0.0.1:8765/map.html>.

`data/basemap.json` and `data/addresses.json` are compact checked-in extracts generated from OpenStreetMap data. To regenerate both from a fresh BBBike Göteborg GeoJSON extract:

```bash
.venv/bin/python make_basemap.py /path/to/Goeteborg.osm.geojson.xz
```
