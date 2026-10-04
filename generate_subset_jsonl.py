import json

INPUT_JSONL = "batch_requests.jsonl"
OUTPUT_JSONL = "batch_requests_500.jsonl"
LIMIT = 500

count = 0
with open(INPUT_JSONL, "r", encoding="utf-8") as f_in, open(OUTPUT_JSONL, "w", encoding="utf-8") as f_out:
    for line in f_in:
        f_out.write(line)
        count += 1
        if count >= LIMIT:
            break

print(f"Successfully created '{OUTPUT_JSONL}' with {count} requests.")
