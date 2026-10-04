import sqlite3
import pandas as pd

DB_FILE = "validator_data.db"
KODY_FILE = "kody.xlsx"

def generate_table():
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
    ORDER BY (cnt * 1.0) DESC
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

    print("| Kód výkonu | Název výkonu | Počet doplnění | Body za 1 výkon | Celkový bodový zisk pro VFN |")
    print("| :---: | :--- | :---: | :---: | :---: |")
    for d in table_data:
        print(f"| **{d['code']}** | {d['name']} | **{d['count']:,}×** | {d['pts_item']:,.0f} b. | **+{d['tot_pts']:,.0f} bodů** |")
    print(f"| **CELKEM** | **Všechny navržené výkony** | **{total_cnt_all:,}×** | - | **+{total_pts_all:,.0f} bodů** |")

if __name__ == "__main__":
    generate_table()
