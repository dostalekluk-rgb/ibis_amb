import os
import json
import time
from google import genai
from google.genai import types

API_KEY = os.getenv("GEMINI_API_KEY", "")
INPUT_JSONL = "batch_requests.jsonl"
SUBSET_JSONL = "batch_requests_1000.jsonl"
INFO_FILE = "batch_job_info.json"
MODEL_NAME = "models/gemini-3.8-flash"
LIMIT = 1000

print(f"Creating subset file '{SUBSET_JSONL}' with {LIMIT} requests...")
count = 0
with open(INPUT_JSONL, "r", encoding="utf-8") as f_in, open(SUBSET_JSONL, "w", encoding="utf-8") as f_out:
    for line in f_in:
        f_out.write(line)
        count += 1
        if count >= LIMIT:
            break

print(f"Created subset file with {count} requests.")

print(f"Initializing Google GenAI client...")
client = genai.Client(api_key=API_KEY)

print(f"Uploading '{SUBSET_JSONL}' to Google AI Studio...")
start_time = time.time()
uploaded_file = client.files.upload(
    file=SUBSET_JSONL,
    config=types.UploadFileConfig(mime_type="text/plain")
)
upload_duration = time.time() - start_time
print(f"Upload complete in {upload_duration:.1f} seconds! File Name: {uploaded_file.name}")

print(f"Submitting Batch Job for {count} requests with model '{MODEL_NAME}'...")
batch_job = client.batches.create(
    model=MODEL_NAME,
    src=uploaded_file.name
)

job_info = {
    "job_id": batch_job.name,
    "model": MODEL_NAME,
    "file_name": uploaded_file.name,
    "file_uri": uploaded_file.uri,
    "state": str(batch_job.state),
    "count": count,
    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
}

with open(INFO_FILE, "w", encoding="utf-8") as f:
    json.dump(job_info, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 60)
print(f"BATCH JOB FOR {count} REQUESTS SUCCESSFULLY SUBMITTED!")
print("=" * 60)
print(f"Job ID: {batch_job.name}")
print(f"Current State: {batch_job.state}")
