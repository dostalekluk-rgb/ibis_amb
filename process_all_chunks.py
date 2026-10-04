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

print(f"Reading '{INPUT_JSONL}'...")
all_lines = []
with open(INPUT_JSONL, "r", encoding="utf-8") as f:
    all_lines = f.readlines()

total_requests = len(all_lines)
print(f"Total requests in dataset: {total_requests}")

num_chunks = (total_requests + CHUNK_SIZE - 1) // CHUNK_SIZE
print(f"Dividing dataset into {num_chunks} chunks of ~{CHUNK_SIZE} requests each...")

# Load existing jobs tracker if available
jobs_data = []
if os.path.exists(JOBS_TRACKER):
    try:
        with open(JOBS_TRACKER, "r", encoding="utf-8") as f:
            jobs_data = json.load(f)
    except Exception:
        jobs_data = []

client = genai.Client(api_key=API_KEY)

for chunk_idx in range(num_chunks):
    start_i = chunk_idx * CHUNK_SIZE
    end_i = min(start_i + CHUNK_SIZE, total_requests)
    chunk_filename = f"batch_chunk_{chunk_idx:02d}.jsonl"
    
    # Check if already submitted
    already_submitted = any(j.get("chunk_idx") == chunk_idx for j in jobs_data)
    if already_submitted:
        print(f"Chunk #{chunk_idx:02d} ({start_i}..{end_i}) already submitted. Skipping submit.")
        continue

    print(f"\n--- Submitting Chunk #{chunk_idx:02d} ({start_i}..{end_i}) ---")
    chunk_lines = all_lines[start_i:end_i]
    with open(chunk_filename, "w", encoding="utf-8") as f_out:
        f_out.writelines(chunk_lines)
        
    print(f"Uploading '{chunk_filename}'...")
    uploaded_file = client.files.upload(
        file=chunk_filename,
        config=types.UploadFileConfig(mime_type="text/plain")
    )
    print(f"Uploaded: {uploaded_file.name}")
    
    print(f"Creating Batch Job on Google Cloud...")
    try:
        batch_job = client.batches.create(
            model=MODEL_NAME,
            src=uploaded_file.name
        )
        print(f"Job Created! ID: {batch_job.name}, State: {batch_job.state}")
        
        jobs_data.append({
            "chunk_idx": chunk_idx,
            "range": [start_i, end_i],
            "chunk_file": chunk_filename,
            "file_name": uploaded_file.name,
            "job_id": batch_job.name,
            "state": str(batch_job.state),
            "output_file": None,
            "status": "SUBMITTED"
        })
        
        with open(JOBS_TRACKER, "w", encoding="utf-8") as f_track:
            json.dump(jobs_data, f_track, indent=2, ensure_ascii=False)
            
        time.sleep(2) # Small pause between submissions
    except Exception as e:
        print(f"Error submitting chunk #{chunk_idx:02d}: {e}")
        break

print(f"\nAll submitted chunks tracked in '{JOBS_TRACKER}'.")
