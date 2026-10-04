from bs4 import BeautifulSoup

with open('scratch_detail.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

print("=== TABLES ===")
for i, table in enumerate(soup.find_all('table')):
    print(f"\n--- Table {i} ---")
    for tr in table.find_all('tr'):
        cells = [td.get_text(' ', strip=True) for td in tr.find_all(['th', 'td'])]
        if any(cells):
            print(" | ".join(cells))

print("\n=== ALL LABELS / HEADERS / PARAGRAPHS ===")
for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'dt', 'dd', 'p', 'th', 'td', 'div']):
    txt = tag.get_text(' ', strip=True)
    if 'Obsah a rozsah' in txt or 'Název' in txt or '09115' in txt:
        print(f"<{tag.name} class='{tag.get('class')}'>: {txt}")
