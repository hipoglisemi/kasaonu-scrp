import urllib.request
from bs4 import BeautifulSoup

url = "https://www.teb.com.tr/sizin-icin/beymen-6/"

try:
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
    )
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        
    soup = BeautifulSoup(html, 'html.parser')
    
    # Print the divs that contain actual paragraphs <p>
    divs_with_p = soup.find_all('div')
    print("--- DIVS CONTAINING PARAGRAPHS OR UL/LI ---")
    count = 0
    for d in divs_with_p:
        if d.find('p') or d.find('ul'):
            txt = d.get_text().strip()
            if len(txt) > 200 and "Zaman Aşımı" not in txt and "ARAMAYI KAPAT" not in txt:
                print(f"ID: {d.get('id')} | Classes: {d.get('class')} | Length: {len(txt)}")
                print(f"Snippet: {txt[:120]}...\n")
                count += 1
                if count >= 5:
                    break
except Exception as e:
    print(f"❌ Error: {e}")
