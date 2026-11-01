#!/usr/bin/env python3
"""Scrape aggregate preschool scores into data/schools.json."""

import io
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import pdfplumber
import requests
from bs4 import BeautifulSoup

BASE = "https://enkater.goteborg.se/"
ROOT = "2026\\UTBILDNING_Föräldrar och barn om förskolan"
OUTPUT = Path("data/schools.json")


def page_url(category):
    return urljoin(BASE, "ListEnkater.aspx?kat=" + quote(category, safe=""))


def soup(session, category):
    response = session.get(page_url(category), timeout=45)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def folders(document):
    result = []
    for link in document.select("a.survey-link[href]"):
        values = parse_qs(urlparse(link["href"]).query).get("kat")
        if not values:
            continue
        name = link.select_one(".survey-link__text").get_text(" ", strip=True)
        result.append((name, unquote(values[0])))
    return result


def report(document):
    link = document.select_one("a.file-link[href$='.pdf']")
    if not link:
        return None
    return urljoin(BASE, quote(link["href"], safe="/:?=&%"))


def overall_score(pdf_bytes, area):
    response_rate = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if response_rate is None:
                match = re.search(r"Svarsfrekvens\s+(\d+)\s*%", text)
                if match:
                    response_rate = int(match.group(1))
            if "Helhetsomdöme" not in text or "Jag är nöjd med mitt barns" not in text:
                continue
            for table in page.extract_tables():
                if not table or len(table) < 2:
                    continue
                headers = [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in table[0]]
                school_column = next((
                    index for index, header in enumerate(headers)
                    if index > 0
                    and header not in {"GR", "Göteborg", area}
                    and not re.fullmatch(r"\d{4}", header)
                ), None)
                if school_column is None:
                    continue
                for row in table[1:]:
                    if not row or "Jag är nöjd" not in str(row[0] or "").replace("\n", " "):
                        continue
                    match = re.search(r"\d+(?:[,.]\d+)?", str(row[school_column] or ""))
                    if match:
                        return float(match.group(0).replace(",", ".")), response_rate
    return None, response_rate


def geocode(session, school):
    address = re.split(r"\s+förskola", school, maxsplit=1, flags=re.I)[0]
    address = re.sub(r"(\d+)\s+och\s+\d+", r"\1", address)
    response = session.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": f"{address}, Göteborg, Sverige", "format": "jsonv2", "limit": 1, "countrycodes": "se"},
        timeout=45,
    )
    response.raise_for_status()
    matches = response.json()
    if not matches:
        return None
    return float(matches[0]["lat"]), float(matches[0]["lon"])


def save(rows):
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    rows = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else []
    done = {row["survey_url"] for row in rows}
    done_names = {row["name"] for row in rows}
    with requests.Session() as session:
        session.headers["User-Agent"] = "fsscraper/1.0 (public survey map)"
        areas = [item for item in folders(soup(session, ROOT)) if item[0] not in {"- Göteborg kommunala totalt -", "Familjedaghem"}]
        schools = []
        for area, category in areas:
            for school, school_category in folders(soup(session, category)):
                if re.search(r"\d", school):
                    schools.append((area, school, school_category))
        print(f"Found {len(schools)} address-named schools.", flush=True)

        for index, (area, school, category) in enumerate(schools, 1):
            if school in done_names:
                continue
            survey_url = report(soup(session, category))
            if not survey_url or survey_url in done:
                continue
            pdf = session.get(survey_url, timeout=90)
            pdf.raise_for_status()
            score, response_rate = overall_score(pdf.content, area)
            coordinates = geocode(session, school)
            time.sleep(1.05)
            if not coordinates:
                print(f"[{index}/{len(schools)}] no coordinates: {school}", flush=True)
                continue
            rows.append({
                "name": school,
                "area": area,
                "lat": coordinates[0],
                "lng": coordinates[1],
                "score": score,
                "response_rate": response_rate,
                "survey_url": survey_url,
            })
            done.add(survey_url)
            done_names.add(school)
            save(rows)
            print(f"[{index}/{len(schools)}] {school}: {score if score is not None else '—'}", flush=True)

    rows.sort(key=lambda row: (row["area"], row["name"]))
    save(rows)
    print(f"Wrote {len(rows)} schools to {OUTPUT}.")


if __name__ == "__main__":
    main()
