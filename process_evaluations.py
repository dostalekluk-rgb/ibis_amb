import json
import pandas as pd

INPUT_AMBU = "ambu_anonymized.xlsx"
RESPONSES_JSONL = "batch_responses.jsonl"
OUTPUT_EXCEL = "evaluations_summary.xlsx"

print(f"Loading {INPUT_AMBU}...")
df_ambu = pd.read_excel(INPUT_AMBU)

print(f"Reading {RESPONSES_JSONL}...")
results_map = {}

with open(RESPONSES_JSONL, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        data = json.loads(line)
        custom_id = data.get("custom_id")  # e.g. "row_0"
        
        try:
            raw_text = data["response"]["candidates"][0]["content"]["parts"][0]["text"]
            eval_data = json.loads(raw_text)
            results_map[custom_id] = eval_data.get("evaluations", [])
        except Exception as e:
            results_map[custom_id] = []

print(f"Parsed evaluations for {len(results_map)} rows.")

rows_out = []
supported_total = 0
unsupported_total = 0

for idx, row in df_ambu.iterrows():
    custom_id = f"row_{idx}"
    if custom_id not in results_map:
        continue
        
    evals = results_map[custom_id]
    
    supported_list = []
    unsupported_list = []
    
    for ev in evals:
        code = ev.get("code")
        status = ev.get("status")
        quote = ev.get("verbatim_quote", "")
        reason = ev.get("unsupported_reason", "")
        conf = ev.get("confidence", 1.0)
        
        if status:
            supported_total += 1
            supported_list.append(f"{code} (jistota {conf*100:.0f}%: \"{quote}\")")
        else:
            unsupported_total += 1
            unsupported_list.append(f"{code} (důvod: {reason})")
            
    rows_out.append({
        "Řádek": idx,
        "Vykázané kódy": row[df_ambu.columns[0]],
        "Podpořené kódy (OK)": "\n".join(supported_list),
        "Chybné / Nepodpořené kódy": "\n".join(unsupported_list),
        "Text zprávy": row[df_ambu.columns[1]]
    })

df_res = pd.DataFrame(rows_out)
df_res.to_excel(OUTPUT_EXCEL, index=False)

print(f"\n==========================================")
print(f"EVALUATION SUMMARY")
print(f"==========================================")
print(f"Processed rows:             {len(df_res)}")
print(f"Total supported codes (OK): {supported_total}")
print(f"Total unsupported (False): {unsupported_total}")
print(f"Saved summary to '{OUTPUT_EXCEL}'.")
