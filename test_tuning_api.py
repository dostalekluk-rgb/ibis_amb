import os
import json
import requests

API_KEY = os.getenv("GEMINI_API_KEY", "")
URL = f"https://generativelanguage.googleapis.com/v1beta/tunedModels?key={API_KEY}"

print("Reading first 20 SFT examples...")
examples = []
with open("vertex_sft_dataset.jsonl", "r", encoding="utf-8") as f:
    for i in range(20):
        line = f.readline()
        if not line:
            break
        item = json.loads(line)
        u_txt = item["contents"][0]["parts"][0]["text"]
        m_txt = item["contents"][1]["parts"][0]["text"]
        examples.append({
            "text_input": u_txt,
            "output": m_txt
        })

payload = {
    "display_name": "vfn_medical_coding_gemini",
    "base_model": "models/gemini-1.5-flash-001-tuning",
    "tuning_task": {
        "hyperparameters": {
            "epoch_count": 3,
            "batch_size": 4,
            "learning_rate": 0.001
        },
        "training_data": {
            "examples": {
                "examples": examples
            }
        }
    }
}

print(f"Sending POST to {URL[:60]}...")
res = requests.post(URL, json=payload)
print("HTTP Status:", res.status_code)
print("Response Body:\n", res.text[:500])
