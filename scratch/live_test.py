
import os
import sys
import requests
from bs4 import BeautifulSoup
import json

# Fix sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.ai_parser_golden import AIParserGolden
from src.services.text_cleaner import clean_campaign_text

def fetch_and_parse(url, bank_name):
    print(f"\n🚀 Fetching: {url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Simulating Scraper Extraction
        og_title_el = soup.find("meta", property="og:title")
        og_title = og_title_el.get("content") if og_title_el else None
        title_el = soup.find("h1")
        title = title_el.text.strip() if title_el else og_title or "Başlık Yok"
        
        # Logic: Find the main container (like our scrapers do)
        desc_el = soup.select_one(".campaign-detail") or soup.select_one(".page-content") or soup.select_one(".content")
        raw_html = str(desc_el) if desc_el else html

        print(f"   📝 Title Found: {title}")
        print(f"   🧹 Cleaning with new TextCleaner...")
        
        # Use our NEW Hardened Cleaner
        cleaned_text = clean_campaign_text(raw_html, og_title=og_title, title=title)
        
        print(f"   🤖 Sending to AI (AIParser)...")
        from src.services.ai_parser import parse_campaign
        res = parse_campaign(
            raw_text=raw_html,
            title=title,
            bank_name=bank_name,
            force=True, # Force fresh AI call
            og_title=og_title
        )
        
        return res
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    urls = [
        ("https://www.maximum.com.tr/kampanyalar/samsung-comda-secili-telefon-tablet-saat-ve-kulakliklarda-indirim-firsati", "İşbankası"),
        ("https://milesandsmilesgarantibbva.com/kampanyalar/yurt-disi-giyim-harcamalariniza-1-500-tlye-varan-indirim-ayricaligi-nisan", "Garanti")
    ]
    
    results = {}
    for url, bank in urls:
        results[url] = fetch_and_parse(url, bank)
        
    print("\n" + "="*50)
    print("FINAL PARSING RESULTS:")
    print("="*50)
    print(json.dumps(results, indent=2, ensure_ascii=False))
