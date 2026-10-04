import sqlite3
import pandas as pd

DB_FILE = "validator_data.db"
KODY_FILE = "kody.xlsx"

def run_full_statistics():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Load point values from kody.xlsx
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

    cursor.execute("SELECT COUNT(*) FROM reports")
    total_reports = cursor.fetchone()[0]

    cursor.execute("""
    SELECT code, type, COUNT(*) as cnt 
    FROM reviews 
    GROUP BY code, type
    ORDER BY cnt DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    additions = []
    removals = []
    total_add_count = 0
    total_rem_count = 0
    total_points_gained = 0.0

    for r in rows:
        code = r["code"]
        rev_type = r["type"]
        cnt = r["cnt"]
        pts_per_item = points_map.get(code, 0.0)
        c_name = name_map.get(code, "Výkon")

        if rev_type == "ADDITION":
            total_add_count += cnt
            gained = cnt * pts_per_item
            total_points_gained += gained
            additions.append({
                "code": code,
                "name": c_name,
                "count": cnt,
                "points_per_item": pts_per_item,
                "total_points": gained
            })
        elif rev_type == "REMOVAL":
            total_rem_count += cnt
            removals.append({
                "code": code,
                "name": c_name,
                "count": cnt,
                "points_per_item": pts_per_item
            })

    print("=================================================================")
    print(" VFN MEDICAL CODING - CELKOVÁ ANALÝZA 19 000+ LÉKAŘSKÝCH ZPRÁV")
    print("=================================================================")
    print(f" Analyzováno zpráv celkem:          {total_reports:,}")
    print(f" Celkem navržených DOPLNĚNÍ (+):     {total_add_count:,}")
    print(f" Celkem navržených ODEBRÁNÍ (-):     {total_rem_count:,}")
    print(f" CELKOVÝ BODOVÝ ZISK PRO VFN:       {total_points_gained:,.0f} bodů")
    print("-----------------------------------------------------------------")
    print(" TOP 10 NAVRŽENÝCH KÓDŮ K DOPLNĚNÍ (PODVYKÁZÁNÍ):")
    for i, a in enumerate(additions[:10], 1):
        print(f"  {i:2d}. Kód {a['code']} ({a['name'][:35]}...): {a['count']:,}x | +{a['total_points']:,.0f} bodů")
    print("=================================================================")

if __name__ == "__main__":
    run_full_statistics()
