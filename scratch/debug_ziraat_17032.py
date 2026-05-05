import requests
import sys
import os
from bs4 import BeautifulSoup

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.ai_parser import parse_api_campaign

def debug_17032():
    url = "https://www.bankkart.com.tr/kampanyalar/e-ticaret/n11de-6-taksit"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    
    print(f"🌐 Fetching URL: {url}")
    resp = requests.get(url, headers=headers)
    html = resp.text
    
    soup = BeautifulSoup(html, 'html.parser')
    body_el = soup.find("body")
    raw_html = str(body_el) if body_el else html
    
    print(f"📝 Raw HTML Length: {len(raw_html)}")
    
    # Check if 'Bankkart' exists in raw HTML
    found_bankkart = "Bankkart" in raw_html
    print(f"🔍 Is 'Bankkart' in Raw HTML? {found_bankkart}")

    # Run AI Parser
    print("🤖 Running AI Parser...")
    result = parse_api_campaign(
        title="N11'de 6 Taksit",
        short_description="Ziraat Bankası Kampanyası",
        content_html=raw_html,
        bank_name="Ziraat Bankası",
        tracking_url=url,
        force=True
    )
    
    print(f"📊 AI Result Cards: {result.get('cards')}")
    print("-" * 50)
    # Metnin temizlenmiş halini görelim
    print(f"📝 AI'nin Okuduğu Temiz Metin (İlk 1000 karakter):\n{result.get('_clean_text', '')[:1000]}")

if __name__ == "__main__":
    debug_17032()
