import json
import os
import sys
import time
import datetime
import subprocess
import requests

INFO_FILE = "vertex_batch_job_info.json"
POLL_INTERVAL_SECONDS = 10

def get_auth_token():
    try:
        return subprocess.check_output("gcloud auth print-access-token", shell=True, text=True).strip()
    except Exception as e:
        print(f"Chyba pri ziskavani gcloud tokenu: {e}")
        return None

def format_time_delta(seconds):
    if seconds < 0:
        return "0s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"

def draw_progress_bar(completed, total, length=30):
    if total <= 0:
        return ""
    percent = min(1.0, max(0.0, completed / total))
    filled_len = int(length * percent)
    bar = '=' * filled_len + '-' * (length - filled_len)
    return f"[{bar}] {percent * 100:.1f}%"

def main():
    if not os.path.exists(INFO_FILE):
        print(f"[-] Soubor s metadaty jobu '{INFO_FILE}' nebyl nalezen.")
        print("Pred spustenim monitoringu nejprve odeslete davku na Vertex AI skriptem submit_vertex_batch.py.")
        return

    try:
        with open(INFO_FILE, "r", encoding="utf-8") as f:
            job_data = json.load(f)
    except Exception as e:
        print(f"[-] Nelze nacist metadata z '{INFO_FILE}': {e}")
        return

    job_name = job_data.get("name")
    display_name = job_data.get("displayName", "Vertex AI Batch Prediction")
    
    if not job_name:
        print("[-] Neplatna metadata jobu (chybi 'name').")
        return

    token = get_auth_token()
    if not token:
        print("[-] Nelze se autorizovat vuci GCP.")
        return

    url = f"https://europe-central2-aiplatform.googleapis.com/v1/{job_name}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    start_time = time.time()
    last_token_refresh = start_time
    iteration = 0

    print("=" * 75)
    print(f"--- SLEDOVAC PRUBESHU VERTEX AI BATCH JOB (Obnoveni kazdych {POLL_INTERVAL_SECONDS}s) ---")
    print(f"  • Nazev davky: {display_name}")
    print(f"  • Job ID:      {job_name}")
    print("=" * 75)

    while True:
        iteration += 1
        now = time.time()

        # Refresh OAuth token every 45 minutes
        if now - last_token_refresh > 2700:
            new_token = get_auth_token()
            if new_token:
                token = new_token
                headers["Authorization"] = f"Bearer {token}"
                last_token_refresh = now

        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                state = data.get("state", "UNKNOWN")
                update_time = data.get("updateTime", "")

                stats = data.get("completionStats", {})
                succ = int(stats.get("successfulCount", 0))
                failed = int(stats.get("failedCount", 0))
                incomplete = int(stats.get("incompleteCount", 0))
                
                total_items = succ + failed + incomplete
                if total_items == 0:
                    total_items = 21468  # Vychazi z celkoveho poctu zprav VFN

                completed = succ + failed
                percent = (completed / total_items * 100) if total_items > 0 else 0.0
                elapsed = now - start_time

                # ETA calculation
                eta_str = "pocitam..."
                if completed > 0 and total_items > completed:
                    rate = completed / elapsed  # items per second
                    rem_items = total_items - completed
                    rem_seconds = rem_items / rate
                    eta_str = format_time_delta(rem_seconds)
                elif completed >= total_items:
                    eta_str = "0s"

                timestamp_str = datetime.datetime.now().strftime("%H:%M:%S")
                elapsed_str = format_time_delta(elapsed)
                
                if completed > 0:
                    status_line = f"[{timestamp_str}] Test #{iteration} | Stav: {state} | {draw_progress_bar(completed, total_items)} | ETA: {eta_str} | Uplynulo: {elapsed_str}"
                else:
                    status_line = f"[{timestamp_str}] Test #{iteration} | Stav: {state} (Aktivní výpočet 21 468 zpráv na GCP GPUs) | Uplynulý čas: {elapsed_str}"
                
                sys.stdout.write(f"\r{status_line}")
                sys.stdout.flush()

                if state == "JOB_STATE_SUCCEEDED":
                    print("\n\n" + "=" * 75)
                    print("  * DAVKOVE AUDITOVANI BYLO USPESNE DOKONCENO NA 100 %!")
                    print(f"  • Zpracovano zprav: {completed:,} z {total_items:,}")
                    print(f"  • Celkovy cas vypoctud: {format_time_delta(elapsed)}")
                    output_gcs = data.get("outputConfig", {}).get("gcsDestination", {}).get("outputUriPrefix")
                    print(f"  • Vysledky ulozeny na GCS: {output_gcs}")
                    print("=" * 75)
                    break

                elif state in ["JOB_STATE_FAILED", "JOB_STATE_CANCELLED"]:
                    print("\n\n" + "=" * 75)
                    print(f"  [-] JOB SKONCIL CHYBOU / ZRUSENIM (Stav: {state})")
                    err = data.get("error", {})
                    if err:
                        print(f"  • Detail chyby: {err.get('message')}")
                    print("=" * 75)
                    break

            elif res.status_code == 401:
                new_token = get_auth_token()
                if new_token:
                    token = new_token
                    headers["Authorization"] = f"Bearer {token}"
            else:
                print(f"\n[!] HTTP Chyba {res.status_code}: {res.text[:100]}")

        except Exception as e:
            print(f"\n[!] Chyba pri dotazu na Vertex AI: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
