import json
import os
import glob
import sys
from google import genai

# Ensure UTF-8 output encoding for Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

API_KEY = os.getenv("GEMINI_API_KEY", "")
JOBS_TRACKER = "all_batch_jobs.json"
TOTAL_DATASET_ROWS = 19404

print("=" * 65)
print(" VFN MEDICAL CODING - STATUS BATCH PREDIKCE")
print("=" * 65)

# Check downloaded response files
downloaded_resp_files = glob.glob("batch_chunk_*_resp.jsonl")
downloaded_rows = 0
supported_codes = 0
unsupported_codes = 0

for resp_file in downloaded_resp_files:
    try:
        with open(resp_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                downloaded_rows += 1
                data = json.loads(line)
                try:
                    raw_txt = data["response"]["candidates"][0]["content"]["parts"][0]["text"]
                    evals = json.loads(raw_txt).get("evaluations", [])
                    for ev in evals:
                        if ev.get("status"):
                            supported_codes += 1
                        else:
                            unsupported_codes += 1
                except Exception:
                    pass
    except Exception:
        pass

# Check tracked jobs in all_batch_jobs.json
jobs = []
if os.path.exists(JOBS_TRACKER):
    try:
        with open(JOBS_TRACKER, "r", encoding="utf-8") as f:
            jobs = json.load(f)
    except Exception:
        pass

client = genai.Client(api_key=API_KEY)

active_job_id = None
active_job_state = None
active_job_chunk = None

for j in jobs:
    job_id = j.get("job_id")
    chunk_idx = j.get("chunk_idx")
    if job_id:
        try:
            res = client.batches.get(name=job_id)
            state_str = str(res.state).replace("JobState.", "")
            if "RUNNING" in state_str or "PENDING" in state_str:
                active_job_id = job_id
                active_job_state = state_str
                active_job_chunk = chunk_idx
        except Exception:
            pass

# Progress calculation
pct = (downloaded_rows / TOTAL_DATASET_ROWS) * 100
bar_len = 30
filled_len = int(bar_len * downloaded_rows // TOTAL_DATASET_ROWS)
bar = "#" * filled_len + "-" * (bar_len - filled_len)

print(f"Postup zpracovani: [{bar}] {pct:.1f}% ({downloaded_rows} / {TOTAL_DATASET_ROWS} zprav)")
print("-" * 65)

if active_job_id:
    print(f" [>] BATCH PROCES AKTUÁLNĚ BĚŽÍ:")
    print(f"     - Aktivní Balík:  #0{active_job_chunk} (řádky {active_job_chunk*1000} až {(active_job_chunk+1)*1000})")
    print(f"     - Stav Úlohy:    {active_job_state}")
    print(f"     - Google Job ID:  {active_job_id}")
else:
    if downloaded_rows >= TOTAL_DATASET_ROWS:
        print(" [OK] VŠECHNY ZPRÁVY BYLY ÚSPĚŠNĚ ZPRACOVÁNY A STAŽENY!")
    else:
        print(" [||] ŽÁDNÁ ÚLOHA NENÍ AKTUÁLNĚ V BĚHU (ČEKÁ NA SPUŠTĚNÍ DALŠÍHO BALÍKU).")

print("-" * 65)
print(f" DOSAVATNÍ STATISTIKA VYHODNOCENÍ:")
print(f"   - Vyhodnocené zprávy:               {downloaded_rows}")
print(f"   - Řádně doložené kódy (OK + citace): {supported_codes}")
print(f"   - Chybné / neoprávněné kódy (False): {unsupported_codes}")
print("=" * 65)
