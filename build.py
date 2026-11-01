#!/usr/bin/env python3
"""Pre-render the complete offline map as SVG and add optional interaction."""

import base64
import html
import io
import json
import math
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageDraw

DATA = Path("data/schools.json")
BASEMAP = Path("data/basemap.json")
ADDRESSES = Path("data/addresses.json")
WEB_OUTPUTS = (Path("public/index.html"), Path("docs/index.html"))
OFFLINE_OUTPUT = Path("public/map.html")
ADDRESS_OUTPUTS = (Path("public/addresses.json"), Path("docs/addresses.json"))
BASEMAP_IMAGE_OUTPUTS = (Path("public/basemap.webp"), Path("docs/basemap.webp"))
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

    raster_scale = 2
    image = Image.new("RGB", (round(width * raster_scale), round(height * raster_scale)), "#edf0e7")
    draw = ImageDraw.Draw(image)

    def pixels(points):
        return [(round(x * raster_scale), round(y * raster_scale)) for point in points for x, y in (project(point),)]

    for polygon in basemap["land"]:
        draw.polygon(pixels(polygon[0]), fill="#f5f6f1")
        for hole in polygon[1:]:
            draw.polygon(pixels(hole), fill="#edf0e7")
    for line in basemap["coastline"]:
        draw.line(pixels(line), fill="#80b5c3", width=round(1.2 * raster_scale), joint="curve")
    for polygon in basemap["water"]:
        draw.polygon(pixels(polygon[0]), fill="#b8d7df", outline="#9bc5d0", width=max(1, round(.6 * raster_scale)))
        for hole in polygon[1:]:
            draw.polygon(pixels(hole), fill="#f5f6f1")
    for line in basemap["waterways"]:
        draw.line(pixels(line), fill="#82b9c7", width=round(2.4 * raster_scale), joint="curve")
    road_styles = {"secondary": ("#d6d1c6", 1), "primary": ("#c7bdad", 1.4), "trunk": ("#d9b896", 1.8), "motorway": ("#d69b78", 2.2)}
    for road_class in ("secondary", "primary", "trunk", "motorway"):
        color, stroke_width = road_styles[road_class]
        for line in basemap["roads"][road_class]:
            draw.line(pixels(line), fill=color, width=max(1, round(stroke_width * raster_scale)), joint="curve")
    raster_buffer = io.BytesIO()
    image.save(raster_buffer, format="WEBP", lossless=True, method=6)
    raster_bytes = raster_buffer.getvalue()

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
        .replace("MARKERS_SVG", "".join(markers))
        .replace("SCHOOL_DATA", json.dumps(schools, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    )
    web_basemap = f'<image class="basemap-image" href="basemap.webp" width="{width:.2f}" height="{height:.2f}"/>'
    offline_basemap = f'<image class="basemap-image" href="data:image/webp;base64,{base64.b64encode(raster_bytes).decode()}" width="{width:.2f}" height="{height:.2f}"/>'
    web_document = document.replace("BASEMAP_SVG", web_basemap).replace("ADDRESS_DATA", "null")
    offline_document = document.replace("BASEMAP_SVG", offline_basemap).replace("ADDRESS_DATA", json.dumps(addresses, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    for output in WEB_OUTPUTS:
        output.parent.mkdir(exist_ok=True)
        output.write_text(web_document, encoding="utf-8")
    OFFLINE_OUTPUT.parent.mkdir(exist_ok=True)
    OFFLINE_OUTPUT.write_text(offline_document, encoding="utf-8")
    address_payload = ADDRESSES.read_text(encoding="utf-8")
    for output in ADDRESS_OUTPUTS:
        output.parent.mkdir(exist_ok=True)
        output.write_text(address_payload, encoding="utf-8")
    for output in BASEMAP_IMAGE_OUTPUTS:
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(raster_bytes)
    print(f"Wrote {', '.join(map(str, WEB_OUTPUTS))} plus {OFFLINE_OUTPUT} with {len(schools)} pre-rendered schools.")


if __name__ == "__main__":
    build()
