#!/usr/bin/env python3
"""Pre-render the complete offline map as SVG and add optional interaction."""

import html
import json
import math
from pathlib import Path
from urllib.parse import quote

DATA = Path("data/schools.json")
BASEMAP = Path("data/basemap.json")
ADDRESSES = Path("data/addresses.json")
OUTPUTS = (Path("public/index.html"), Path("public/map.html"), Path("docs/index.html"))
SURVEY_ROOT = "2026\\UTBILDNING_Föräldrar och barn om förskolan"


def build():
    schools = json.loads(DATA.read_text(encoding="utf-8"))
    for school in schools:
        category = f'{SURVEY_ROOT}\\{school["area"]}\\{school["name"]}'
        school["source_url"] = "https://enkater.goteborg.se/ListEnkater.aspx?Kat=" + quote(category, safe="")
    basemap = json.loads(BASEMAP.read_text(encoding="utf-8"))
    addresses = json.loads(ADDRESSES.read_text(encoding="utf-8"))
    min_lon, min_lat, max_lon, max_lat = basemap["bounds"]
    cos_lat = math.cos(math.radians((min_lat + max_lat) / 2))
    width = 1000.0
    height = (max_lat - min_lat) / ((max_lon - min_lon) * cos_lat) * width

    def project(point):
        lon, lat = point
        return (
            (lon - min_lon) / (max_lon - min_lon) * width,
            (max_lat - lat) / (max_lat - min_lat) * height,
        )

    def line_path(points):
        return " ".join(
            f"{'M' if index == 0 else 'L'}{x:.2f},{y:.2f}"
            for index, point in enumerate(points)
            for x, y in (project(point),)
        )

    def polygon_path(rings):
        return " ".join(f"{line_path(ring)} Z" for ring in rings)

    geometry = [f'<rect class="sea" width="{width:.2f}" height="{height:.2f}"/>']
    geometry.extend(f'<path class="land" d="{polygon_path(polygon)}"/>' for polygon in basemap["land"])
    geometry.extend(f'<path class="coastline" d="{line_path(line)}"/>' for line in basemap["coastline"])
    geometry.extend(f'<path class="water" d="{polygon_path(polygon)}"/>' for polygon in basemap["water"])
    geometry.extend(f'<path class="waterway" d="{line_path(line)}"/>' for line in basemap["waterways"])
    for road_class in ("secondary", "primary", "trunk", "motorway"):
        geometry.extend(
            f'<path class="road {road_class}" d="{line_path(line)}"/>'
            for line in basemap["roads"][road_class]
        )

    markers = []
    for index, school in enumerate(schools):
        x, y = project((school["lng"], school["lat"]))
        score = school["score"]
        color = "#16834b" if score >= 4.5 else "#dfa900" if score >= 4 else "#c9463d"
        label = html.escape(
            f'{school["name"]} — {score:.2f}, svarsfrekvens {school["response_rate"]}%',
            quote=False,
        )
        url = html.escape(school["source_url"], quote=True)
        markers.append(
            f'<a href="{url}" target="_blank" rel="noopener">'
            f'<circle class="marker" data-index="{index}" cx="{x:.2f}" cy="{y:.2f}" '
            f'r="5.2" fill="{color}" tabindex="0"><title>{label}</title></circle></a>'
        )

    template = Path("template.html").read_text(encoding="utf-8")
    document = (
        template.replace("MAP_VIEWBOX", f"0 0 {width:.2f} {height:.2f}")
        .replace("MAP_WIDTH", f"{width:.2f}")
        .replace("MAP_HEIGHT", f"{height:.2f}")
        .replace("MAP_MIN_LON", repr(min_lon))
        .replace("MAP_MIN_LAT", repr(min_lat))
        .replace("MAP_MAX_LON", repr(max_lon))
        .replace("MAP_MAX_LAT", repr(max_lat))
        .replace("BASEMAP_SVG", "".join(geometry))
        .replace("MARKERS_SVG", "".join(markers))
        .replace("SCHOOL_DATA", json.dumps(schools, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
        .replace("ADDRESS_DATA", json.dumps(addresses, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    )
    for output in OUTPUTS:
        output.parent.mkdir(exist_ok=True)
        output.write_text(document, encoding="utf-8")
    print(f"Wrote {', '.join(map(str, OUTPUTS))} with {len(schools)} pre-rendered schools.")


if __name__ == "__main__":
    build()
