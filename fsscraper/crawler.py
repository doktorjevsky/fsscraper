#!/usr/bin/env python3
"""
Crawler for Göteborgs Stad enkätundersökningar.
Walks the ASPX folder tree and discovers PDF links.
"""

import re
import urllib.parse
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://enkater.goteborg.se"


def fetch_soup(path: str) -> BeautifulSoup:
    url = f"{BASE_URL}/{path}" if not path.startswith("http") else path
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_list_page(soup: BeautifulSoup, parent_category: str):
    """
    Parse a ListEnkater.aspx page and yield:
    - folders: dicts with name and kat param
    - pdfs: dicts with name and relative url
    """
    results = {"folders": [], "pdfs": []}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if not text:
            continue

        # PDF link
        if href.lower().endswith(".pdf"):
            # href may be relative like "2026\\BARN__FÖRSKOLA\\..."
            results["pdfs"].append({"name": text, "url": href.replace("\\", "/")})
            continue

        # Folder link
        m = re.search(r"ListEnkater\.aspx\?kat=(.+)", href)
        if m:
            kat = urllib.parse.unquote(m.group(1))
            results["folders"].append({"name": text, "kat": kat})

    return results


def list_areas(year: int = 2026) -> list[dict]:
    """List all areas under a given year for BARN__FÖRSKOLA."""
    kat = f"{year}\\BARN__FÖRSKOLA"
    soup = fetch_soup(f"ListEnkater.aspx?kat={urllib.parse.quote(kat)}")
    data = parse_list_page(soup, kat)
    return [f for f in data["folders"] if not f["name"].startswith((">>", "-"))]


def list_preschools(area_kat: str) -> list[dict]:
    """List all preschools (and sub-units) under an area."""
    soup = fetch_soup(f"ListEnkater.aspx?kat={urllib.parse.quote(area_kat)}")
    data = parse_list_page(soup, area_kat)
    return data["folders"]


def list_pdfs_and_subunits(preschool_kat: str) -> dict:
    """Get PDFs and sub-units for a preschool page."""
    soup = fetch_soup(f"ListEnkater.aspx?kat={urllib.parse.quote(preschool_kat)}")
    return parse_list_page(soup, preschool_kat)


def crawl(year: int = 2026, areas: list[str] | None = None):
    """
    Generator yielding discovered PDF entries.
    Each entry: {
        year, area, preschool, sub_unit (or None),
        pdf_name, pdf_url, kat
    }
    """
    all_areas = list_areas(year)
    for area in all_areas:
        area_name = area["name"]
        if areas and area_name not in areas:
            continue

        preschools = list_preschools(area["kat"])
        for pre in preschools:
            pre_name = pre["name"]
            if pre_name.startswith(">>") or pre_name.startswith("-"):
                continue
            page_data = list_pdfs_and_subunits(pre["kat"])

            # Direct PDFs on this page
            for pdf in page_data["pdfs"]:
                yield {
                    "year": year,
                    "area": area_name,
                    "preschool": pre_name,
                    "sub_unit": None,
                    "pdf_name": pdf["name"],
                    "pdf_url": f"{BASE_URL}/{pdf['url']}",
                    "kat": pre["kat"],
                }

            # Sub-units (skip self-reference folders like ">> Preschool Name")
            for sub in page_data["folders"]:
                sub_name = sub["name"]
                if sub_name.startswith(">>"):
                    continue
                sub_page = list_pdfs_and_subunits(sub["kat"])
                for pdf in sub_page["pdfs"]:
                    yield {
                        "year": year,
                        "area": area_name,
                        "preschool": pre_name,
                        "sub_unit": sub_name,
                        "pdf_name": pdf["name"],
                        "pdf_url": f"{BASE_URL}/{pdf['url']}",
                        "kat": sub["kat"],
                    }


if __name__ == "__main__":
    for item in crawl(2026, areas=["Sydväst 1"]):
        print(item)
