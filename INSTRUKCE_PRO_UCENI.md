# 🚀 INSTRUKCE PRO TRÉNOVÁNÍ A VALIDACI MODELU NA GOOGLE CLOUD VERTEX AI

Tento návod vás krok za krokem provede nahráním vygenerovaných datasetů do vašich Google Cloud Storage bucketů, spuštěním trénování a prováděním vestavěné i externí validace.

---

## 📁 1. Přehled vygenerovaných souborů

Skript automaticky vytvořil z vašich **1 219 validovaných zpráv (1 749 rozhodnutí)** následující soubory v kořenovém adresáři projektu:

1. **`vertex_train_dataset.jsonl`** (975 příkladů – 80 % dat)
   * Hlavní trénovací soubor pro Supervised Fine-Tuning.
2. **`vertex_val_dataset.jsonl`** (244 příkladů – 20 % dat)
   * Slepecká validační sada určená přímo do rozhraní Vertex AI (`Enable model validation`).
3. **`external_validation_gold.json`** (244 příkladů)
   * Zlatý standard pro náš externí hodnotící skript v Pythonu.
4. **`ustava.txt`**
   * Systémová instrukce (System Instruction) definující pravidla a JSON formát auditu.

---

## ☁️ 2. Krok 1: Nahrání souborů do Google Cloud Storage Bucket

Otevřete příkazovou řádku (Google Cloud SDK / PowerShell) a nahrajte soubory do vašeho bucketu `gs://ibis_amb/`:

```bash
gcloud storage cp vertex_train_dataset.jsonl gs://ibis_amb/vertex_train_dataset.jsonl
gcloud storage cp vertex_val_dataset.jsonl gs://ibis_amb/vertex_val_dataset.jsonl
```

*(Případně můžete soubory přetáhnout přímo přes webové rozhraní Google Cloud Console -> Cloud Storage -> Buckets -> `ibis_amb`).*

---

## ⚙️ 3. Krok 2: Spuštění Fine-Tuning Jobu ve Vertex AI Console

1. Otevřete **Google Cloud Console**: [https://console.cloud.google.com/vertex-ai/models/tuning](https://console.cloud.google.com/vertex-ai/models/tuning)
2. Klikněte na tlačítko **+ CREATE TUNED MODEL**.
3. Vyberte základní model:
   * **Model:** `Gemini 1.5 Flash` nebo `Gemini 3.8 Flash`
4. Nastavte trénovací dataset:
   * **Training dataset:** `gs://ibis_amb/vertex_train_dataset.jsonl`
5. **Zapněte vestavěnou validaci:**
   * Přepínač **`Enable model validation`** přepněte do polohy **ZAPNUTO (ON)**.
   * **Validation dataset:** `gs://ibis_amb/vertex_val_dataset.jsonl`
6. Vložte systémovou instrukci (System Instruction):
   * Do pole **System Instruction** zkopírujte celý text ze souboru [`ustava.txt`](file:///c:/Users/dosta/Documents/prog/ibis_a/ustava.txt).
7. Klikněte na **START TUNING**.

---

## 📊 4. Krok 3: Sledování průběhu a vestavěné validace

Po spuštění tuningu uvidíte v rozhraní GCP:
* **Training Loss Curve:** Křivku učení na trénovacích datech.
* **Validation Loss Curve:** Křivku chybovosti na validačních datech (`vertex_val_dataset.jsonl`), která ukazuje, že se model nepřeučuje (neoverfittuje).

Trénování trvá obvykle 15 až 45 minut podle vytížení GCP.

---

## 🔬 5. Krok 4: Spuštění naší externí klinické validace

Po dokončení trénování získáte vaše nové **Tuned Model Endpoint ID**.

Pro spočítání lékařských meřítek (přesnost doplňování, senzitivita odhalování opomenutých kódů a správnost vyřazení anamnézy) spustíte v terminálu:

```bash
python evaluate_vertex_model.py --endpoint ZDE_VLOŽTE_VAŠE_TUNED_MODEL_ENDPOINT_ID
```

Skript porovná predikce nového modelu oproti slepeckému zlatému standardu v `external_validation_gold.json` a vypíše přehledný lékařský protokol přesnosti.
