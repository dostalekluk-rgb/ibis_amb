import os
import json
import requests

API_KEY = os.getenv("GEMINI_API_KEY", "")

# Let's inspect the batch jobs endpoint or files endpoint
url_files = f"https://generativelanguage.googleapis.com/v1beta/files?key={API_KEY}"
res_files = requests.get(url_files)
print("Files endpoint status:", res_files.status_code)

url_batch = f"https://generativelanguage.googleapis.com/v1beta/batchJobs?key={API_KEY}"
res_batch = requests.get(url_batch)
print("Batch jobs endpoint status:", res_batch.status_code)
if res_batch.status_code != 200:
    print("Batch jobs error:", res_batch.text)
else:
    print("Batch jobs list:", res_batch.json())
