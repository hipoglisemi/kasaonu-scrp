import requests
from bs4 import BeautifulSoup
import re

url = "https://www.bonus.com.tr/kampanyalar/a101-ekstra-market-kampanyasi"
resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
soup = BeautifulSoup(resp.content, 'html.parser')

print("--- HEADERS ---")
for h in soup.find_all(['h2', 'h3', 'h4']):
    print(f"[{h.name}] {h.get_text(strip=True)}")

print("\n--- DİĞER BİLGİLER BÖLÜMÜ ---")
# DİĞER BİLGİLER usually in a specific div or section
for header in soup.find_all(string=re.compile(r'(?i)Diğer Bilgiler|Kampanyaya Dahil')):
    print(f"Found match: {header.strip()}")
    parent = header.parent
    print(f"Parent tag: {parent.name}")
    # Print next few siblings
    for sibling in parent.find_next_siblings()[:5]:
        print(f"  -> [{sibling.name}] {sibling.get_text(strip=True)[:100]}...")

