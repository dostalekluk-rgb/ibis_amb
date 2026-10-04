import json
import os
import argparse
import subprocess
import requests
import re

GOLD_FILE = "external_validation_gold.json"
USTAVA_FILE = "ustava.txt"
PROJECT_ID = "ibis-510508"
LOCATION = "europe-central2"

def get_auth_token():
    try:
        token = subprocess.check_output("gcloud auth print-access-token", shell=True).decode().strip()
        return token
    except Exception as e:
        print(f"Error obtaining gcloud token: {e}")
        return None

def evaluate_model(endpoint_id: str):
    if not os.path.exists(GOLD_FILE):
        print(f"Error: {GOLD_FILE} not found. Run build_vertex_tuning_datasets.py first.")
        return

    with open(GOLD_FILE, "r", encoding="utf-8") as f:
        gold_data = json.load(f)

    # Load system instruction from ustava.txt
    system_instruction_text = ""
    if os.path.exists(USTAVA_FILE):
        with open(USTAVA_FILE, "r", encoding="utf-8") as f:
            system_instruction_text = f.read().strip()

    system_instruction_obj = {
        "parts": [{"text": system_instruction_text}]
    }

    total_reports = len(gold_data)
    print(f"Loaded {total_reports} gold standard reports for offline clinical evaluation.")
    
    token = get_auth_token()
    if not token:
        print("Failed to get authorization token from gcloud.")
        return

    # Clean endpoint_id
    ep_clean = endpoint_id.strip()
    if "endpoints/" in ep_clean:
        ep_clean = ep_clean.split("endpoints/")[-1]

    endpoint_url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/endpoints/{ep_clean}:generateContent"
    
    # Load existing progress if available
    progress_file = "validation_results.json"
    results = {}
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                results = json.load(f)
        except Exception:
            results = {}

    tp = 0
    fp = 0
    fn = 0

    print(f"\nStarting evaluation against Vertex Endpoint: '{ep_clean}'...")
    print("=" * 65, flush=True)

    for idx, item in enumerate(gold_data):
        rep_id = str(item['report_id'])
        gt = item["ground_truth_target"]
        gt_additions = {c["code"]: c for c in gt.get("doporučení_k_doplnění", [])}
        
        user_prompt = f"""Analýza lékařské zprávy pro vykazování výkonů VFN.
Datum vyšetření: {item.get('date_str') or 'Neuvedeno'}
Čas vyšetření: {item.get('time_str') or 'Neuvedeno'}
Původně vykázané kódy v IS: {item.get('codes_raw') or 'Žádné'}

Lékařská zpráva:
{item.get('text', '')}"""

        payload = {
            "systemInstruction": system_instruction_obj,
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }

        pred_additions = {}
        if rep_id in results and "pred_additions" in results[rep_id]:
            pred_additions = results[rep_id]["pred_additions"]
        else:
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
                                results[rep_id] = {
                                    "pred_additions": pred_additions
                                }
                                success = True
                                break
                    elif res.status_code == 401:
                        token = get_auth_token()
                    elif res.status_code == 429:
                        import time
                        time.sleep(2 * (attempt + 1))
                    else:
                        print(f"Report ID {rep_id} status {res.status_code}: {res.text[:100]}", flush=True)
                except Exception as e:
                    import time
                    time.sleep(1 * (attempt + 1))
            
            import time
            time.sleep(0.1)

        # Match TP, FP, FN
        for p_code in pred_additions:
            if p_code in gt_additions:
                tp += 1
            else:
                fp += 1
        for g_code in gt_additions:
            if g_code not in pred_additions:
                fn += 1

        with open(progress_file, "w", encoding="utf-8") as pf:
            json.dump(results, pf, ensure_ascii=False, indent=2)

        pct = ((idx + 1) / total_reports) * 100
        prec = (tp / (tp + fp)) * 100 if (tp + fp) > 0 else 0.0
        rec = (tp / (tp + fn)) * 100 if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        
        print(f"[{idx + 1}/{total_reports} - {pct:.1f}%] TP: {tp} | FP: {fp} | FN: {fn} | Precision: {prec:.1f}% | Recall: {rec:.1f}% | F1: {f1:.1f}%", flush=True)

    print("=" * 65, flush=True)
    final_prec = (tp / (tp + fp)) * 100 if (tp + fp) > 0 else 0.0
    final_rec = (tp / (tp + fn)) * 100 if (tp + fn) > 0 else 0.0
    final_f1 = (2 * final_prec * final_rec) / (final_prec + final_rec) if (final_prec + final_rec) > 0 else 0.0
    
    print("\n==================================================", flush=True)
    print("FINÁLNÍ KLINICKÝ PROTOKOL PŘESNOSTI MODELU:", flush=True)
    print(f"  • Celkem vyhodnoceno zpráv: {total_reports}", flush=True)
    print(f"  • Správně doplňované kódy (True Positives): {tp}", flush=True)
    print(f"  • Falešně navržené kódy (False Positives): {fp}", flush=True)
    print(f"  • Přehlédnuté kódy (False Negatives): {fn}", flush=True)
    print(f"  -----------------------------------------------", flush=True)
    print(f"  * PŘESNOST (Precision): {final_prec:.2f} %", flush=True)
    print(f"  * SENZITIVITA (Recall): {final_rec:.2f} %", flush=True)
    print(f"  * F1 SCORE (Vyvážený výkon): {final_f1:.2f} %", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Tuned Vertex AI Model against Holdout Gold Standard")
    parser.add_argument("--endpoint", type=str, default="4205467049499033600", help="Vertex Endpoint ID (e.g. 4205467049499033600)")
    args = parser.parse_args()

    evaluate_model(args.endpoint)
