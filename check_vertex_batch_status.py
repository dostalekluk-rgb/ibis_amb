import json
import os
import subprocess
import requests

INFO_FILE = "vertex_batch_job_info.json"

def get_auth_token():
    try:
        return subprocess.check_output("gcloud auth print-access-token", shell=True).decode().strip()
    except Exception as e:
        print(f"Error getting token: {e}")
        return None

def draw_progress_bar(completed, total, length=30):
    if total <= 0:
        return ""
    percent = completed / total
    filled_len = int(length * percent)
    bar = '=' * filled_len + '-' * (length - filled_len)
    return f"[{bar}] {percent * 100:.1f}% ({completed:,} / {total:,})"

def check_status():
    if not os.path.exists(INFO_FILE):
        print(f"Error: '{INFO_FILE}' not found. Připravte nejprve batch job.")
        return

    with open(INFO_FILE, "r", encoding="utf-8") as f:
        job_data = json.load(f)

    job_name = job_data.get("name")
    if not job_name:
        print("Neplatná metadata batch jobu.")
        return

    token = get_auth_token()
    if not token:
        return

    url = f"https://europe-central2-aiplatform.googleapis.com/v1/{job_name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json()
        state = data.get('state', 'UNKNOWN')
        display_name = data.get('displayName', 'Vertex AI Batch')
        
        # Extract completion stats if available from Vertex AI
        stats = data.get("completionStats", {})
        succ = int(stats.get("successfulCount", 0))
        failed = int(stats.get("failedCount", 0))
        incomplete = int(stats.get("incompleteCount", 0))
        
        total_items = succ + failed + incomplete
        if total_items == 0:
            total_items = 21468  # Fallback to total reports count

        print("=" * 70)
        print(f"VERTEX AI BATCH PREDICTION JOB STATUS: {display_name}")
        print("=" * 70)
        print(f"  • Job ID:           {data.get('name')}")
        print(f"  • Stav (State):     {state}")
        print(f"  • Vytvořeno:        {data.get('createTime')}")
        print(f"  • Aktualizováno:    {data.get('updateTime')}")

        if stats:
            print(f"  • Zpracováno:       {succ:,} úspěšných, {failed:,} chyb, {incomplete:,} zbývá")
            print(f"  • Průběh:           {draw_progress_bar(succ, total_items)}")

        err = data.get("error")
        if err:
            print(f"  • Chyba jobu:       {err.get('message')}")

        print("-" * 70)
        if state == 'JOB_STATE_SUCCEEDED':
            print("  🎉 DÁVKOVÉ AUDITOVÁNÍ BYLO ÚSPĚŠNĚ DOKONČENO NA 100 %!")
            output_gcs = data.get('outputConfig', {}).get('gcsDestination', {}).get('outputUriPrefix')
            print(f"  • Výsledné soubory zapsány v GCS: {output_gcs}")
        elif state == 'JOB_STATE_RUNNING':
            progress_str = draw_progress_bar(succ, total_items) if stats else "zpracovávání probíhá na GCP"
            print(f"  ⏳ [RUNNING] Job právě běží na cloudu: {progress_str}")
        elif state == 'JOB_STATE_PENDING':
            print("  🕒 [PENDING] Job alokuje výpočetní GPU uzly na GCP datacentru...")
        print("=" * 70)
    else:
        print(f"HTTP Error {res.status_code}: {res.text}")

if __name__ == "__main__":
    check_status()
