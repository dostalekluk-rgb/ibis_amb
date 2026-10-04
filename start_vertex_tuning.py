import json
import os
import subprocess
import requests

PROJECT_ID = "ibis-510508"
LOCATION = "europe-central2"
LOCAL_TRAIN_FILE = "vertex_train_dataset.jsonl"
GCS_URI = "gs://ibis_amb/vertex_train_dataset.jsonl"
BASE_MODEL = "gemini-2.5-flash"
TUNED_MODEL_DISPLAY_NAME = "ibis_amb5"

def get_gcloud_token():
    try:
        token = subprocess.check_output("gcloud auth print-access-token", shell=True, text=True).strip()
        return token
    except Exception as e:
        print(f"Error getting gcloud token: {e}")
        return None

def upload_to_gcs():
    print(f"Uploading '{LOCAL_TRAIN_FILE}' to '{GCS_URI}'...")
    try:
        cmd = f"gcloud storage cp {LOCAL_TRAIN_FILE} {GCS_URI}"
        subprocess.check_call(cmd, shell=True)
        print("[OK] Upload to GCS completed successfully!")
        return True
    except Exception as e:
        print(f"Error uploading file to GCS: {e}")
        return False

def launch_tuning():
    if not upload_to_gcs():
        print("[!] Aborting tuning due to GCS upload failure.")
        return False

    print(f"\nInitializing Vertex AI Tuning for project '{PROJECT_ID}' in location '{LOCATION}'...")
    print(f"Dataset URI: {GCS_URI} (1254 human-validated reports)")
    print(f"Base Model:  {BASE_MODEL}")
    print(f"Tuned Model: {TUNED_MODEL_DISPLAY_NAME}")
    
    token = get_gcloud_token()
    if not token:
        print("[!] Could not retrieve access token from gcloud.")
        return False
        
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/tuningJobs"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "baseModel": f"publishers/google/models/{BASE_MODEL}",
        "tunedModelDisplayName": TUNED_MODEL_DISPLAY_NAME,
        "supervisedTuningSpec": {
            "trainingDatasetUri": GCS_URI
        }
    }
    
    resp = requests.post(url, headers=headers, json=payload)
    
    if resp.status_code == 200:
        data = resp.json()
        print("\n=========================================================")
        print("[OK] VERTEX AI TUNING JOB SUCCESSFULLY STARTED!")
        print(f"  Job Resource Name: {data.get('name')}")
        print(f"  State:             {data.get('state', 'JOB_STATE_PENDING')}")
        print(f"  Display Name:      {TUNED_MODEL_DISPLAY_NAME}")
        print("=========================================================")
        print("Model condition and progress can be viewed in Google Cloud Console -> Vertex AI -> Model Development -> Tuning.")
        
        # Save config
        cfg = {
            "vertex_model_id": data.get("name", TUNED_MODEL_DISPLAY_NAME),
            "is_active": True,
            "project_id": PROJECT_ID
        }
        with open("vertex_config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            
        return True
    else:
        print(f"\n[!] Vertex AI API returned error ({resp.status_code}): {resp.text}")
        return False

if __name__ == "__main__":
    launch_tuning()

