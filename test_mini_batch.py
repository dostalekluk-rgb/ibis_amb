import os
import time
from google import genai
from google.genai import types

API_KEY = os.getenv("GEMINI_API_KEY", "")
client = genai.Client(api_key=API_KEY)

mini_filename = "mini_batch.jsonl"
with open(mini_filename, "w", encoding="utf-8") as f:
    f.write('{"custom_id": "req_1", "request": {"contents": [{"parts": [{"text": "Ahoj, jak se máš? Odpověz krátce v JSON: {\\\"odpoved\\\": \\\"...\\\"}"}]}], "generationConfig": {"response_mime_type": "application/json"}}}\n')
    f.write('{"custom_id": "req_2", "request": {"contents": [{"parts": [{"text": "Co je to VFN? Odpověz krátce v JSON: {\\\"odpoved\\\": \\\"...\\\"}"}]}], "generationConfig": {"response_mime_type": "application/json"}}}\n')

print(f"Created '{mini_filename}'")

print("Uploading file to Google AI Studio...")
uploaded_file = client.files.upload(
    file=mini_filename,
    config=types.UploadFileConfig(mime_type="text/plain")
)
print(f"File uploaded successfully! Name: {uploaded_file.name}, URI: {uploaded_file.uri}")

print("Creating batch job with gemini-3.8-flash...")
batch_job = client.batches.create(
    model="gemini-3.8-flash",
    src=uploaded_file.name
)

print(f"Batch job created successfully!")
print(f"Job Name (ID): {batch_job.name}")
print(f"State: {batch_job.state}")
