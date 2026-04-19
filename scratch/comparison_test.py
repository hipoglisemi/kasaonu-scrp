
import os
import sys
import requests
from bs4 import BeautifulSoup
import json

# Fix sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.ai_parser import parse_campaign
from src.services.text_cleaner import clean_campaign_text

def autofix_style_clean(html, title):
    # Mimicking data_quality_autofix.py logic
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        script.extract()
    noise_selectors = ['.other-campaigns', '.featured-campaigns', '.similar-campaigns', '.campaignDetail-others']
    for selector in noise_selectors:
        for element in soup.select(selector):
            element.extract()
    text = soup.get_text(separator=' ', strip=True)
    # Autofix also calls clean_campaign_text at the end
    return clean_campaign_text(text, title=title)

def scraper_style_clean(html, title, og_title):
    # Mimicking our NEW scraper logic: Pass Ham HTML to TextCleaner
    return clean_campaign_text(html, og_title=og_title, title=title)

def run_comparison(url, bank_name):
    print(f"\n🔍 Testing URL: {url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
    response = requests.get(url, headers=headers, timeout=15)
    response.encoding = 'utf-8'
    html = response.text
    soup = BeautifulSoup(html, 'html.parser')
    
    og_title_el = soup.find("meta", property="og:title")
    og_title = og_title_el.get("content") if og_title_el else None
    title_el = soup.find("h1")
    title = title_el.text.strip() if title_el else og_title or "Başlık Yok"

    desc_el = soup.select_one(".campaign-detail") or soup.select_one(".page-content")
    raw_html = str(desc_el) if desc_el else html

    print("   🤖 Running Method A (NEW Scraper Flow)...")
    res_a = parse_campaign(raw_text=raw_html, title=title, bank_name=bank_name, force=True, og_title=og_title)

    print("   🤖 Running Method B (Autofix Flow)...")
    # Autofix uses full HTML usually but cleans it first
    # We'll simulate its fetch-and-clean internal call
    autofix_text = autofix_style_clean(html, title)
    res_b = parse_campaign(raw_text=autofix_text, title=title, bank_name=bank_name, force=True)

    return res_a, res_b

if __name__ == "__main__":
    url_isbank = "https://www.maximum.com.tr/kampanyalar/samsung-comda-secili-telefon-tablet-saat-ve-kulakliklarda-indirim-firsati"
    
    a, b = run_comparison(url_isbank, "İşbankası")
    
    print("\n" + "="*60)
    print(f"KARŞILAŞTIRMA TABLOSU (Isbank)")
    print("="*60)
    cols = ["sector", "brands", "cards", "reward_text", "reward_value"]
    print(f"{'Kolon':<15} | {'Yeni Scraper A':<20} | {'Autofix B':<20}")
    print("-" * 60)
    for col in cols:
        val_a = str(a.get(col, ""))
        val_b = str(b.get(col, ""))
        print(f"{col:<15} | {val_a:<20} | {val_b:<20}")
    
    url_garanti = "https://milesandsmilesgarantibbva.com/kampanyalar/yurt-disi-giyim-harcamalariniza-1-500-tlye-varan-indirim-ayricaligi-nisan"
    a2, b2 = run_comparison(url_garanti, "Garanti")
    
    print("\n" + "="*60)
    print(f"KARŞILAŞTIRMA TABLOSU (Garanti)")
    print("="*60)
    print(f"{'Kolon':<15} | {'Yeni Scraper A':<20} | {'Autofix B':<20}")
    print("-" * 60)
    for col in cols:
        val_a = str(a2.get(col, ""))
        val_b = str(b2.get(col, ""))
        print(f"{col:<15} | {val_a:<20} | {val_b:<20}")
