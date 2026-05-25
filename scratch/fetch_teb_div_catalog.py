import urllib.request
import re
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
    
    print("--- ALL DIV ELEMENTS AND TEXT LENGTHS ---")
    for idx, d in enumerate(soup.find_all('div')):
        tag_id = d.get('id')
        classes = d.get('class')
        txt = d.get_text().strip()
        if tag_id or classes:
            # Only print unique structural divs
            if len(txt) > 50:
                print(f"[{idx}] ID: {tag_id} | Classes: {classes} | Length: {len(txt)} | Snippet: {txt[:80].replace(chr(10), ' ').replace(chr(13), ' ')}...")
except Exception as e:
    print(f"❌ Error: {e}")
