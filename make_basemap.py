#!/usr/bin/env python3
"""Reduce a Göteborg OSM GeoJSON extract to the geometry used by the offline map."""

import argparse
import json
import lzma
import re
from pathlib import Path

VIEW = (11.68, 57.53, 12.24, 57.85)
ROAD_GROUPS = {
    "motorway": {"motorway", "motorway_link"},
    "trunk": {"trunk", "trunk_link"},
    "primary": {"primary", "primary_link"},
    "secondary": {"secondary", "secondary_link"},
    "tertiary": {"tertiary", "tertiary_link"},
    "residential": {"residential", "unclassified", "living_street"},
}
ROAD_CLASS = {highway: road_class for road_class, highways in ROAD_GROUPS.items() for highway in highways}


def simplify(points, tolerance):
    if len(points) <= 2:
        return points
    x1, y1 = points[0]
    x2, y2 = points[-1]
    dx, dy = x2 - x1, y2 - y1
    length = dx * dx + dy * dy
    furthest, index = 0.0, 0
    for i, (x, y) in enumerate(points[1:-1], 1):
        if length:
            t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / length))
            px, py = x1 + t * dx, y1 + t * dy
        else:
            px, py = x1, y1
        distance = (x - px) ** 2 + (y - py) ** 2
        if distance > furthest:
            furthest, index = distance, i
    if furthest <= tolerance * tolerance:
        return [points[0], points[-1]]
    left = simplify(points[: index + 1], tolerance)
    right = simplify(points[index:], tolerance)
    return left[:-1] + right


def rounded(points, tolerance):
    return [[round(x, 5), round(y, 5)] for x, y in simplify(points, tolerance)]


def intersects(coordinates):
    min_lon, min_lat, max_lon, max_lat = VIEW
    stack = [coordinates]
    while stack:
        item = stack.pop()
        if item and isinstance(item[0], (int, float)):
            lon, lat = item
            if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                return True
        else:
            stack.extend(item)
    return False


def center(coordinates):
    stack = [coordinates]
    points = []
    while stack:
        item = stack.pop()
        if item and isinstance(item[0], (int, float)):
            points.append(item)
        elif item:
            stack.extend(item)
    if not points:
        return None
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def normalize(value):
    return " ".join(re.sub(r"[^\w]+", " ", str(value).casefold()).split())


def polygons(coordinates, tolerance):
    result = []
    for polygon in coordinates:
        rings = [rounded(ring, tolerance) for ring in polygon if len(ring) >= 4]
        if rings:
            result.append(rings)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default="/tmp/Goeteborg.osm.geojson.xz")
    parser.add_argument("--output", default="data/basemap.json")
    parser.add_argument("--addresses-output", default="data/addresses.json")
    args = parser.parse_args()

    result = {"bounds": VIEW, "land": [], "green": [], "coastline": [], "water": [], "roads": {key: [] for key in ROAD_GROUPS}, "railways": [], "waterways": [], "labels": []}
    addresses = {}
    road_labels = {}
    with lzma.open(args.source, "rt", encoding="utf-8") as source:
        for raw_line in source:
            raw_line = raw_line.strip().rstrip(",")
            if not raw_line.startswith('{"type":"Feature"'):
                continue
            try:
                feature = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates")
            properties = feature.get("properties") or {}
            if not coordinates or not intersects(coordinates):
                continue

            kind = geometry.get("type")
            street = properties.get("addr:street")
            house_number = properties.get("addr:housenumber")
            if street and house_number:
                point = center(coordinates)
                if point:
                    lon, lat = point
                    if VIEW[0] <= lon <= VIEW[2] and VIEW[1] <= lat <= VIEW[3]:
                        key = (normalize(street), normalize(house_number))
                        priority = {"Point": 0, "LineString": 1}.get(kind, 2)
                        current = addresses.get(key)
                        if current is None or priority < current[0]:
                            addresses[key] = (priority, str(street), str(house_number), round(lon, 5), round(lat, 5))

            highway = properties.get("highway")
            natural = properties.get("natural")
            water = properties.get("water")
            landuse = properties.get("landuse")
            waterway = properties.get("waterway")
            railway = properties.get("railway")
            leisure = properties.get("leisure")
            place = properties.get("place")
            name = properties.get("name")

            if kind == "Point" and name and place in {"city", "town", "village", "suburb", "quarter", "neighbourhood"}:
                lon, lat = coordinates
                if VIEW[0] <= lon <= VIEW[2] and VIEW[1] <= lat <= VIEW[3]:
                    result["labels"].append([round(lon, 5), round(lat, 5), str(name), place])

            if kind == "LineString" and highway in ROAD_CLASS:
                tolerance = 0.00006 if ROAD_CLASS[highway] in {"tertiary", "residential"} else 0.0001
                result["roads"][ROAD_CLASS[highway]].append(rounded(coordinates, tolerance))
                road_class = ROAD_CLASS[highway]
                if name and road_class != "residential":
                    key = (normalize(name), road_class)
                    if key not in road_labels or len(coordinates) > road_labels[key][0]:
                        road_labels[key] = (len(coordinates), center(coordinates), str(name), road_class)
            elif kind == "LineString" and natural == "coastline":
                result["coastline"].append(rounded(coordinates, 0.00012))
            elif kind == "LineString" and waterway in {"river", "canal"}:
                result["waterways"].append(rounded(coordinates, 0.00008))
            elif kind == "LineString" and railway in {"rail", "tram"}:
                result["railways"].append(rounded(coordinates, 0.00008))
            elif kind == "MultiPolygon" and natural == "coastline":
                result["land"].extend(polygons(coordinates, 0.00015))
            elif kind == "MultiPolygon" and (natural == "water" or water or landuse in {"reservoir", "basin"}):
                result["water"].extend(polygons(coordinates, 0.0001))
            elif kind == "MultiPolygon" and (natural == "wood" or landuse in {"forest", "cemetery", "recreation_ground"} or leisure in {"park", "garden", "nature_reserve"}):
                result["green"].extend(polygons(coordinates, 0.00012))

    for _, point, name, road_class in road_labels.values():
        if point:
            result["labels"].append([round(point[0], 5), round(point[1], 5), name, f"road-{road_class}"])

    output = Path(args.output)
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    street_names = sorted({address[1] for address in addresses.values()}, key=str.casefold)
    street_ids = {street: index for index, street in enumerate(street_names)}
    address_rows = sorted(
        ([street_ids[street], number, lon, lat] for _, street, number, lon, lat in addresses.values()),
        key=lambda row: (street_names[row[0]].casefold(), normalize(row[1])),
    )
    addresses_output = Path(args.addresses_output)
    addresses_output.parent.mkdir(exist_ok=True)
    addresses_output.write_text(
        json.dumps({"streets": street_names, "addresses": address_rows}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"Wrote {output}: {len(result['land'])} land polygons, "
        f"{len(result['water'])} water polygons, "
        f"{sum(map(len, result['roads'].values()))} road segments; "
        f"{addresses_output}: {len(address_rows)} addresses."
    )


if __name__ == "__main__":
    main()
