
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

def test_bank(url, bank_name):
    print(f"\n🏦 Testing {bank_name}: {url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        og_title_el = soup.find("meta", property="og:title")
        og_title = og_title_el.get("content") if og_title_el else None
        title_el = soup.find("h1")
        title = title_el.text.strip() if title_el else og_title or "Başlık Yok"
        
        # Simulating FULL BODY pass (Autofix style)
        body_el = soup.find("body")
        raw_html = str(body_el) if body_el else html

        print(f"   🤖 AI Parsing...")
        res = parse_campaign(
            raw_text=raw_html,
            title=title,
            bank_name=bank_name,
            force=True,
            og_title=og_title
        )
        return {
            "title": res.get("title"),
            "sector": res.get("sector"),
            "brands": res.get("brands"),
            "reward": res.get("reward_text"),
            "cleaned_text_sample": res.get("_clean_text", "")[:200] + "..."
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    test_cases = [
        ("https://www.axess.com.tr/axess/kampanyalar/kampanya-detay/8000030501/ramazan-alisverislerinize-toplam-2500-tlye-varan-chip-para", "Akbank"),
        ("https://www.qnb.com.tr/kampanyalar/qnb-mobil-ve-internet-subeden-sigortam-net-te-indirim", "QNB"),
        ("https://www.bankkart.com.tr/kampanyalar/giyim-aksesuar-ayakkabi-ve-kozmetik-sektorlerinde-toplam-250-tl-bankkart-lira", "Ziraat"),
        ("https://www.teb.com.tr/kampanyalar/akaryakit-harcamalariniza-toplam-225-tl-bonus/", "TEB"),
        ("https://www.worldcard.com.tr/kampanyalar/akaryakit-harcamalariniza-200-tl-puan/80000000", "Yapı Kredi")
    ]
    
    # Note: Paraf/World URLs might need adjustment if they use different patterns
    
    summary = {}
    for url, bank in test_cases:
        summary[bank] = test_bank(url, bank)
        
    print("\n" + "### GLOBAL TEST SUMMARY ###")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
