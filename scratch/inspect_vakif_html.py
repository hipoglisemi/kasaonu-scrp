import os
import sys
import requests
from bs4 import BeautifulSoup

def debug_vakif(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    }
    res = requests.get(url, headers=headers, verify=False)
    html = res.text
    print(f"HTML Length: {len(html)}")
    
    with open("scratch/vakif_debug.html", "w") as f:
        f.write(html)
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Let's see what happens if we decompose common tags
    for element in soup(["script", "style", "nav", "footer", "header", "noscript", "meta", "iframe", "svg", "link"]):
        element.decompose()
        
    text = soup.get_text(separator=" ", strip=True)
    print(f"Text Length after decompose: {len(text)}")
    print(f"Sample Text: {text[:500]}")

if __name__ == "__main__":
    debug_vakif("https://www.vakifkart.com.tr/kampanyalar/beyaz-esya-alisverisinize-1500-tl-worldpuan-40108")
