import json
import os
import subprocess
import requests
import time

PROJECT_ID = "ibis-510508"
LOCATION = "europe-central2"
MODEL_ID = "2602741935038791680"
USTAVA_FILE = "ustava.txt"
GOLD_FILE = "external_validation_gold.json"

def get_auth_token():
    try:
        return subprocess.check_output("gcloud auth print-access-token", shell=True).decode().strip()
    except Exception as e:
        print(f"Error getting token: {e}")
        return None

def test_mini_batch(format_name, instances):
    token = get_auth_token()
    jsonl_filename = f"mini_test_{format_name}.jsonl"
    gcs_uri = f"gs://ibis_amb/{jsonl_filename}"
    output_prefix = f"gs://ibis_amb/test_output_{format_name}/"

    with open(jsonl_filename, "w", encoding="utf-8") as f:
        for item in instances:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Uploading {jsonl_filename} to GCS...")
    subprocess.run(f"gcloud storage cp {jsonl_filename} {gcs_uri}", shell=True, check=True)

    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/batchPredictionJobs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    job_name = f"test_{format_name}_{int(time.time())}"
    model_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/models/{MODEL_ID}"

    payload = {
        "displayName": job_name,
        "model": model_name,
        "inputConfig": {
            "instancesFormat": "jsonl",
            "gcsSource": {
                "uris": [gcs_uri]
            }
        },
        "outputConfig": {
            "predictionsFormat": "jsonl",
            "gcsDestination": {
                "outputUriPrefix": output_prefix
            }
        }
    }

    print(f"Submitting test batch job '{job_name}'...")
    res = requests.post(url, headers=headers, json=payload)
    if res.status_code == 200:
        res_data = res.json()
        print(f"  • Job Created: {res_data.get('name')}")
        return res_data.get('name')
    else:
        print(f"  • Failed: {res.status_code} - {res.text}")
        return None

def main():
    with open(USTAVA_FILE, "r", encoding="utf-8") as f:
        sys_inst = f.read().strip()

    with open(GOLD_FILE, "r", encoding="utf-8") as f:
        gold = json.load(f)[:5]

    sys_obj = {"parts": [{"text": sys_inst}]}

    # Format 2: request wrapper + systemInstruction + generationConfig (responseMimeType: application/json ONLY)
    inst_format2 = []
    for item in gold:
        prompt = f"Analýza lékařské zprávy pro vykazování výkonů VFN.\nDatum: {item.get('date_str')}\nČas: {item.get('time_str')}\nPůvodně vykázané kódy v IS: {item.get('codes_raw')}\n\nLékařská zpráva:\n{item.get('text')}"
        inst_format2.append({
            "request": {
                "systemInstruction": sys_obj,
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            }
        })

    job2 = test_mini_batch("format2_request_clean", inst_format2)
    print(f"JOB_ID_TO_POLL: {job2}")

if __name__ == "__main__":
    main()
