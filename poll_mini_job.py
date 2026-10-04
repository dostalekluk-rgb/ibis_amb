import json
import subprocess
import requests
import time

JOB_ID = "projects/56686644409/locations/europe-central2/batchPredictionJobs/7108272854583476224"

def get_auth_token():
    try:
        return subprocess.check_output("gcloud auth print-access-token", shell=True).decode().strip()
    except Exception:
        return None

def poll():
    token = get_auth_token()
    url = f"https://europe-central2-aiplatform.googleapis.com/v1/{JOB_ID}"
    headers = {"Authorization": f"Bearer {token}"}

    for i in range(12):
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            state = data.get("state")
            print(f"[{i+1}/12] State: {state}")
            if state in ["JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"]:
                print(json.dumps(data, indent=2, ensure_ascii=False))
                break
        time.sleep(5)

if __name__ == "__main__":
    poll()
