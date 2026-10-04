import json
import os
import subprocess
import requests
import re

GOLD_FILE = "external_validation_gold.json"
USTAVA_FILE = "ustava.txt"
PROJECT_ID = "ibis-510508"
LOCATION = "europe-central2"
ENDPOINT_ID = "4205467049499033600"
RESULTS_FILE = "validation_results.json"

def get_auth_token():
    try:
        return subprocess.check_output("gcloud auth print-access-token", shell=True).decode().strip()
    except Exception as e:
        print(f"Token error: {e}")
        return None

def main():
    with open(GOLD_FILE, "r", encoding="utf-8") as f:
        gold_data = json.load(f)

    with open(USTAVA_FILE, "r", encoding="utf-8") as f:
        sys_inst = f.read().strip()

    token = get_auth_token()
    if not token:
        print("Failed to get gcloud token.")
        return

    endpoint_url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/endpoints/{ENDPOINT_ID}:generateContent"

    results = {}
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
        except Exception:
            results = {}

    total = len(gold_data)
    print(f"Updating predictions for {total} reports (Additions + Removals)...")

    for idx, item in enumerate(gold_data):
        rep_id = str(item["report_id"])
        
        # Check if we already have both pred_additions and pred_removals
        if rep_id in results and "pred_additions" in results[rep_id] and "pred_removals" in results[rep_id]:
            continue

        user_prompt = f"""Analýza lékařské zprávy pro vykazování výkonů VFN.
Datum vyšetření: {item.get('date_str') or 'Neuvedeno'}
Čas vyšetření: {item.get('time_str') or 'Neuvedeno'}
Původně vykázané kódy v IS: {item.get('codes_raw') or 'Žádné'}

Lékařská zpráva:
{item.get('text', '')}"""

        payload = {
            "systemInstruction": {"parts": [{"text": sys_inst}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }

        success = False
        for attempt in range(4):
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
                            pred_additions = {str(c["code"]).zfill(5): c for c in pred_json.get("doporučení_k_doplnění", [])}
                            pred_removals = {str(c["code"]).zfill(5): c for c in pred_json.get("doporučení_k_odebrání", [])}
                            
                            results[rep_id] = {
                                "pred_additions": pred_additions,
                                "pred_removals": pred_removals,
                                "celkovy_stav": pred_json.get("celkovy_stav", "BEZ_ZMENY")
                            }
                            success = True
                            break
                elif res.status_code == 401:
                    token = get_auth_token()
                elif res.status_code == 429:
                    import time
                    time.sleep(2 * (attempt + 1))
            except Exception as e:
                import time
                time.sleep(1 * (attempt + 1))
        
        if (idx + 1) % 10 == 0 or idx == total - 1:
            with open(RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"Processed [{idx + 1}/{total}]", flush=True)

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Done generating full predictions!")

if __name__ == "__main__":
    main()
