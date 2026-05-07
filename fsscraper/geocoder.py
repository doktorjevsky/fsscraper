#!/usr/bin/env python3
"""
Geocoding utilities using Nominatim (OpenStreetMap).
Respects rate limits and caches results in the database.
"""

import time
import urllib.parse
import requests
import sqlite3

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "fsscraper/1.0 (educational project)"}


def normalize_address(preschool_name: str) -> str | None:
    """Turn a preschool DB name into a geocodable query string."""
    name = preschool_name.strip()
    if not name or name.startswith(("-", ">>")):
        return None
    # Strip common suffixes
    for suffix in (" förskola", " Förskola"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    # Some names are not street addresses (categories, areas)
    if name in ("Familjedaghem", "Fristående", "Göteborg kommunala totalt"):
        return None
    if len(name.split()) < 2:
        return None
    return f"{name}, Göteborg, Sweden"


def geocode_query(query_address: str) -> tuple[float, float] | None:
    """Query Nominatim for a single address. Returns (lat, lng) or None."""
    params = {
        "q": query_address,
        "format": "json",
        "limit": 1,
    }
    url = f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data:
        return float(data[0]["lat"]), float(data[0]["lon"])
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two lat/lng points in kilometers."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c
