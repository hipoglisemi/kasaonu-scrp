
import os
import sys
import requests
from bs4 import BeautifulSoup
import re

def get_links_from_page(url, pattern):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if re.search(pattern, href, re.I):
                if href.startswith('/'):
                    base = "/".join(url.split('/')[:3])
                    href = base + href
                elif not href.startswith('http'):
                    href = url.rstrip('/') + '/' + href
                links.append(href)
        return list(set(links))
    except:
        return []

# Banks and their list pages + campaign URL pattern
BANKS_MAP = {
    "Nays": ("https://www.naysapp.com.tr/firsatlar", r"/firsatlar/"),
    "Shell": ("https://www.shell.com.tr/suruculer/shellden-avantajli-kampanyalar.html", r"/kampanyalar/"),
    "TEB": ("https://www.teb.com.tr/kampanyalar/", r"/kampanyalar/"),
    "Akbank": ("https://www.axess.com.tr/axess/kampanyalar", r"/kampanya-detay/"),
    "QNB": ("https://www.qnb.com.tr/kampanyalar", r"/kampanyalar/"),
    "Ziraat": ("https://www.bankkart.com.tr/kampanyalar", r"/kampanyalar/"),
    "Vakifbank": ("https://www.vakifkart.com.tr/kampanyalar", r"/kampanyalar/"),
    "Halkbank": ("https://www.paraf.com.tr/tr/kampanyalar.html", r"/kampanya-detay.html\?cid="), # This might be dynamic
    "Petrolofisi": ("https://www.petrolofisi.com.tr/kampanyalar", r"/kampanyalar/"),
    "Opet": ("https://www.opet.com.tr/kampanyalar", r"/kampanyalar/"),
    "Denizbank": ("https://www.denizbonus.com/bonus-kampanyalari", r"/kampanya/"),
    "Yapı Kredi": ("https://www.worldcard.com.tr/kampanyalar", r"/kampanyalar/"),
    "Vodafone": ("https://www.vodafone.com.tr/kampanyalar/red-marka-ayricaliklari", r"/kampanyalar/"),
    "Turkcell": ("https://paycell.com.tr/kampanyalar", r"/kampanyalar/"),
    "Tami": ("https://www.tami.com.tr/kampanyalar/tami-kart", r"/kampanyalar/"),
}

if __name__ == "__main__":
    test_urls = {}
    for bank, (list_url, pattern) in BANKS_MAP.items():
        print(f"🔍 Searching for {bank} links...")
        found = get_links_from_page(list_url, pattern)
        if found:
            test_urls[bank] = found[0] # Just take the first one for testing
            print(f"   ✅ Found: {found[0]}")
        else:
            print(f"   ❌ No link found for {bank}")
            
    # Output for my use
    import json
    with open("scratch/verified_test_urls.json", "w") as f:
        json.dump(test_urls, f, indent=2)
