import ssl
import urllib.request
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

code = "09115"
url = f"https://szv.mzd.gov.cz/Vykon/Detail/{code}"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(url, headers=headers)

try:
    with urllib.request.urlopen(req, context=ctx) as response:
        html = response.read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        
        with open("scratch_detail.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        print("Page Title:", soup.title.get_text() if soup.title else "No Title")
        
        # Let's find labels, headers, and fields
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'th', 'td', 'dt', 'dd', 'span', 'div', 'p', 'label']):
            txt = tag.get_text(strip=True)
            if txt and len(txt) > 3:
                # Print class/id if any
                classes = tag.get("class", "")
                tag_id = tag.get("id", "")
                # Only print interesting elements
                if any(k in txt.lower() for k in ["název", "obsah", "rozsah", "kód", "09115", "excize", "popis"]):
                    print(f"<{tag.name} id='{tag_id}' class='{classes}'>: {txt[:120]}")
except Exception as e:
    print("Error:", e)
