#!/usr/bin/env python3
"""
Deterministic PDF extractor using pdfplumber.
Extracts structured tables and metadata from preschool survey PDFs.
"""

import re
import io
import requests
import pdfplumber


def fetch_pdf(url: str) -> pdfplumber.PDF:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return pdfplumber.open(io.BytesIO(resp.content))


def extract_footer_info(page) -> dict:
    """Extract preschool name and response rate from page footer text."""
    text = page.extract_text() or ""
    # Footer pattern: "Preschool Name | Svarsfrekvens XX%"
    m = re.search(r"(.+?)\s*\|\s*Svarsfrekvens\s+(\d+)%", text)
    if m:
        return {"name": m.group(1).strip(), "response_rate": int(m.group(2))}
    return {}


def find_table_page(pdf: pdfplumber.PDF, keyword: str) -> int | None:
    """Return page index containing a specific keyword in its text."""
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if keyword in text:
            return i
    return None


def _normalize_header(header: str, footer_name: str, area_name: str | None = None) -> str:
    """Replace the preschool-specific header with the clean footer name."""
    h = header.replace("\n", " ").strip()
    if h in ("GR", "Göteborg", area_name or ""):
        return h
    if re.match(r"^\d{4}$", h):
        return h
    # If it looks like the preschool name (contains parts of footer name), normalize
    if footer_name and any(part in h for part in footer_name.split() if len(part) > 3):
        return footer_name
    return h


def extract_overall_score(pdf: pdfplumber.PDF, footer_name: str = "", area_name: str = "") -> dict | None:
    """
    Extract the 'Helhetsomdöme' comparison table.
    Returns a dict mapping column names to the score for 'Jag är nöjd...'.
    """
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if "Jag är nöjd med mitt barns" not in text or "Årsjämförelsen gäller" not in text:
            continue
        tables = page.extract_tables()
        for table in tables:
            if not table or len(table) < 2:
                continue
            headers = table[0]
            header_str = " ".join(str(h) for h in headers if h)
            if "GR" not in header_str or "Göteborg" not in header_str:
                continue
            for row in table[1:]:
                first_cell = (row[0] or "").strip()
                if "Jag är nöjd" in first_cell:
                    result = {"question": row[0].replace("\n", " ").strip()}
                    for h, v in zip(headers[1:], row[1:]):
                        if h and v:
                            clean_h = _normalize_header(h.replace("\n", " ").strip(), footer_name, area_name)
                            clean_v = v.replace("\n", " ").strip()
                            result[clean_h] = clean_v
                    return result
    return None


def extract_category_scores(pdf: pdfplumber.PDF, footer_name: str = "", area_name: str = "") -> list[dict]:
    """
    Extract category average tables (e.g., Normer och värden).
    Returns list of dicts with category, headers, and values.
    """
    scores = []
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if "Årsjämförelsen gäller" not in text:
            continue
        tables = page.extract_tables()
        for table in tables:
            if not table or len(table) < 2:
                continue
            headers = table[0]
            header_str = " ".join(str(h) for h in headers if h)
            if "GR" not in header_str or "Göteborg" not in header_str:
                continue
            category = None
            for cat in [
                "Normer och värden",
                "Värdegrund och uppdrag",
                "Omsorg, utveckling och lärande",
                "Barns inflytande och delaktighet",
                "Förskola och hem",
                "Helhetsomdöme",
            ]:
                if cat in text:
                    category = cat
                    break
            if not category:
                category = "Unknown"

            for row in table[1:]:
                if not row or not row[0]:
                    continue
                question = row[0].replace("\n", " ").strip()
                result = {"category": category, "question": question, "values": {}}
                for h, v in zip(headers, row):
                    if h and v:
                        clean_h = _normalize_header(h.replace("\n", " ").strip(), footer_name, area_name)
                        clean_v = v.replace("\n", " ").strip()
                        result["values"][clean_h] = clean_v
                scores.append(result)
    return scores


def extract_survey(pdf_url: str, preschool_name: str = "", area_name: str = "") -> dict:
    """
    Main extraction function.
    Returns a dict with:
    - response_rate
    - overall_score (dict of headers->values for satisfaction question)
    - category_scores (list)
    - raw_footer_name
    """
    pdf = fetch_pdf(pdf_url)
    try:
        footer = {}
        for page in pdf.pages:
            f = extract_footer_info(page)
            if f:
                footer = f
                break

        # Use crawler-provided name as canonical if available, else footer
        canonical_name = preschool_name or footer.get("name", "")
        overall = extract_overall_score(pdf, footer_name=canonical_name, area_name=area_name)
        categories = extract_category_scores(pdf, footer_name=canonical_name, area_name=area_name)

        return {
            "pdf_url": pdf_url,
            "response_rate": footer.get("response_rate"),
            "footer_name": footer.get("name"),
            "overall_score": overall,
            "category_scores": categories,
        }
    finally:
        pdf.close()


if __name__ == "__main__":
    url = "https://enkater.goteborg.se/2026/BARN__F%C3%96RSKOLA/Sydv%C3%A4st%201/Askims%20Domarringsv%C3%A4g%20103%20f%C3%B6rskola/Askims%20Domarringsv%C3%A4g%20103%20f%C3%B6rskol.pdf"
    data = extract_survey(url)
    import json
    print(json.dumps(data, indent=2, ensure_ascii=False))
