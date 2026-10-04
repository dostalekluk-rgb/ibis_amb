import json
import os
import sqlite3

DB_FILE = "validator_data.db"
USTAVA_FILE = "ustava.txt"
OUTPUT_JSONL = "vertex_batch_21k.jsonl"

def main():
    if not os.path.exists(DB_FILE):
        print(f"Error: {DB_FILE} not found.")
        return

    if not os.path.exists(USTAVA_FILE):
        print(f"Error: {USTAVA_FILE} not found.")
        return

    with open(USTAVA_FILE, "r", encoding="utf-8") as f:
        system_instruction_text = f.read().strip()

    system_instruction_obj = {
        "parts": [{"text": system_instruction_text}]
    }

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT id, row_idx, codes_raw, date_str, time_str, text FROM reports ORDER BY id ASC")
    reports = c.fetchall()
    conn.close()

    total_rows = len(reports)
    print(f"Loaded {total_rows:,} reports from database '{DB_FILE}'...")

    written_count = 0
    skipped_count = 0

    print(f"Generating Vertex AI Batch Prediction file '{OUTPUT_JSONL}'...")
    
    with open(OUTPUT_JSONL, "w", encoding="utf-8") as f_out:
        for rep in reports:
            rep_id = rep["id"]
            text_val = rep["text"]
            codes_val = rep["codes_raw"]
            date_val = rep["date_str"]
            time_val = rep["time_str"]

            if not text_val or not str(text_val).strip():
                skipped_count += 1
                continue

            text_str = str(text_val).strip()
            codes_str = str(codes_val).strip() if codes_val and str(codes_val).strip() and str(codes_val).strip() != "nan" else "Žádné"
            date_str = str(date_val).strip() if date_val and str(date_val).strip() and str(date_val).strip() != "nan" else "Neuvedeno"
            time_str = str(time_val).strip() if time_val and str(time_val).strip() and str(time_val).strip() != "nan" else "Neuvedeno"

            user_prompt = f"""Analýza lékařské zprávy pro vykazování výkonů VFN.
Datum vyšetření: {date_str}
Čas vyšetření: {time_str}
Původně vykázané kódy v IS: {codes_str}

Lékařská zpráva:
{text_str}"""

            req_item = {
                "custom_id": f"report_{rep_id}",
                "request": {
                    "systemInstruction": system_instruction_obj,
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": user_prompt}]
                        }
                    ],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }
            }

            f_out.write(json.dumps(req_item, ensure_ascii=False) + "\n")
            written_count += 1

            if written_count % 5000 == 0:
                print(f"  Vygenerováno {written_count:,} / {total_rows:,} zpráv...")

    file_size_mb = os.path.getsize(OUTPUT_JSONL) / (1024 * 1024)
    print("\n" + "=" * 65)
    print("SUCCESSFULLY GENERATED FULL VERTEX BATCH DATASET!")
    print("=" * 65)
    print(f"  • Výstupní soubor: {OUTPUT_JSONL}")
    print(f"  • Celkem platných zpráv k auditu: {written_count:,}")
    print(f"  • Přeskočené prázdné zprávy: {skipped_count}")
    print(f"  • Velikost souboru: {file_size_mb:.2f} MB")
    print("=" * 65)

if __name__ == "__main__":
    main()
