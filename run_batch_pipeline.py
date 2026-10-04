import json
import os
import time
from google import genai
from google.genai import types

API_KEY = os.getenv("GEMINI_API_KEY", "")
INPUT_JSONL = "batch_requests.jsonl"
JOBS_TRACKER = "all_batch_jobs.json"
MODEL_NAME = "gemini-3.8-flash"
CHUNK_SIZE = 1000

print(f"Reading '{INPUT_JSONL}'...", flush=True)
with open(INPUT_JSONL, "r", encoding="utf-8") as f:
    all_lines = f.readlines()

total_requests = len(all_lines)
num_chunks = (total_requests + CHUNK_SIZE - 1) // CHUNK_SIZE

print(f"Total dataset: {total_requests} requests split into {num_chunks} chunks.")

client = genai.Client(api_key=API_KEY)

# Load existing tracker
jobs_data = []
if os.path.exists(JOBS_TRACKER):
    with open(JOBS_TRACKER, "r", encoding="utf-8") as f:
        jobs_data = json.load(f)

for chunk_idx in range(num_chunks):
    start_i = chunk_idx * CHUNK_SIZE
    end_i = min(start_i + CHUNK_SIZE, total_requests)
    chunk_filename = f"batch_chunk_{chunk_idx:02d}.jsonl"
    resp_filename = f"batch_chunk_{chunk_idx:02d}_resp.jsonl"
    
    if os.path.exists(resp_filename):
        print(f"Chunk #{chunk_idx:02d} ({start_i}..{end_i}) already completed & downloaded.")
        continue

    # Find job info in tracker
    job_info = next((j for j in jobs_data if j.get("chunk_idx") == chunk_idx), None)
    
    if not job_info:
        # Needs to be submitted
        print(f"\nSubmitting Chunk #{chunk_idx:02d} ({start_i}..{end_i})...")
        chunk_lines = all_lines[start_i:end_i]
        with open(chunk_filename, "w", encoding="utf-8") as f_out:
            f_out.writelines(chunk_lines)
            
        submitted = False
        for attempt in range(10):
            try:
                uploaded_file = client.files.upload(
                    file=chunk_filename,
                    config=types.UploadFileConfig(mime_type="text/plain")
                )
                batch_job = client.batches.create(
                    model=MODEL_NAME,
                    src=uploaded_file.name
                )
                print(f"  -> Job Submitted! ID: {batch_job.name}, State: {batch_job.state}")
                
                job_info = {
                    "chunk_idx": chunk_idx,
                    "range": [start_i, end_i],
                    "chunk_file": chunk_filename,
                    "file_name": uploaded_file.name,
                    "job_id": batch_job.name,
                    "state": str(batch_job.state)
                }
                jobs_data.append(job_info)
                with open(JOBS_TRACKER, "w", encoding="utf-8") as f_t:
                    json.dump(jobs_data, f_t, indent=2, ensure_ascii=False)
                submitted = True
                break
            except Exception as e:
                wait_time = (attempt + 1) * 30
                print(f"  -> Submission attempt {attempt+1} failed ({e}). Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                
        if not submitted:
            print("  -> Could not submit chunk due to repeated capacity/connection errors. Will retry on next cycle.")
            break

    # Monitor current running job
    job_id = job_info["job_id"]
    print(f"Waiting for Chunk #{chunk_idx:02d} (Job {job_id[:20]}...) to finish...")
    
    while True:
        try:
            job = client.batches.get(name=job_id)
            print(f"  [Status Check]: {job.state}")
            if "SUCCEEDED" in str(job.state):
                print(f"  -> Chunk #{chunk_idx:02d} SUCCEEDED! Downloading results...")
                content = client.files.download(file=job.dest.file_name)
                with open(resp_filename, "wb") as f_res:
                    f_res.write(content)
                print(f"  -> Saved to '{resp_filename}'!")
                break
            elif "FAILED" in str(job.state) or "CANCELLED" in str(job.state):
                print(f"  -> Chunk #{chunk_idx:02d} FAILED or CANCELLED.")
                break
        except Exception as e:
            print(f"  -> Error checking status (503/network, retrying in 30s): {e}")
            
        time.sleep(30) # Poll every 30 seconds with error tolerance

print("\nPipeline execution cycle finished.")
