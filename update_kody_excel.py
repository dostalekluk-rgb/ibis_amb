import pandas as pd

# Load existing kody.xlsx and uzis.xlsx
df_kody = pd.read_excel('kody.xlsx')
df_uzis = pd.read_excel('uzis.xlsx')

# Ensure Kód formatting (5 digits)
df_kody['Kód'] = df_kody['Kód'].astype(str).str.strip().str.zfill(5)
df_uzis['Číslo výkonu'] = df_uzis['Číslo výkonu'].astype(str).str.strip().str.zfill(5)

# Drop duplicate code numbers in uzis.xlsx if any
df_uzis_clean = df_uzis.drop_duplicates(subset=['Číslo výkonu']).copy()

# Identify columns H and L in uzis.xlsx
col_frekvence = df_uzis.columns[7]  # 'Omezení frekvencí' (Col H)
col_body = df_uzis.columns[11]      # 'Bodová hodnota celkem' (Col L)

print(f"Column H name in uzis.xlsx: {col_frekvence}")
print(f"Column L name in uzis.xlsx: {col_body}")

# Map values using code dictionary
frekvence_map = df_uzis_clean.set_index('Číslo výkonu')[col_frekvence].to_dict()
body_map = df_uzis_clean.set_index('Číslo výkonu')[col_body].to_dict()

def clean_frekvence(val):
    if pd.isna(val):
        return ""
    s = str(val).strip()
    # Normalize newlines or multiple whitespace
    s = " ".join(s.split())
    return s

df_kody['Omezení frekvencí'] = df_kody['Kód'].map(frekvence_map).apply(clean_frekvence)
df_kody['Bodová hodnota celkem'] = df_kody['Kód'].map(body_map)

print("\n--- Check results ---")
for idx, row in df_kody.iterrows():
    code = row['Kód']
    freq = row['Omezení frekvencí']
    pts = row['Bodová hodnota celkem']
    print(f"Code {code}: Frekvence='{freq}' | Body={pts}")

# Save updated DataFrame to kody.xlsx
df_kody.to_excel('kody.xlsx', index=False, columns=[
    'Kód', 
    'Název výkonu', 
    'Obsah a rozsah výkonu', 
    'Omezení frekvencí', 
    'Bodová hodnota celkem'
])

print("\nSuccessfully updated kody.xlsx with columns D (Omezení frekvencí) and E (Bodová hodnota celkem).")
