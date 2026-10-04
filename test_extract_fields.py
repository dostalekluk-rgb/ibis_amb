from bs4 import BeautifulSoup

with open('scratch_detail.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

# Find all <th> or <td> or labels
name = ""
content_scope = ""

# Method 1: searching by table rows or text blocks
full_text = soup.get_text()

# Let's inspect all tr / th / td pairs or dl / dt / dd
for tr in soup.find_all('tr'):
    th = tr.find('th')
    td = tr.find('td')
    if th and td:
        label = th.get_text(strip=True)
        val = td.get_text(strip=True)
        print(f"Row label: '{label}' => '{val}'")

for element in soup.find_all(['div', 'tr', 'td', 'p']):
    text = element.get_text(strip=True)
    if text.startswith('Název') and not name:
        # Check next sibling or parent
        print("FOUND NAZEV ELEMENT:", repr(text))

# Let's search by string position in text or DOM
for dt in soup.find_all(['dt', 'th', 'td', 'div', 'span']):
    t = dt.get_text(strip=True)
    if t == 'Název':
        parent = dt.find_parent('tr') or dt.parent
        print("Název parent text:", repr(parent.get_text(' ', strip=True)))
    if t == 'Obsah a rozsah výkonu':
        parent = dt.find_parent('tr') or dt.parent
        print("Obsah parent text:", repr(parent.get_text(' ', strip=True)))
