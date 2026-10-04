import json
import os
import time
from datetime import datetime, timezone, timedelta
from google import genai

API_KEY = os.getenv("GEMINI_API_KEY", "")
INFO_FILE = "batch_job_info.json"

def format_time(dt):
    if not dt:
        return "N/A"
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        local_dt = dt.astimezone(timezone(timedelta(hours=2)))
        return f"{local_dt.strftime('%H:%M:%S')} CEST (UTC {dt.strftime('%H:%M:%S')})"
    except Exception:
        return str(dt)

def format_duration(create_time):
    if not create_time:
        return "N/A"
    try:
        if isinstance(create_time, str):
            create_time = datetime.fromisoformat(create_time.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - create_time
        total_sec = int(diff.total_seconds())
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        seconds = total_sec % 60
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        return f"{minutes}m {seconds}s"
    except Exception:
        return "N/A"

client = genai.Client(api_key=API_KEY)

print("=" * 70)
print("              PŘEHLED VŠECH BATCH DÁVEK NA GOOGLE AI STUDIO            ")
print("=" * 70)

all_batches = list(client.batches.list())

if not all_batches:
    print("Žádné batch úlohy nebyly nalezeny.")
    exit(0)

running_jobs = []
succeeded_jobs = []
other_jobs = []

for job in all_batches:
    st = str(job.state)
    if "RUNNING" in st or "PENDING" in st:
        running_jobs.append(job)
    elif "SUCCEEDED" in st:
        succeeded_jobs.append(job)
    else:
        other_jobs.append(job)

print(f"\n[+] AKTIVNE BEZICI DAVKY ({len(running_jobs)}):")
for j in running_jobs:
    print(f"  * ID:          {j.name}")
    print(f"    Model:       {j.model}")
    print(f"    Stav:        {j.state}")
    print(f"    Vytvoreno:   {format_time(j.create_time)}")
    print(f"    Doba behu:   {format_duration(j.create_time)}")
    
    # Check if completion stats exist
    stats = getattr(j, "completion_stats", None)
    if stats:
        print(f"    Prubeh %:    {stats}")
    else:
        print(f"    Prubeh %:    Zpracovava se na cloudu Google (Atomic Batch)")
        
    print("-" * 50)

print(f"\n[v] DOKONCENE DAVKY ({len(succeeded_jobs)}):")
for j in succeeded_jobs[:3]: # show last 3
    print(f"  * ID: {j.name} | Vytvoreno: {format_time(j.create_time)}")

# Update batch_job_info.json to monitor the most recent running job if available
if running_jobs:
    latest_job = running_jobs[0] # most recent
    with open(INFO_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "job_id": latest_job.name,
            "model": latest_job.model,
            "state": str(latest_job.state),
            "create_time": str(latest_job.create_time)
        }, f, indent=2)
    print(f"\nSledovany Job v {INFO_FILE} aktualizovan na nejnovejsi: {latest_job.name}")

# Check if latest running job or any succeeded job output needs downloading
for j in succeeded_jobs[:1]:
    if hasattr(j, "dest") and j.dest and hasattr(j.dest, "file_name"):
        output_file_name = j.dest.file_name
        out_file = f"batch_responses_{j.name.split('/')[-1]}.jsonl"
        if not os.path.exists(out_file) and not os.path.exists("batch_responses.jsonl"):
            try:
                content = client.files.download(file=output_file_name)
                with open("batch_responses.jsonl", "wb") as f_out:
                    f_out.write(content)
                print(f"\nStazeny vysledky z dokoncene davky '{j.name}' do 'batch_responses.jsonl'!")
            except Exception as e:
                print(f"Chyba pri stahovani souboru: {e}")

print("=" * 70)
