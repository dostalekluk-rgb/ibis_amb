import json
import subprocess
import requests
import time

PROJECT_ID = "ibis-510508"
LOCATION = "europe-central2"
MODEL_ID = "6198584762517422080"  # ibis_amb5 fine-tuned model
INPUT_GCS = "gs://ibis_amb/vertex_batch_21k.jsonl"
OUTPUT_GCS_PREFIX = "gs://ibis_amb/batch_output_ibis_amb5/"
INFO_FILE = "vertex_batch_job_info.json"

def get_auth_token():
    try:
        return subprocess.check_output("gcloud auth print-access-token", shell=True, text=True).strip()
    except Exception as e:
        print(f"Error obtaining gcloud token: {e}")
        return None

def submit_batch_prediction():
    token = get_auth_token()
    if not token:
        print("Failed to get gcloud authorization token.")
        return

    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/batchPredictionJobs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    job_name = f"ibis_amb5_full_21k_{int(time.time())}"
    model_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/models/{MODEL_ID}"

    payload = {
        "displayName": job_name,
        "model": model_name,
        "inputConfig": {
            "instancesFormat": "jsonl",
            "gcsSource": {
                "uris": [INPUT_GCS]
            }
        },
        "outputConfig": {
            "predictionsFormat": "jsonl",
            "gcsDestination": {
                "outputUriPrefix": OUTPUT_GCS_PREFIX
            }
        }
    }

    print(f"Submitting Vertex AI Batch Prediction Job for model ibis_amb5 ('{MODEL_ID}')...")
    print(f"  • Input GCS: {INPUT_GCS}")
    print(f"  • Output GCS Prefix: {OUTPUT_GCS_PREFIX}")
    print(f"  • Display Name: {job_name}")

    res = requests.post(url, headers=headers, json=payload)
    print(f"HTTP Status: {res.status_code}")

    if res.status_code == 200:
        res_data = res.json()
        print("\n" + "=" * 65)
        print("BATCH PREDICTION JOB FOR IBIS_AMB5 CREATED SUCCESSFULLY ON VERTEX AI!")
        print("=" * 65)
        print(f"Job Name: {res_data.get('name')}")
        print(f"State: {res_data.get('state')}")
        print(f"Create Time: {res_data.get('createTime')}")
        
        with open(INFO_FILE, "w", encoding="utf-8") as f:
            json.dump(res_data, f, indent=2, ensure_ascii=False)
        print(f"Saved job metadata to '{INFO_FILE}'.")
    else:
        print("Error submitting batch prediction job:")
        print(res.text)

if __name__ == "__main__":
    submit_batch_prediction()
