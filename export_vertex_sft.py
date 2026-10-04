import json
import sqlite3
import pandas as pd

DB_FILE = "validator_data.db"
OUTPUT_FILE = "vertex_sft_dataset.jsonl"

def export_vertex_sft(validated_only: bool = False):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if validated_only:
        cursor.execute("SELECT * FROM reports WHERE status = 'VALIDATED'")
    else:
        # Include validated reports + reports with clean review suggestions
        cursor.execute("""
        SELECT DISTINCT r.* 
        FROM reports r
        JOIN reviews rev ON r.id = rev.report_id
        """)
        
    reports = cursor.fetchall()
    
    sft_records = []
    
    for r in reports:
        report_id = r["id"]
        row_idx = r["row_idx"]
        text_str = r["text"]
        date_str = r["date_str"]
        time_str = r["time_str"]
        codes_raw = r["codes_raw"]
        
        # Fetch reviews and decisions for this report
        cursor.execute("SELECT * FROM reviews WHERE report_id = ?", (report_id,))
        reviews = [dict(rev) for rev in cursor.fetchall()]
        
        cursor.execute("SELECT * FROM decisions WHERE report_id = ?", (report_id,))
        decisions = [dict(d) for d in cursor.fetchall()]
        
        # Determine accepted additions and non-removed existing codes
        additions = []
        removals = []
        
        for rev in reviews:
            rev_id = rev["id"]
            code = rev["code"]
            rev_type = rev["type"]
            
            # Check doctor decision if available
            dec = next((d for d in decisions if d["review_id"] == rev_id), None)
            
            if dec:
                action = dec["action"] # ACCEPT or REJECT
                if rev_type == "ADDITION" and action == "ACCEPT":
                    additions.append({"code": code, "name": rev["code_name"], "reason": rev["reason"]})
                elif rev_type == "REMOVAL" and action == "ACCEPT":
                    removals.append({"code": code, "name": rev["code_name"], "reason": rev["reason"]})
            else:
                # Default suggestion
                if rev_type == "ADDITION":
                    additions.append({"code": code, "name": rev["code_name"], "reason": rev["reason"]})
                elif rev_type == "REMOVAL":
                    removals.append({"code": code, "name": rev["code_name"], "reason": rev["reason"]})

        user_prompt = f"""Analýza lékařské zprávy pro vykazování výkonů VFN.
Datum vyšetření: {date_str or 'Neuvedeno'}
Čas vyšetření: {time_str or 'Neuvedeno'}
Původně vykázané kódy v IS: {codes_raw or 'Žádné'}

Lékařská zpráva:
{text_str}"""

        response_payload = {
            "doporučení_k_doplnění": additions,
            "doporučení_k_odebrání": removals,
            "celkovy_stav": "OPRAVENO" if (additions or removals) else "BEZ_ZMENY"
        }
        
        sft_entry = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                },
                {
                    "role": "model",
                    "parts": [{"text": json.dumps(response_payload, ensure_ascii=False, indent=2)}]
                }
            ]
        }
        sft_records.append(sft_entry)
        
    conn.close()
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for entry in sft_records:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
    print(f"Successfully exported {len(sft_records)} SFT training examples to '{OUTPUT_FILE}'.")
    return len(sft_records)

if __name__ == "__main__":
    export_vertex_sft(validated_only=False)
