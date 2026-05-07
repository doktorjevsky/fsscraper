#!/usr/bin/env python3
"""
CLI for the preschool survey scraper and ranking tool.
"""

import argparse
import sys
import json
from pathlib import Path

from .crawler import crawl, list_areas
from .extractor import extract_survey
from .db import SurveyDB
from .geocoder import normalize_address, geocode_query, haversine_km


def cmd_scrape(args):
    db = SurveyDB(args.db)
    areas = args.areas.split(",") if args.areas else None
    entries = list(crawl(year=args.year, areas=areas))
    print(f"Discovered {len(entries)} PDFs to process.")

    success = 0
    failed = 0
    for entry in entries:
        try:
            data = extract_survey(
                entry["pdf_url"],
                preschool_name=entry["preschool"],
                area_name=entry["area"],
            )
            scores = data.get("category_scores", [])

            # Add a synthetic _self score for each category so ranking is unambiguous
            target_name = entry["sub_unit"] or entry["preschool"]
            for s in scores:
                if target_name in s.get("values", {}):
                    s["values"]["_self"] = s["values"][target_name]

            db.insert_survey(
                year=entry["year"],
                area=entry["area"],
                preschool=entry["preschool"],
                sub_unit=entry["sub_unit"],
                pdf_url=entry["pdf_url"],
                response_rate=data.get("response_rate"),
                footer_name=data.get("footer_name"),
                scores=scores,
            )
            success += 1
            if args.verbose:
                label = f"{entry['preschool']}"
                if entry["sub_unit"]:
                    label += f" / {entry['sub_unit']}"
                print(f"  OK  {label}")
        except Exception as e:
            failed += 1
            label = f"{entry['preschool']}"
            if entry["sub_unit"]:
                label += f" / {entry['sub_unit']}"
            print(f"  FAIL {label}: {e}")

    print(f"\nDone. Success: {success}, Failed: {failed}")


def cmd_rank(args):
    db = SurveyDB(args.db)
    rows = db.rank_by_overall(
        year=args.year,
        area=args.area,
        min_response_rate=args.min_response_rate,
    )
    if not rows:
        print("No data found for the given criteria.")
        return

    print(f"{'Rank':>4}  {'Score':>6}  {'Resp%':>5}  {'Area':<15} {'Preschool'}")
    print("-" * 100)
    rank = 1
    for r in rows:
        if r["sub_unit"] and not args.include_subunits:
            continue
        name = r["preschool"]
        if r["sub_unit"]:
            name += f" / {r['sub_unit']}"
        score = r["score"]
        resp = r["response_rate"] or "?"
        area = r["area"]
        print(f"{rank:>4}  {score:>6}  {resp:>5}  {area:<15} {name}")
        rank += 1


def cmd_list_areas(args):
    areas = list_areas(args.year)
    for a in areas:
        print(a["name"])


def cmd_export(args):
    db = SurveyDB(args.db)
    surveys = db.get_surveys(year=args.year, area=args.area)
    out = []
    for s in surveys:
        scores = db.get_scores(s["id"])
        out.append({
            "year": s["year"],
            "area": s["area"],
            "preschool": s["preschool"],
            "sub_unit": s["sub_unit"],
            "response_rate": s["response_rate"],
            "scores": [dict(r) for r in scores],
        })
    if args.format == "json":
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        import csv
        writer = csv.writer(sys.stdout)
        writer.writerow(["year", "area", "preschool", "sub_unit", "response_rate", "category", "question", "column", "value"])
        for s in out:
            for sc in s["scores"]:
                writer.writerow([
                    s["year"], s["area"], s["preschool"], s["sub_unit"],
                    s["response_rate"], sc["category"], sc["question"],
                    sc["column_name"], sc["value"],
                ])


def cmd_geocode(args):
    db = SurveyDB(args.db)
    rows = db.get_addresses_to_geocode()
    print(f"Found {len(rows)} unique preschool addresses to geocode.")
    import time
    ok = 0
    fail = 0
    for row in rows:
        raw = row["raw_name"]
        query = normalize_address(raw)
        if not query:
            db.insert_address(raw, "", None, None, error="skipped")
            continue
        try:
            result = geocode_query(query)
            if result:
                lat, lng = result
                db.insert_address(raw, query, lat, lng)
                if args.verbose:
                    print(f"  OK   {raw} -> ({lat}, {lng})")
                ok += 1
            else:
                db.insert_address(raw, query, None, None, error="not_found")
                if args.verbose:
                    print(f"  FAIL {raw} -> not found")
                fail += 1
        except Exception as e:
            db.insert_address(raw, query, None, None, error=str(e))
            if args.verbose:
                print(f"  FAIL {raw} -> {e}")
            fail += 1
        time.sleep(1.0)  # Nominatim rate limit
    print(f"\nDone. Geocoded: {ok}, Failed: {fail}")


def cmd_nearby(args):
    db = SurveyDB(args.db)
    # Geocode user's address
    user_query = args.address
    print(f"Geocoding your address: {user_query}")
    user_coords = geocode_query(user_query)
    if not user_coords:
        print("Could not geocode your address. Try a more specific query.")
        sys.exit(1)
    user_lat, user_lng = user_coords
    print(f"Your location: ({user_lat}, {user_lng})")

    # Fetch surveys with coordinates
    rows = db.get_surveys_with_coords(year=args.year, area=args.area)
    results = []
    for r in rows:
        if r["lat"] is None or r["lng"] is None:
            continue
        dist = haversine_km(user_lat, user_lng, r["lat"], r["lng"])
        if dist <= args.radius:
            results.append((dist, r))

    results.sort(key=lambda x: x[0])

    if not results:
        print(f"No preschools found within {args.radius} km.")
        return

    print(f"\n{'Dist(km)':>8}  {'Score':>6}  {'Resp%':>5}  {'Area':<15} {'Preschool'}")
    print("-" * 110)
    for dist, r in results:
        if r["sub_unit"] and not args.include_subunits:
            continue
        name = r["preschool"]
        if r["sub_unit"]:
            name += f" / {r['sub_unit']}"
        score = "?"
        # Fetch overall score on the fly
        scores = db.get_scores(r["id"], category="Helhetsomdöme")
        for sc in scores:
            if sc["column_name"] == "_self" and "Jag är nöjd" in sc["question"]:
                score = sc["value"]
                break
        resp = r["response_rate"] or "?"
        area = r["area"]
        print(f"{dist:>8.2f}  {score:>6}  {resp:>5}  {area:<15} {name}")


def main():
    parser = argparse.ArgumentParser(description="Preschool survey scraper and ranker")
    parser.add_argument("--db", default="surveys.db", help="SQLite database path")
    parser.add_argument("--year", type=int, default=2026, help="Survey year")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    sub = parser.add_subparsers(dest="command", required=True)

    p_scrape = sub.add_parser("scrape", help="Crawl and extract PDFs into DB")
    p_scrape.add_argument("--areas", help="Comma-separated area names (default: all)")
    p_scrape.set_defaults(func=cmd_scrape)

    p_rank = sub.add_parser("rank", help="Rank preschools by overall satisfaction")
    p_rank.add_argument("--area", help="Filter by area")
    p_rank.add_argument("--min-response-rate", type=int, default=0, help="Minimum response rate %%")
    p_rank.add_argument("--include-subunits", action="store_true", help="Also show sub-units")
    p_rank.set_defaults(func=cmd_rank)

    p_areas = sub.add_parser("list-areas", help="List available areas")
    p_areas.set_defaults(func=cmd_list_areas)

    p_export = sub.add_parser("export", help="Export raw data")
    p_export.add_argument("--area", help="Filter by area")
    p_export.add_argument("--format", choices=["json", "csv"], default="json")
    p_export.set_defaults(func=cmd_export)

    p_geocode = sub.add_parser("geocode", help="Geocode all preschool addresses")
    p_geocode.set_defaults(func=cmd_geocode)

    p_nearby = sub.add_parser("nearby", help="Find preschools near an address")
    p_nearby.add_argument("address", help="Your address query (e.g. 'Stigbergsliden 5, Göteborg')")
    p_nearby.add_argument("--radius", type=float, default=2.0, help="Radius in km (default: 2.0)")
    p_nearby.add_argument("--area", help="Filter by area")
    p_nearby.add_argument("--include-subunits", action="store_true", help="Also show sub-units")
    p_nearby.set_defaults(func=cmd_nearby)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
