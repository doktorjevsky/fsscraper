#!/usr/bin/env python3
"""Export main preschool data to a single self-contained HTML map."""
import json
import sqlite3

DB_PATH = "surveys.db"
OUTPUT_PATH = "docs/preschool_map_2026.html"

# Order categories as they appear in the PDF summary
CATEGORY_ORDER = [
    "Helhetsomdöme",
    "Normer och värden",
    "Värdegrund och uppdrag",
    "Omsorg, utveckling och lärande",
    "Barns inflytande och delaktighet",
    "Förskola och hem",
]


def get_color(score):
    """Return a colorblind-friendly color based on score value."""
    if score is None:
        return "#9ca3af"
    try:
        val = float(score)
    except (ValueError, TypeError):
        return "#9ca3af"
    if val >= 4.5:
        return "#16a34a"  # green
    elif val >= 4.0:
        return "#2563eb"  # blue
    elif val >= 3.5:
        return "#eab308"  # bright yellow
    else:
        return "#dc2626"  # red


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Fetch main preschools
    cur = conn.cursor()
    cur.execute("""
        SELECT
            s.id,
            s.year,
            s.area,
            s.preschool AS name,
            s.response_rate,
            s.pdf_url,
            a.lat,
            a.lng
        FROM surveys s
        JOIN addresses a ON s.preschool = a.raw_name
        WHERE s.sub_unit IS NULL
            AND a.lat IS NOT NULL
            AND a.lng IS NOT NULL
        ORDER BY s.area, s.preschool
    """)
    rows = cur.fetchall()

    # Fetch category means for each survey
    cur.execute("""
        SELECT
            survey_id,
            category,
            ROUND(AVG(CAST(value AS REAL)), 2) as mean
        FROM scores
        WHERE column_name = '_self'
            AND value GLOB '*[0-9]*'
        GROUP BY survey_id, category
    """)
    score_rows = cur.fetchall()
    conn.close()

    # Build score lookup: {survey_id: {category: mean}}
    scores_by_survey = {}
    for r in score_rows:
        sid = r["survey_id"]
        cat = r["category"]
        mean = r["mean"]
        if sid not in scores_by_survey:
            scores_by_survey[sid] = {}
        scores_by_survey[sid][cat] = mean

    features = []
    for row in rows:
        sid = row["id"]
        category_scores = scores_by_survey.get(sid, {})

        # Build ordered scores dict
        ordered_scores = {}
        for cat in CATEGORY_ORDER:
            ordered_scores[cat] = category_scores.get(cat)

        # Overall score for dot coloring
        overall = category_scores.get("Helhetsomdöme")

        features.append({
            "name": row["name"],
            "area": row["area"],
            "year": row["year"],
            "response_rate": row["response_rate"],
            "pdf_url": row["pdf_url"],
            "lat": row["lat"],
            "lng": row["lng"],
            "overall": overall,
            "color": get_color(overall),
            "scores": ordered_scores,
        })

    data_json = json.dumps(features, ensure_ascii=False, indent=2)

    html = f'''<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Förskolekollen Göteborg</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f3f4f6; }}
  #map {{ height: 100vh; width: 100vw; }}
  .leaflet-popup-content-wrapper {{
    border-radius: 12px;
    padding: 0;
    overflow: hidden;
    box-shadow: 0 10px 25px rgba(0,0,0,0.15);
    font-family: inherit;
  }}
  .leaflet-popup-content {{
    margin: 0;
    width: 300px !important;
  }}
  .popup-card {{
    padding: 16px;
  }}
  .popup-area {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #6b7280;
    margin-bottom: 6px;
  }}
  .popup-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 14px;
    gap: 10px;
  }}
  .popup-title {{
    font-size: 15px;
    font-weight: 700;
    color: #111827;
    line-height: 1.3;
    flex: 1;
  }}
  .popup-score-badge {{
    font-size: 16px;
    font-weight: 800;
    padding: 4px 10px;
    border-radius: 20px;
    color: white;
    white-space: nowrap;
  }}
  .popup-meta {{
    display: flex;
    gap: 16px;
    margin-bottom: 14px;
    padding-bottom: 12px;
    border-bottom: 1px solid #e5e7eb;
  }}
  .popup-meta-item {{
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}
  .popup-meta-label {{
    font-size: 11px;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}
  .popup-meta-value {{
    font-size: 13px;
    font-weight: 600;
    color: #111827;
  }}
  .popup-scores-title {{
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #6b7280;
    margin-bottom: 8px;
  }}
  .popup-score-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 0;
    border-bottom: 1px solid #f3f4f6;
    font-size: 13px;
  }}
  .popup-score-row:last-child {{
    border-bottom: none;
  }}
  .popup-score-name {{
    color: #374151;
    line-height: 1.3;
    flex: 1;
    padding-right: 8px;
  }}
  .popup-score-value {{
    font-weight: 700;
    font-size: 13px;
    color: #111827;
    min-width: 32px;
    text-align: right;
  }}
  .popup-hint {{
    margin-top: 12px;
    font-size: 11px;
    color: #6b7280;
    font-style: italic;
  }}
  #legend {{
    position: absolute;
    bottom: 24px;
    right: 24px;
    z-index: 1000;
    background: white;
    padding: 14px 18px;
    border-radius: 12px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    font-size: 13px;
  }}
  #legend h4 {{
    margin-bottom: 10px;
    font-size: 14px;
    color: #111827;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }}
  .legend-dot {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 2px solid white;
    box-shadow: 0 0 0 1px rgba(0,0,0,0.1);
  }}
  .legend-label {{ color: #4b5563; }}
</style>
</head>
<body>

<div id="map"></div>

<div id="legend">
  <h4>Omdöme</h4>
  <div class="legend-item"><div class="legend-dot" style="background:#16a34a"></div><span class="legend-label">Utmärkt (4.5+)</span></div>
  <div class="legend-item"><div class="legend-dot" style="background:#2563eb"></div><span class="legend-label">Bra (4.0–4.5)</span></div>
  <div class="legend-item"><div class="legend-dot" style="background:#eab308"></div><span class="legend-label">Godkänt (3.5–4.0)</span></div>
  <div class="legend-item"><div class="legend-dot" style="background:#dc2626"></div><span class="legend-label">Underkänt (&lt;3.5)</span></div>
  <div class="legend-item"><div class="legend-dot" style="background:#9ca3af"></div><span class="legend-label">Ingen data</span></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
  integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
const data = {data_json};

const map = L.map('map').setView([57.7, 11.97], 11);

L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, &copy; <a href="https://carto.com/attributions">CARTO</a>',
  subdomains: 'abcd',
  maxZoom: 19
}}).addTo(map);

const markers = [];

function formatScore(val) {{
  if (val === null || val === undefined) return '—';
  return parseFloat(val).toFixed(2);
}}

function scoreColor(val) {{
  if (val === null || val === undefined) return '#9ca3af';
  const v = parseFloat(val);
  if (v >= 4.5) return '#16a34a';
  if (v >= 4.0) return '#2563eb';
  if (v >= 3.5) return '#eab308';
  return '#dc2626';
}}

for (const p of data) {{
  const overallText = formatScore(p.overall);
  const overallBg = p.color;

  let scoresHtml = '';
  for (const [cat, val] of Object.entries(p.scores)) {{
    if (cat === 'Helhetsomdöme') continue; // shown separately
    const valText = formatScore(val);
    const valColor = scoreColor(val);
    scoresHtml += `
      <div class="popup-score-row">
        <span class="popup-score-name">${{cat}}</span>
        <span class="popup-score-value" style="color:${{valColor}}">${{valText}}</span>
      </div>
    `;
  }}

  const popupContent = `
    <div class="popup-card">
      <div class="popup-area">${{p.area}}</div>
      <div class="popup-header">
        <div class="popup-title">${{p.name}}</div>
        <div class="popup-score-badge" style="background:${{overallBg}}">${{overallText}}</div>
      </div>
      <div class="popup-meta">
        <div class="popup-meta-item">
          <span class="popup-meta-label">År</span>
          <span class="popup-meta-value">${{p.year}}</span>
        </div>
        <div class="popup-meta-item">
          <span class="popup-meta-label">Svarsfrekvens</span>
          <span class="popup-meta-value">${{p.response_rate !== null ? p.response_rate + '%' : '—'}}</span>
        </div>
      </div>
      <div class="popup-scores-title">Omdömen per område</div>
      ${{scoresHtml}}
      <div class="popup-hint">Klicka på pricken för att öppna enkäten (PDF)</div>
    </div>
  `;

  const popup = L.popup({{
    closeButton: false,
    offset: [0, -6],
    className: 'preschool-popup'
  }}).setContent(popupContent);

  const circle = L.circleMarker([p.lat, p.lng], {{
    radius: 8,
    fillColor: p.color,
    color: "#fff",
    weight: 2,
    opacity: 1,
    fillOpacity: 0.9
  }}).addTo(map);

  circle.on('mouseover', function () {{
    popup.setLatLng(this.getLatLng()).openOn(map);
  }});

  circle.on('mouseout', function () {{
    map.closePopup(popup);
  }});

  circle.on('click', function () {{
    window.open(p.pdf_url, '_blank', 'noopener,noreferrer');
  }});

  markers.push(circle);
}}

if (markers.length > 0) {{
  const group = new L.featureGroup(markers);
  map.fitBounds(group.getBounds().pad(0.1));
}}
</script>

</body>
</html>
'''

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {OUTPUT_PATH} with {len(features)} preschools.")


if __name__ == "__main__":
    main()
