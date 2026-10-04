import json
import os
import time
from google import genai
import pandas as pd

API_KEY = os.getenv("GEMINI_API_KEY", "")
JOBS_TRACKER = "all_batch_jobs.json"
INPUT_AMBU = "ambu_anonymized.xlsx"
FINAL_EXCEL = "evaluations_summary_ALL.xlsx"

if not os.path.exists(JOBS_TRACKER):
    print(f"Error: '{JOBS_TRACKER}' does not exist.")
    exit(1)

with open(JOBS_TRACKER, "r", encoding="utf-8") as f:
    jobs_data = json.load(f)

client = genai.Client(api_key=API_KEY)

completed_chunks = 0
total_chunks = len(jobs_data)

all_results_map = {}

print(f"Checking status for {total_chunks} batch jobs...")

for job_item in jobs_data:
    chunk_idx = job_item["chunk_idx"]
    job_id = job_item["job_id"]
    out_jsonl = f"batch_chunk_{chunk_idx:02d}_resp.jsonl"
    
    # Check if already downloaded
    if os.path.exists(out_jsonl):
        print(f"Chunk #{chunk_idx:02d}: Already downloaded to '{out_jsonl}'. Loading...")
        with open(out_jsonl, "r", encoding="utf-8") as f_in:
            for line in f_in:
                if not line.strip():
                    continue
                d = json.loads(line)
                cid = d.get("custom_id")
                try:
                    raw_txt = d["response"]["candidates"][0]["content"]["parts"][0]["text"]
                    all_results_map[cid] = json.loads(raw_txt).get("evaluations", [])
                except Exception:
                    all_results_map[cid] = []
        completed_chunks += 1
        continue

    try:
        job = client.batches.get(name=job_id)
        print(f"Chunk #{chunk_idx:02d} (Job {job_id[:25]}...): State = {job.state}")
        
        if "SUCCEEDED" in str(job.state):
            file_name = job.dest.file_name
            content = client.files.download(file=file_name)
            with open(out_jsonl, "wb") as f_out:
                f_out.write(content)
            print(f"  -> Downloaded and saved to '{out_jsonl}'!")
            
            with open(out_jsonl, "r", encoding="utf-8") as f_in:
                for line in f_in:
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    cid = d.get("custom_id")
                    try:
                        raw_txt = d["response"]["candidates"][0]["content"]["parts"][0]["text"]
                        all_results_map[cid] = json.loads(raw_txt).get("evaluations", [])
                    except Exception:
                        all_results_map[cid] = []
            completed_chunks += 1
    except Exception as e:
        print(f"Error checking chunk #{chunk_idx:02d}: {e}")

print(f"\nProgress: {completed_chunks}/{total_chunks} chunks completed and downloaded ({len(all_results_map)} evaluations ready).")

if completed_chunks > 0:
    print(f"Building master Excel '{FINAL_EXCEL}'...")
    df_ambu = pd.read_excel(INPUT_AMBU)
    rows_out = []
    
    supported_total = 0
    unsupported_total = 0
    
    for idx, row in df_ambu.iterrows():
        custom_id = f"row_{idx}"
        if custom_id not in all_results_map:
            continue
            
        evals = all_results_map[custom_id]
        supported_list = []
        unsupported_list = []
        
        for ev in evals:
            code = ev.get("code")
            status = ev.get("status")
            quote = ev.get("verbatim_quote", "")
            reason = ev.get("unsupported_reason", "")
            conf = ev.get("confidence", 1.0)
            
            if status:
                supported_total += 1
                supported_list.append(f"{code} (jistota {conf*100:.0f}%: \"{quote}\")")
            else:
                unsupported_total += 1
                unsupported_list.append(f"{code} (důvod: {reason})")
                
        rows_out.append({
            "Řádek": idx,
            "Vykázané kódy": row[df_ambu.columns[0]],
            "Podpořené kódy (OK)": "\n".join(supported_list),
            "Chybné / Nepodpořené kódy": "\n".join(unsupported_list),
            "Text zprávy": row[df_ambu.columns[1]]
        })
        
    df_res = pd.DataFrame(rows_out)
    df_res.to_excel(FINAL_EXCEL, index=False)
    print(f"Saved master Excel '{FINAL_EXCEL}' ({len(df_res)} rows processed, {supported_total} supported codes, {unsupported_total} unsupported).")
