import json
import os
import sqlite3
import pandas as pd
import re
import html

DB_FILE = "validator_data.db"
KODY_FILE = "kody.xlsx"

# Load catalog
df_kody = pd.read_excel(KODY_FILE)
name_map = {}
for _, r in df_kody.iterrows():
    c = str(r["Kód"]).strip().zfill(5)
    name_map[c] = str(r["Název výkonu"]) if pd.notna(r["Název výkonu"]) else "Výkon"

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Map row_idx to report_id
cursor.execute("SELECT id, row_idx FROM reports")
row_idx_to_report_id = {r["row_idx"]: r["id"] for r in cursor.fetchall()}

batch_file = "batch_responses.jsonl"
if not os.path.exists(batch_file):
    print(f"Error: {batch_file} not found.")
    exit(1)

# Clean previous BILLED reviews to present clean batch results
cursor.execute("DELETE FROM reviews WHERE type = 'BILLED'")
conn.commit()

billed_found_count = 0
billed_missing_count = 0

with open(batch_file, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip(): continue
        resp_obj = json.loads(line)
        cid = resp_obj.get("custom_id", "")
        
        m = re.match(r"row_(\d+)", cid)
        if not m:
            continue
            
        row_idx = int(m.group(1))
        report_id = row_idx_to_report_id.get(row_idx)
        if not report_id:
            continue
            
        try:
            raw_text = resp_obj["response"]["candidates"][0]["content"]["parts"][0]["text"]
            clean_json = raw_text.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r"^```[a-z]*", "", clean_json)
                clean_json = re.sub(r"```$", "", clean_json).strip()
                
            eval_data = json.loads(clean_json)
            evals = eval_data.get("evaluations", [])
            
            for ev in evals:
                code = str(ev.get("code", "")).strip().zfill(5)
                status = ev.get("status")
                quote = ev.get("verbatim_quote") or ""
                reason = ev.get("unsupported_reason") or ""
                code_name = name_map.get(code, "Výkon")
                
                # We store BILLED codes evaluated by the batch
                if status is True and quote:
                    cursor.execute("""
                    INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason)
                    VALUES (?, 'BILLED', ?, ?, '⚡ Vertex AI (Gemini 3.8 Flash)', ?, ?)
                    """, (report_id, code, code_name, quote, reason or 'dokladovani_vykonu'))
                    billed_found_count += 1
                elif status is False:
                    cursor.execute("""
                    INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason)
                    VALUES (?, 'BILLED', ?, ?, '⚡ Vertex AI (Gemini 3.8 Flash)', ?, ?)
                    """, (report_id, code, code_name, quote or '', reason or 'vykon_nedolozen_v_textu'))
                    billed_missing_count += 1
        except Exception as e:
            pass

conn.commit()
conn.close()

print(f"Processed BILLED code evaluations from batch successfully!")
print(f"Loaded {billed_found_count} BILLED codes with text grounding quotes and {billed_missing_count} BILLED codes flagged missing/past.")
