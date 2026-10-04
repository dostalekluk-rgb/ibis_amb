import json
import os
import sqlite3
import subprocess
import requests
import re
import time
from temporal_rules import get_temporal_code_suggestions

DB_FILE = "validator_data.db"
USTAVA_FILE = "ustava.txt"
PROJECT_ID = "ibis-510508"
LOCATION = "europe-central2"
ENDPOINT_ID = "8311624009754083328"
BATCH_SIZE = 200

def get_auth_token():
    try:
        return subprocess.check_output("gcloud auth print-access-token", shell=True).decode().strip()
    except Exception as e:
        print(f"Error getting gcloud token: {e}")
        return None

def main():
    if not os.path.exists(DB_FILE):
        print(f"Error: {DB_FILE} not found.")
        return

    with open(USTAVA_FILE, "r", encoding="utf-8") as f:
        system_instruction_text = f.read().strip()

    system_instruction_obj = {
        "parts": [{"text": system_instruction_text}]
    }

    token = get_auth_token()
    if not token:
        print("Failed to acquire token.")
        return

    endpoint_url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/endpoints/{ENDPOINT_ID}:generateContent"

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Fetch 100 pending reports
    c.execute("SELECT id, row_idx, codes_raw, date_str, time_str, text FROM reports WHERE status = 'PENDING' LIMIT ?", (BATCH_SIZE,))
    pending_reports = c.fetchall()

    if not pending_reports:
        print("No pending reports found in DB.")
        return

    print(f"Loaded {len(pending_reports)} pending reports for Active Learning iteration...")
    print("=" * 65)

    processed_count = 0
    total_additions = 0
    total_removals = 0

    for idx, rep in enumerate(pending_reports):
        rep_id = rep["id"]
        codes_raw = rep["codes_raw"] or ""
        date_str = rep["date_str"] or ""
        time_str = rep["time_str"] or ""
        text_content = rep["text"] or ""

        user_prompt = f"""Analýza lékařské zprávy pro vykazování výkonů VFN.
Datum vyšetření: {date_str or 'Neuvedeno'}
Čas vyšetření: {time_str or 'Neuvedeno'}
Původně vykázané kódy v IS: {codes_raw or 'Žádné'}

Lékařská zpráva:
{text_content}"""

        payload = {
            "systemInstruction": system_instruction_obj,
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }

        pred_additions = []
        pred_removals = []
        success = False

        for attempt in range(3):
            try:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
                res = requests.post(endpoint_url, headers=headers, json=payload, timeout=30)
                if res.status_code == 200:
                    res_data = res.json()
                    candidates = res_data.get("candidates", [])
                    if candidates and "content" in candidates[0] and "parts" in candidates[0]["content"]:
                        parts = candidates[0]["content"]["parts"]
                        if parts and "text" in parts[0]:
                            raw_text = parts[0]["text"].strip()
                            clean_json = raw_text
                            if clean_json.startswith("```"):
                                clean_json = re.sub(r"^```[a-z]*", "", clean_json)
                                clean_json = re.sub(r"```$", "", clean_json).strip()
                            
                            pred_json = json.loads(clean_json)
                            raw_adds = pred_json.get("doporučení_k_doplnění", [])
                            raw_rems = pred_json.get("doporučení_k_odebrání", [])
                            
                            # Parse originally billed IS codes
                            raw_codes_set = set(str(c).strip().zfill(5) for c in re.split(r'[, \t]+', codes_raw.replace(';', ',')) if c.strip())
                            EXAM_CODES = {"63021", "63022", "63023"}
                            billed_exam_codes = raw_codes_set.intersection(EXAM_CODES)

                            # Filter out temporal and age codes from LLM output (handled strictly by Python)
                            TEMPORAL_AND_AGE_CODES = {"09545", "09580", "09581", "09557"}

                            filtered_adds = []
                            for item_add in raw_adds:
                                code_str = str(item_add.get("code", "")).zfill(5)
                                # Rule 0: Skip temporal/age codes
                                if code_str in TEMPORAL_AND_AGE_CODES:
                                    continue
                                # Rule 1: Skip if ALREADY billed in IS (No duplicate additions)
                                if code_str in raw_codes_set:
                                    continue
                                # Rule 2: Skip exam codes if an exam code (63021/63022/63023) is ALREADY in IS
                                if code_str in EXAM_CODES and billed_exam_codes:
                                    continue
                                filtered_adds.append(item_add)

                            filtered_rems = []
                            for item_rem in raw_rems:
                                code_str = str(item_rem.get("code", "")).zfill(5)
                                # Rule 0: Skip temporal/age codes
                                if code_str in TEMPORAL_AND_AGE_CODES:
                                    continue
                                # Rule 2: Skip removing exam codes if an exam code is in IS (No exam code switching)
                                if code_str in EXAM_CODES and billed_exam_codes:
                                    continue
                                filtered_rems.append(item_rem)

                            pred_additions = filtered_adds
                            pred_removals = filtered_rems
                            success = True
                            break
                elif res.status_code == 401:
                    token = get_auth_token()
                elif res.status_code == 429:
                    time.sleep(2 * (attempt + 1))
            except Exception as e:
                time.sleep(1 * (attempt + 1))

        # Apply Python Temporal Rules (Out-of-hours / Holiday 09545, 09580, 09581)
        raw_codes_list = [c.strip() for c in codes_raw.split(",") if c.strip()]
        temp_suggestions = get_temporal_code_suggestions(date_str, time_str, raw_codes_list)

        # Clear existing AI reviews for this report
        c.execute("DELETE FROM reviews WHERE report_id = ?", (rep_id,))

        # Insert Temporal Suggestions
        for t_add in temp_suggestions:
            c.execute("""
            INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
            VALUES (?, 'ADDITION', ?, ?, 'ČASOVÉ PRAVIDLO', ?, ?, 1.0)
            """, (rep_id, t_add["code"], t_add["name"], t_add["verbatim_quote"], t_add["reasoning"]))
            total_additions += 1

        # Insert Model Additions
        for m_add in pred_additions:
            code_str = str(m_add.get("code", "")).zfill(5)
            name_str = m_add.get("name", "")
            quote_str = m_add.get("verbatim_quote", "")
            reason_str = m_add.get("reason", "V textu zprávy popsán výkon")

            c.execute("""
            INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
            VALUES (?, 'ADDITION', ?, ?, 'GEMINI_IBIS_AMB4', ?, ?, 0.95)
            """, (rep_id, code_str, name_str, quote_str, reason_str))
            total_additions += 1

        # Insert Model Removals
        for m_rem in pred_removals:
            code_str = str(m_rem.get("code", "")).zfill(5)
            name_str = m_rem.get("name", "")
            reason_str = m_rem.get("reason", "Chybí podklad v textu")

            c.execute("""
            INSERT INTO reviews (report_id, type, code, code_name, source, exact_text_snippet, reason, confidence)
            VALUES (?, 'REMOVAL', ?, ?, 'GEMINI_IBIS_AMB4', NULL, ?, 0.95)
            """, (rep_id, code_str, name_str, reason_str))
            total_removals += 1

        processed_count += 1
        if (idx + 1) % 10 == 0 or idx == len(pending_reports) - 1:
            conn.commit()
            print(f"Processed [{idx + 1}/{len(pending_reports)}] -> Added {total_additions} additions, {total_removals} removals", flush=True)

        time.sleep(0.1)

    conn.commit()
    conn.close()

    print("=" * 65)
    print(f"ACTIVE LEARNING ITERATION READY!")
    print(f"  • Zpracováno zpráv: {processed_count}")
    print(f"  • Vygenerováno návrhů k doplnění (+): {total_additions}")
    print(f"  • Vygenerováno návrhů k odebrání (-): {total_removals}")
    print("=" * 65)

if __name__ == "__main__":
    main()
