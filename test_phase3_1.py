import os
import json
import re
import requests
import pandas as pd

API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = "gemini-3.8-flash"

# 1. Load kody.xlsx catalog
df_kody = pd.read_excel("kody.xlsx")
kody_catalog = {}
for _, row in df_kody.iterrows():
    code = str(row["Kód"]).strip().zfill(5)
    name = str(row["Název výkonu"]) if pd.notna(row["Název výkonu"]) else ""
    scope = str(row["Obsah a rozsah výkonu"]) if pd.notna(row["Obsah a rozsah výkonu"]) else ""
    kody_catalog[code] = {
        "nazev": name,
        "obsah_rozsah": scope
    }

# 2. Load ambu_anonymized.xlsx
df_ambu = pd.read_excel("ambu_anonymized.xlsx")
vykony_col = df_ambu.columns[0]
text_col = df_ambu.columns[1]

# Pick 3 non-empty sample reports with codes
sample_reports = []
for idx, row in df_ambu.iterrows():
    codes_str = str(row[vykony_col])
    text_str = str(row[text_col])
    
    if pd.isna(row[vykony_col]) or pd.isna(row[text_col]):
        continue
    if len(text_str.strip()) > 100 and len(codes_str.strip()) > 3:
        raw_parts = re.split(r'[, \t]+', codes_str.replace(';', ','))
        cleaned_codes = []
        for p in raw_parts:
            p = p.strip()
            if p:
                c = re.sub(r'^\d+x', '', p, flags=re.IGNORECASE).strip().zfill(5)
                if c not in cleaned_codes:
                    cleaned_codes.append(c)
        
        sample_reports.append({
            "row_idx": idx,
            "codes": cleaned_codes,
            "text": text_str.strip()
        })
        if len(sample_reports) >= 3:
            break

SYSTEM_INSTRUCTION = """Jsi špičkový lékařský auditor a odborník na vykazování zdravotních výkonů ve Všeobecné fakultní nemocnici.
Tvořivě a s hlubokým porozuměním české lékařské terminologii, klinickým zkratkám a slangu vyhodnocuješ, zda byl daný výkon v textu zprávy reálně proveden.

DŮLEŽITÉ UPOZORNĚNÍ:
Lékaři ve zprávách NEPOUŽÍVAJÍ doslovný název výkonu z číselníku ÚZIS. Popisují zákroky, klinické úkony, symptomy, podané léky nebo nálezy (např. 'provedena probatorní excize z čípku', 'zrcadla, 5% kys. octová', 'i.v. kanyla', 'odběr krve').
Musíš s porozuměním posoudit, zda popsaný klinický postup nebo nález v textu sémanticky odpovídá náplni daného výkonu!

Úkoly pro každý přiřazený kód:
1. 'code': Kód výkonu (5 cifer).
2. 'status': true (pokud je výkon v textu sémanticky doložen), false (pokud zcela chybí, jde jen o anamnézu, plán do budoucna nebo jiný výkon).
3. 'verbatim_quote': Pokud status=true, uveď PŘESNOU DOSLOVNOU CITACI věty nebo úseku z textu zprávy, který provedení výkonu odůvodňuje. Pokud status=false, uveď null.
4. 'confidence': Číslo od 0.0 do 1.0 vyjadřující jistotu tvého hodnocení.
5. 'unsupported_reason': Pokud status=false, uveď důvod (např. 'anamnesticky_udaj', 'pouze_planovano_do_budoucna', 'zcela_chybi_zminka', 'zamena_vykonu'). Pokud status=true, uveď null.
"""

url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={API_KEY}"

for sample in sample_reports:
    print("=" * 80)
    print(f"REPORT ROW #{sample['row_idx']} | Assigned Codes: {sample['codes']}")
    print("-" * 80)
    print("TEXT ZPRÁVY:")
    print(sample['text'])
    print("-" * 80)
    
    codes_context = []
    for c in sample['codes']:
        info = kody_catalog.get(c, {"nazev": "Neznámý výkon", "obsah_rozsah": ""})
        codes_context.append(f"- Kód {c}: Název = '{info['nazev']}', Náplň výkonu = '{info['obsah_rozsah']}'")
    
    codes_str = "\n".join(codes_context)
    
    user_prompt = f"""Kódy k hodnocení a jejich oficiální definice ÚZIS:
{codes_str}

Text lékařské zprávy:
\"\"\"{sample['text']}\"\"\"

Vyhodnoť každý z výše uvedených kódů a vrať výsledek v definované struktuře JSON."""

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        },
        "contents": [
            {
                "parts": [{"text": user_prompt}]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": {
                "type": "OBJECT",
                "properties": {
                    "evaluations": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "code": {"type": "STRING"},
                                "status": {"type": "BOOLEAN"},
                                "verbatim_quote": {"type": "STRING", "nullable": True},
                                "confidence": {"type": "NUMBER"},
                                "unsupported_reason": {"type": "STRING", "nullable": True}
                            },
                            "required": ["code", "status", "confidence"]
                        }
                    }
                },
                "required": ["evaluations"]
            },
            "temperature": 0.1
        }
    }
    
    try:
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        if res.status_code == 200:
            result_json = res.json()
            raw_text = result_json['candidates'][0]['content']['parts'][0]['text']
            parsed_eval = json.loads(raw_text)
            print("GEMINI EVALUATION RESULT:")
            print(json.dumps(parsed_eval, indent=2, ensure_ascii=False))
        else:
            print("API Error:", res.status_code, res.text)
    except Exception as e:
        print("Execution Exception:", e)
    print("\n")
