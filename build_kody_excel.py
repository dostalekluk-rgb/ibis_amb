import re
import ssl
import time
import urllib.request
from bs4 import BeautifulSoup
import pandas as pd
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 1. Read input dataset and extract unique codes
input_file = "ambu_anonymized.xlsx"
output_file = "kody.xlsx"

print(f"Loading input file: {input_file}")
df_ambu = pd.read_excel(input_file)
vykony_col = df_ambu.columns[0]

code_counts = {}
for item in df_ambu[vykony_col].dropna():
    s = str(item).replace(';', ',').replace('\n', ',')
    parts = re.split(r'[, \t]+', s)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        cleaned = re.sub(r'^\d+x', '', part, flags=re.IGNORECASE).strip()
        if cleaned:
            code_counts[cleaned] = code_counts.get(cleaned, 0) + 1

unique_codes = sorted(list(code_counts.keys()))
print(f"Extracted {len(unique_codes)} unique procedure codes from dataset.")

# SSL context for scraping ÚZIS
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

results = []

print("\nStarting ÚZIS scraping for each code...")
for idx, code in enumerate(unique_codes, 1):
    url = f"https://szv.mzd.gov.cz/Vykon/Detail/{code}"
    req = urllib.request.Request(url, headers=headers)
    
    nazev = ""
    obsah_rozsah = ""
    status_str = "OK"
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            html = resp.read().decode('utf-8')
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract row values based on header names
            for tr in soup.find_all('tr'):
                th = tr.find('th')
                td = tr.find('td')
                if th and td:
                    label = th.get_text(strip=True)
                    val = td.get_text(' ', strip=True)
                    if label == 'Název' and not nazev:
                        nazev = val
                    elif label == 'Obsah a rozsah výkonu' and not obsah_rozsah:
                        obsah_rozsah = val
            
            # Fallback for name if title tag exists
            if not nazev and soup.title:
                title_txt = soup.title.get_text(strip=True)
                if "-" in title_txt:
                    nazev = title_txt.split("-")[-1].strip()
                    
    except Exception as e:
        status_str = f"Error: {e}"
        print(f"[{idx}/{len(unique_codes)}] Code {code} -> Scraping failed: {e}")
    else:
        print(f"[{idx}/{len(unique_codes)}] Code {code} -> {nazev[:60]}... ({len(obsah_rozsah)} chars scope)")
        
    results.append({
        "Kód": code,
        "Název výkonu": nazev,
        "Obsah a rozsah výkonu": obsah_rozsah
    })
    
    # Polite delay between requests
    time.sleep(0.1)

# 2. Save to kody.xlsx
df_out = pd.DataFrame(results)
df_out.to_excel(output_file, index=False, columns=["Kód", "Název výkonu", "Obsah a rozsah výkonu"])
print(f"\nSuccessfully created '{output_file}' with {len(df_out)} rows.")
