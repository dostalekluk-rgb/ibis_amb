import ssl
import urllib.request
from bs4 import BeautifulSoup

missing_codes = ["06355", "09545", "09547", "63894", "99821", "99991"]

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {"User-Agent": "Mozilla/5.0"}

for code in missing_codes:
    url = f"https://szv.mzd.gov.cz/Vykon/Detail/{code}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            html = resp.read().decode('utf-8')
            soup = BeautifulSoup(html, 'html.parser')
            freq = ""
            pts = ""
            for tr in soup.find_all('tr'):
                th = tr.find('th')
                td = tr.find('td')
                if th and td:
                    label = th.get_text(strip=True)
                    val = td.get_text(' ', strip=True)
                    if 'frekvenc' in label.lower():
                        freq = val
                    if 'bod' in label.lower():
                        pts = val
            print(f"Scraped missing code {code}: Freq='{freq}' | Pts='{pts}'")
    except Exception as e:
        print(f"Code {code} not found on web: {e}")
