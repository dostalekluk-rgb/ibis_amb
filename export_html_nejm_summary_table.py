import sqlite3
import pandas as pd

DB_FILE = "validator_data.db"
KODY_FILE = "kody.xlsx"
OUTPUT_HTML = "summary_table_nejm.html"

def generate_nejm_html_table():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    df_kody = pd.read_excel(KODY_FILE)
    points_map = {}
    name_map = {}
    for _, r in df_kody.iterrows():
        c = str(r["Kód"]).strip().zfill(5)
        try:
            pts = float(r["Bodová hodnota celkem"]) if pd.notna(r["Bodová hodnota celkem"]) else 0.0
        except Exception:
            pts = 0.0
        points_map[c] = pts
        name_map[c] = str(r["Název výkonu"]) if pd.notna(r["Název výkonu"]) else ""

    cursor.execute("""
    SELECT code, COUNT(*) as cnt 
    FROM reviews 
    WHERE type = 'ADDITION'
    GROUP BY code 
    """)
    rows = cursor.fetchall()
    conn.close()

    table_data = []
    total_pts_all = 0.0
    total_cnt_all = 0

    for r in rows:
        code = r["code"]
        cnt = r["cnt"]
        name = name_map.get(code, "Výkon")
        pts_item = points_map.get(code, 0.0)
        tot_pts = cnt * pts_item
        
        total_cnt_all += cnt
        total_pts_all += tot_pts
        
        table_data.append({
            "code": code,
            "name": name,
            "count": cnt,
            "pts_item": pts_item,
            "tot_pts": tot_pts
        })

    # Sort by total points descending
    table_data.sort(key=lambda x: x["tot_pts"], reverse=True)

    rows_html = ""
    for idx, d in enumerate(table_data, 1):
        pct = (d["tot_pts"] / total_pts_all * 100) if total_pts_all > 0 else 0
        rows_html += f"""
        <tr>
          <td style="text-align:center; font-weight:bold;">{idx}</td>
          <td style="text-align:center; font-family:'Merriweather', serif; font-weight:bold; color:#7A0016;">{d['code']}</td>
          <td style="font-weight:600; color:#1A1A1A;">{d['name']}</td>
          <td style="text-align:right; font-weight:bold;">{d['count']:,}×</td>
          <td style="text-align:right; color:#4A4A4A;">{d['pts_item']:,.0f} b.</td>
          <td style="text-align:right; font-weight:bold; color:#1B5E20;">+{d['tot_pts']:,.0f} bodů</td>
          <td style="text-align:right; font-size:0.85rem; color:#717171;">{pct:.1f} %</td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <title>VFN Přehled Nevykázaných Výkonů | NEJM Style Report</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Merriweather:ital,wght@0,300;0,400;0,700;1,300&family=Source+Sans+3:wght@400;600;700&display=swap');
    
    body {{
      background-color: #FAF8F5;
      color: #1A1A1A;
      font-family: 'Source Sans 3', system-ui, sans-serif;
      padding: 40px;
      margin: 0;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
      background: #FFFFFF;
      border-top: 4px solid #7A0016;
      border-bottom: 2px solid #B5AD9C;
      box-shadow: 0 4px 16px rgba(0,0,0,0.08);
      padding: 36px 44px;
      border-radius: 4px;
    }}
    .nejm-masthead {{
      border-bottom: 2px solid #7A0016;
      padding-bottom: 16px;
      margin-bottom: 24px;
    }}
    .journal-title {{
      font-family: 'Merriweather', serif;
      font-size: 1.6rem;
      font-weight: 700;
      color: #7A0016;
      letter-spacing: -0.5px;
      text-transform: uppercase;
    }}
    .journal-subtitle {{
      font-size: 0.88rem;
      color: #4A4A4A;
      font-weight: 600;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      margin-top: 4px;
    }}
    .summary-cards {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 18px;
      margin-bottom: 28px;
    }}
    .card {{
      background: #FAF8F5;
      border: 1px solid #D8D2C2;
      border-radius: 4px;
      padding: 16px 20px;
    }}
    .card-label {{
      font-size: 0.78rem;
      font-weight: 700;
      color: #717171;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .card-val {{
      font-family: 'Merriweather', serif;
      font-size: 1.45rem;
      font-weight: 700;
      color: #7A0016;
      margin-top: 4px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.92rem;
      margin-top: 10px;
    }}
    th {{
      background-color: #F4F1EA;
      color: #1A1A1A;
      font-family: 'Source Sans 3', sans-serif;
      font-weight: 700;
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 12px 14px;
      border-bottom: 2px solid #7A0016;
    }}
    td {{
      padding: 12px 14px;
      border-bottom: 1px solid #E8E3D9;
    }}
    tr:hover {{
      background-color: #FAF4EB;
    }}
    .total-row {{
      background-color: #F0EDE6;
      font-weight: bold;
    }}
    .total-row td {{
      border-top: 2px solid #7A0016;
      border-bottom: 2px solid #7A0016;
      font-size: 1.05rem;
      padding: 16px 14px;
    }}
    .footer-note {{
      margin-top: 24px;
      font-size: 0.82rem;
      color: #717171;
      border-top: 1px solid #D8D2C2;
      padding-top: 12px;
      display: flex;
      justify-content: space-between;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="nejm-masthead">
      <div class="journal-title">VFN Clinical Coding Journal</div>
      <div class="journal-subtitle">Souhrnná analýza podvykázaných výkonů • Datová sada 21 468 lékařských zpráv</div>
    </div>

    <div class="summary-cards">
      <div class="card">
        <div class="card-label">Analyzováno zpráv</div>
        <div class="card-val">21 468</div>
      </div>
      <div class="card">
        <div class="card-label">Celkem doplnění (+)</div>
        <div class="card-val" style="color:#1B5E20">{total_cnt_all:,}×</div>
      </div>
      <div class="card">
        <div class="card-label">Celkový bodový zisk VFN</div>
        <div class="card-val" style="color:#1B5E20">+{total_pts_all:,.0f} b.</div>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th style="width:40px; text-align:center;">#</th>
          <th style="width:90px; text-align:center;">Kód</th>
          <th>Název výkonu (ÚZIS)</th>
          <th style="width:130px; text-align:right;">Počet doplnění</th>
          <th style="width:130px; text-align:right;">Body / 1 výkon</th>
          <th style="width:170px; text-align:right;">Bodový zisk pro VFN</th>
          <th style="width:80px; text-align:right;">Podíl</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
        <tr class="total-row">
          <td colspan="3">CELKEM PRO VŠECHNY IDENTIFIKOVANÉ VÝKONY</td>
          <td style="text-align:right; font-weight:bold;">{total_cnt_all:,}×</td>
          <td style="text-align:right;">—</td>
          <td style="text-align:right; color:#1B5E20; font-weight:bold;">+{total_pts_all:,.0f} bodů</td>
          <td style="text-align:right;">100.0 %</td>
        </tr>
      </tbody>
    </table>

    <div class="footer-note">
      <span>Zdroj dat: VFN Ambulantní zprávy (ambu_anonymized.xlsx) & Katalog ÚZIS (kody.xlsx)</span>
      <span>Generováno: Google Vertex AI Model ibis_amb & Explicit Rules</span>
    </div>
  </div>
</body>
</html>
"""
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"Successfully generated NEJM HTML summary table: '{OUTPUT_HTML}'")

if __name__ == "__main__":
    generate_nejm_html_table()
