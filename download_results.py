import os
import json
from google import genai

API_KEY = os.getenv("GEMINI_API_KEY", "")
INFO_FILE = "batch_job_info.json"
OUTPUT_FILE = "batch_responses.jsonl"

client = genai.Client(api_key=API_KEY)

with open(INFO_FILE, "r", encoding="utf-8") as f:
    job_info = json.load(f)

job_id = job_info["job_id"]
print(f"Fetching job status for: {job_id}")
job = client.batches.get(name=job_id)

file_name = job.dest.file_name
print(f"Downloading output file: {file_name}")

content_bytes = client.files.download(file=file_name)

with open(OUTPUT_FILE, "wb") as f_out:
    f_out.write(content_bytes)

print(f"Successfully downloaded and saved results to '{OUTPUT_FILE}'! (Size: {len(content_bytes)} bytes)")

# Read sample responses from batch_responses.jsonl
print("\n--- SAMPLE RESPONSES ---")
with open(OUTPUT_FILE, "r", encoding="utf-8") as f_in:
    for i in range(3):
        line = f_in.readline()
        if line:
            data = json.loads(line)
            print(f"\nResponse {i+1} (Custom ID: {data.get('custom_id')}):")
            print(json.dumps(data, indent=2, ensure_ascii=False)[:600] + "...")
