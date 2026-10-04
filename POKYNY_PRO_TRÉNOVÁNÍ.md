# Pokyny pro trénování modelu IBIS_AMB na Google Cloud Vertex AI

Tento dokument slouží jako metodický a technický návod pro přípravu trénovacího datasetu a spuštění **Supervised Fine-Tuning (SFT)** modelu Gemini na platformě Google Cloud Vertex AI.

---

## 1. Cíl trénování a architektura

Cílem je vytvořit specializovaný model Gemini vyladěný pro **audit lékařského vykazování výkonů VFN**. 

Model provádí **akční audit odchylek**:
1. **Doporučení k odebrání (`doporučení_k_odebrání`):** Identifikuje kódy původně vykázané v IS, které v textu zprávy nemají oporu.
2. **Doporučení k doplnění (`doporučení_k_doplnění`):** Identifikuje opomenuté výkony, které nebyly v IS vykázané, ale v textu jsou prokazatelně doloženy jako dnešní provedený výkon (vždy s doslovnou citací `verbatim_quote`).
3. **Ochrana proti anamnéze:** Výkony zmíněné pouze jako minulost (`st.p.`, `anamn.`, minulá léta) model striktně ignoruje a k doplnění nenavrhuje.

---

## 2. Skladba trénovacích dat (Trénovací dvojice)

Trénovací soubor `vertex_sft_dataset.jsonl` se skládá z trénovacích záznamů, kde každý záznam obsahuje dvojici **Vstup (`user`)** a **Cílová schválená odpověď (`model`)**.

### A. Vstupní část (`role: user`)
* **Datum vyšetření** (např. `24.06.2026`)
* **Čas vyšetření** (např. `08:58:00`)
* **Původně vykázané kódy v IS** (např. `42022, 09543`)
* **Celý nezkrácený text lékařské zprávy**

### B. Cílová schválená odpověď (`role: model`)
Jedná se o **sloučený finální audit**, který vzniká kombinací dvou zdrojů dat:

1. **Výstupy z dávkového auditování (Batch Job z Google AI Studio):**
   * Dodávají prověřená odebrání kódů, které lékař v IS vykázal neoprávněně.
   * Plní pole **`"doporučení_k_odebrání"`**.

2. **Ruční Gold Standard anotace z databáze (`validator_data.db`):**
   * Dodávají lidsky schválené návrhy na doplnění chybějících kódů na základě vašich anotací z validátoru:
     * **Klávesa `P` (ACCEPT):** Výkon se zařadí do **`"doporučení_k_doplnění"`** včetně doslovného textového důkazu (`verbatim_quote`).
     * **Klávesy `I` (REJECT_PAST) a `O` (REJECT):** Výkon se **do doplnění ZAŘADIT NESMÍ**. Model se na tomto negativním příkladu naučí ignorovat anamnézu a chybné návrhy.

---

## 3. Struktura trénovacího JSONL souboru (`vertex_sft_dataset.jsonl`)

Každý řádek v trénovacím JSONL souboru odpovídá standardnímu formátu Vertex AI Supervised Fine-Tuning:

```json
{
  "systemInstruction": {
    "parts": [
      {
        "text": "Jsi expertní revizní lékař a auditor gynekologického vykazování pro Všeobecnou fakultní nemocnici v Praze (VFN)... [obsah ze souboru ustava.txt]"
      }
    ]
  },
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "Analýza lékařské zprávy pro vykazování výkonů VFN.\nDatum vyšetření: 24.06.2026\nČas vyšetření: 08:58:00\nPůvodně vykázané kódy v IS: 42022, 09543\n\nLékařská zpráva:\n[kompletní text zprávy z VFN]"
        }
      ]
    },
    {
      "role": "model",
      "parts": [
        {
          "text": "{\n  \"doporučení_k_odebrání\": [\n    {\n      \"code\": \"09511\",\n      \"name\": \"Minimální kontakt lékaře s pacientem\",\n      \"reason\": \"zcela_chybi_zminka\"\n    }\n  ],\n  \"doporučení_k_doplnění\": [\n    {\n      \"code\": \"63417\",\n      \"name\": \"Ultrasonografické vyšetření pánve\",\n      \"verbatim_quote\": \"UZ vag.: děloha v AVF, ovaria bilat bpn\",\n      \"reason\": \"V textu popsáno dnešní UZ vyšetření pánve\"\n    }\n  ],\n  \"celkovy_stav\": \"OPRAVENO\"\n}"
        }
      ]
    }
  ]
}
```

---

## 4. Postup realizace trénování (Krok za krokem)

1. **Export z SQLite databáze:**
   * Spuštění skriptu `export_vertex_sft.py`, který z databáze `validator_data.db` a batch výsledků sestaví finální soubor `vertex_sft_dataset.jsonl`.

2. **Nahrání na Google Cloud Storage:**
   * Nahrání datasetu do GCP bucketu:
     `gsutil cp vertex_sft_dataset.jsonl gs://ibis_amb/vertex_sft_dataset.jsonl`

3. **Spuštění Fine-Tuning Jobu na Vertex AI:**
   * Vytvoření trénovacího úkolu nad základním modelem Gemini (např. `models/gemini-1.5-flash` nebo `gemini-3.8-flash`) v kontejneru Vertex AI Fine-Tuning.

4. **Vyhodnocení a nasazení:**
   * Získání nového Tuned Model Endpoint ID pro nasazení do produkčního prostředí IBIS_AMB.
