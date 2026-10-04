import json
import sqlite3
import pandas as pd
import random
import os

DB_FILE = "validator_data.db"
KODY_FILE = "kody.xlsx"
USTAVA_FILE = "ustava.txt"

TRAIN_OUTPUT = "vertex_train_dataset.jsonl"
VAL_OUTPUT = "vertex_val_dataset.jsonl"
EXT_VAL_GOLD = "external_validation_gold.json"

# Set fixed seed for reproducible random split
random.seed(42)

def build_datasets():
    print("Loading catalog and system instructions...")
    # Load system instruction from ustava.txt
    system_instruction_text = ""
    if os.path.exists(USTAVA_FILE):
        with open(USTAVA_FILE, "r", encoding="utf-8") as f:
            system_instruction_text = f.read().strip()
            
    system_instruction_obj = {
        "parts": [{"text": system_instruction_text}]
    }
    
    # Load code catalog for names
    name_map = {}
    if os.path.exists(KODY_FILE):
        df_kody = pd.read_excel(KODY_FILE)
        for _, r in df_kody.iterrows():
            c = str(r["Kód"]).strip().zfill(5)
            name_map[c] = str(r["Název výkonu"]) if pd.notna(r["Název výkonu"]) else "Výkon"

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch all validated reports (reports with decisions)
    cursor.execute("""
    SELECT DISTINCT r.* 
    FROM reports r
    JOIN decisions d ON r.id = d.report_id
    """)
    reports = [dict(r) for r in cursor.fetchall()]
    
    print(f"Total human-validated reports found: {len(reports)}")
    print("Using 100% of human-validated reports for Vertex AI Fine-Tuning!")
    
    train_reports = reports
    
    def format_entry(report):
        report_id = report["id"]
        text_str = report["text"]
        date_str = report["date_str"]
        time_str = report["time_str"]
        codes_raw = report["codes_raw"]
        
        # 1. Fetch user decisions for additions (ACCEPT vs REJECT_PAST vs REJECT)
        cursor.execute("""
        SELECT rev.*, d.action
        FROM decisions d
        JOIN reviews rev ON d.review_id = rev.id
        WHERE d.report_id = ?
        """, (report_id,))
        dec_rows = [dict(r) for r in cursor.fetchall()]
        
        additions_to_add = []
        seen_additions = set()
        for dr in dec_rows:
            if dr["type"] == "ADDITION" and dr["action"] == "ACCEPT":
                c = dr["code"]
                if c not in seen_additions:
                    seen_additions.add(c)
                    additions_to_add.append({
                        "code": c,
                        "name": dr["code_name"] or name_map.get(c, "Výkon"),
                        "verbatim_quote": dr["exact_text_snippet"] or "",
                        "reason": dr["reason"] or "V textu popsán dnes provedený výkon"
                    })
                
        # 2. Fetch user decisions for removals (ACCEPT)
        removals_to_remove = []
        seen_removals = set()
        for dr in dec_rows:
            if dr["type"] == "REMOVAL" and dr["action"] == "ACCEPT":
                c = dr["code"]
                if c not in seen_removals:
                    seen_removals.add(c)
                    removals_to_remove.append({
                        "code": c,
                        "name": dr["code_name"] or name_map.get(c, "Výkon"),
                        "reason": dr["reason"] or "zcela_chybi_zminka"
                    })
                
        user_prompt = f"""Analýza lékařské zprávy pro vykazování výkonů VFN.
Datum vyšetření: {date_str or 'Neuvedeno'}
Čas vyšetření: {time_str or 'Neuvedeno'}
Původně vykázané kódy v IS: {codes_raw or 'Žádné'}

Lékařská zpráva:
{text_str}"""

        has_changes = bool(additions_to_add or removals_to_remove)
        
        target_payload = {
            "doporučení_k_odebrání": removals_to_remove,
            "doporučení_k_doplnění": additions_to_add,
            "celkovy_stav": "OPRAVENO" if has_changes else "BEZ_ZMENY"
        }
        
        entry = {
            "systemInstruction": system_instruction_obj,
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                },
                {
                    "role": "model",
                    "parts": [{"text": json.dumps(target_payload, ensure_ascii=False, indent=2)}]
                }
            ]
        }
        return entry, target_payload

    # Build train JSONL with 100% of validated reports
    train_entries = []
    for r in train_reports:
        entry, _ = format_entry(r)
        train_entries.append(entry)
        
    with open(TRAIN_OUTPUT, "w", encoding="utf-8") as f:
        for entry in train_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
    conn.close()
    
    print("\nDataset generation completed successfully!")
    print(f"[OK] 100% Training dataset for Vertex AI: '{TRAIN_OUTPUT}' ({len(train_entries)} examples)")

if __name__ == "__main__":
    build_datasets()
