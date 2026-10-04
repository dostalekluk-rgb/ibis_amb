import os
import json
from google import genai

API_KEY = os.getenv("GEMINI_API_KEY", "")
client = genai.Client(api_key=API_KEY)

with open("all_batch_jobs.json", "r", encoding="utf-8") as f:
    jobs = json.load(f)

print(f"Tracked batch jobs in all_batch_jobs.json: {len(jobs)}")
for j in jobs:
    chunk_idx = j["chunk_idx"]
    job_id = j["job_id"]
    rng = j["range"]
    res = client.batches.get(name=job_id)
    print(f"Chunk #{chunk_idx:02d} (Rows {rng[0]}..{rng[1]}) | Job ID: {job_id} | State: {res.state}")
