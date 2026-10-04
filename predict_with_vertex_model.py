import sys
import json
from google import genai

PROJECT_ID = "ibis-510508"
LOCATION = "us-central1"
MODEL_NAME = "ibis_amb"

def predict_with_vertex(text_narrative: str, date_str: str = "26.09.2026", time_str: str = "14:00:00", raw_codes: str = "63022"):
    """
    Sends a medical report directly to the fine-tuned Google Vertex AI model 'ibis_amb'
    and returns its AI generated code suggestions and reasoning.
    """
    print(f"Querying fine-tuned Vertex AI Model '{MODEL_NAME}' in region '{LOCATION}'...")
    
    prompt = f"""Analýza lékařské zprávy pro vykazování výkonů VFN.
Datum vyšetření: {date_str}
Čas vyšetření: {time_str}
Původně vykázané kódy v IS: {raw_codes}

Lékařská zpráva:
{text_narrative}"""

    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        print("\n--- GOOGLE VERTEX AI MODEL (ibis_amb) RESPONSE ---")
        print(response.text)
        print("-------------------------------------------------")
        return response.text
    except Exception as e:
        print(f"Error calling Vertex AI model: {e}")
        return None

if __name__ == "__main__":
    sample_text = "NO: Pacientka přichází po kolposkopickém nálezu. Provedena punch biopsie z čípku děložního (PB) z pozice č. 12. Vzorek odeslán na histologii."
    if len(sys.argv) > 1:
        sample_text = " ".join(sys.argv[1:])
    predict_with_vertex(sample_text)
