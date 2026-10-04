import os
import json
import time
from google import genai
from google.genai import types

API_KEY = os.getenv("GEMINI_API_KEY", "")
INPUT_JSONL = "batch_requests_500.jsonl"
INFO_FILE = "batch_job_info.json"
MODEL_NAME = "gemini-3.8-flash"

print(f"Initializing Google GenAI client with key: {API_KEY[:8]}...")
client = genai.Client(api_key=API_KEY)

print(f"Uploading '{INPUT_JSONL}' (500 requests) to Google AI Studio...")
start_time = time.time()

uploaded_file = client.files.upload(
    file=INPUT_JSONL,
    config=types.UploadFileConfig(mime_type="text/plain")
)

upload_duration = time.time() - start_time
print(f"Upload complete in {upload_duration:.1f} seconds!")
print(f"File Name: {uploaded_file.name}")
print(f"File URI: {uploaded_file.uri}")

print(f"\nSubmitting Batch Job for model '{MODEL_NAME}'...")
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
    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
}

with open(INFO_FILE, "w", encoding="utf-8") as f:
    json.dump(job_info, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 60)
print(f"BATCH JOB SUCCESSFULLY SUBMITTED TO GOOGLE CLOUD!")
print("=" * 60)
print(f"Job ID: {batch_job.name}")
print(f"Current State: {batch_job.state}")
print(f"Saved job info to '{INFO_FILE}'.")
