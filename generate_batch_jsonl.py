import json
import re
import pandas as pd

INPUT_AMBU = "ambu_anonymized.xlsx"
INPUT_KODY = "kody.xlsx"
OUTPUT_JSONL = "batch_requests.jsonl"

print("Loading kody.xlsx catalog...")
df_kody = pd.read_excel(INPUT_KODY)
kody_catalog = {}
for _, row in df_kody.iterrows():
    code = str(row["Kód"]).strip().zfill(5)
    name = str(row["Název výkonu"]) if pd.notna(row["Název výkonu"]) else ""
    scope = str(row["Obsah a rozsah výkonu"]) if pd.notna(row["Obsah a rozsah výkonu"]) else ""
    kody_catalog[code] = {
        "nazev": name,
        "obsah_rozsah": scope
    }

print(f"Loading {INPUT_AMBU}...")
df_ambu = pd.read_excel(INPUT_AMBU)
vykony_col = df_ambu.columns[0]
text_col = df_ambu.columns[1]

SYSTEM_INSTRUCTION = """Jsi špičkový lékařský auditor a odborník na vykazování zdravotních výkonů ve Všeobecné fakultní nemocnici.
Tvořivě a s hlubokým porozuměním české lékařské terminologii, klinickým zkratkám a slangu vyhodnocuješ, zda byl daný výkon v textu zprávy reálně proveden BĚHEM DNEŠNÍ NÁVŠTĚVY.

STRIKTNÍ HLAVNÍ PRAVIDLA AUDITU:
1. PŘEČÍST CELOU ZPRÁVU A POSOUZIT HLAVNÍ KONTEXT: Neposuzuj zprávu podle jednoho vytrženého slova. Vždy si přečti celý text, porozuměj celkovému klinickému ději a záměru ošetření.
2. DŮRAZNĚ ODLIŠIT VYŠETŘENÍ Z MINULOSTI: Důrazně odliš vyšetření, která proběhla v minulosti (v anamnéze, na jiném pracovišti či před lety), od výkonů reálně provedených během DNEŠNÍ vizity/ošetření.
3. POZOR NA FORMULACE 'st.p.' (status post): Označení 'st.p.' (např. 'st.p. excizi čípku', 'st.p. LPSK', 'st.p. extrakci IUD') VŽDY označuje stav po minulém zákroku! Tyto zákroky nebyly provedeny dnes a NESMÍ být vykazovány.
4. IGNOROVAT A ZAMÍTAT (status: false):
   - Minulé letopočty a anamnézu (např. '2018 - extrakce IUD', 'kyretáž Nymburk 2020', 'cytologie 2024 negativní').
   - Stav po minulých zákrocích ('st.p. probatorní excizi').
   - Plány a doporučení do budoucna (např. 'doporučuji kontrolní cytologii za rok', 'doporučen odběr u OG').
   - Negace a neprovedení ('cytologie neodebrána').

KLÍČOVÝ PŘÍKLAD ANAMNÉZY (NEVYKAZOVAT):
Text: "terapeutická kyretáž pro krvácení (Nymburk). 2018 - extrakce IUD - nyní UZ diagnostikována rezidua IUD. st.p. LPSK 2021."
- Hodnocení kódu 63555 (Extrakce IUD): status: false, unsupported_reason: "anamnesticky_udaj_z_roku_2018".
- Odůvodnění: Extrakce IUD i LPSK proběhly v minulosti. Dnes byla pouze diagnostikována rezidua na UZ, nová extrakce provedena nebyla.

Úkoly pro každý přiřazený kód:
1. 'code': Kód výkonu (5 cifer).
2. 'status': true (pokud je výkon sémanticky doložen jako DNES PROVEDENÝ), false (pokud jde o anamnézu/st.p./minulost, plán do budoucna, negaci nebo chybějící výkon).
3. 'verbatim_quote': Pokud status=true, uveď PŘESNOU DOSLOVNOU CITACI úseku z textu zprávy odůvodňující dnešní provedení. Pokud status=false, uveď null.
4. 'confidence': Číslo od 0.0 do 1.0 vyjadřující jistotu hodnocení.
5. 'unsupported_reason': Pokud status=false, uveď přesný důvod ('anamnesticky_udaj_z_minulosti', 'stav_po_zakroku_st_p', 'pouze_planovano_do_budoucna', 'zcela_chybi_zminka', 'zamena_vykonu'). Pokud status=true, uveď null.
"""

response_schema = {
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
}

written_count = 0
skipped_count = 0

print(f"Generating '{OUTPUT_JSONL}'...")
with open(OUTPUT_JSONL, "w", encoding="utf-8") as f_out:
    for idx, row in df_ambu.iterrows():
        codes_val = row[vykony_col]
        text_val = row[text_col]
        
        if pd.isna(codes_val) or pd.isna(text_val):
            skipped_count += 1
            continue
            
        text_str = str(text_val).strip()
        codes_str = str(codes_val).strip()
        
        if not text_str or not codes_str:
            skipped_count += 1
            continue
            
        # Parse individual codes
        raw_parts = re.split(r'[, \t]+', codes_str.replace(';', ','))
        cleaned_codes = []
        for p in raw_parts:
            p = p.strip()
            if p:
                c = re.sub(r'^\d+x', '', p, flags=re.IGNORECASE).strip().zfill(5)
                if c not in cleaned_codes:
                    cleaned_codes.append(c)
                    
        if not cleaned_codes:
            skipped_count += 1
            continue
            
        codes_context = []
        for c in cleaned_codes:
            info = kody_catalog.get(c, {"nazev": "Neznámý výkon", "obsah_rozsah": ""})
            codes_context.append(f"- Kód {c}: Název = '{info['nazev']}', Náplň výkonu = '{info['obsah_rozsah']}'")
        
        codes_prompt_part = "\n".join(codes_context)
        
        user_prompt = f"""Kódy k hodnocení a jejich oficiální definice ÚZIS:
{codes_prompt_part}

Text lékařské zprávy:
\"\"\"{text_str}\"\"\"

Vyhodnoť každý z výše uvedených kódů a vrať výsledek v definované struktuře JSON."""

        # Construct JSONL request object
        req_item = {
            "custom_id": f"row_{idx}",
            "request": {
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
                    "response_schema": response_schema,
                    "temperature": 0.1
                }
            }
        }
        
        f_out.write(json.dumps(req_item, ensure_ascii=False) + "\n")
        written_count += 1
        
        if written_count % 5000 == 0:
            print(f"Processed {written_count} rows...")

print(f"\nDone! Generated {written_count} JSONL requests in '{OUTPUT_JSONL}' (Skipped {skipped_count} empty rows).")
