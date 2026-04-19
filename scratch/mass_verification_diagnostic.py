import sys
import os
import json
import time
from datetime import datetime

# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the Golden Parser
from src.services.ai_parser_golden import parse_api_campaign

# 14 Test URLs sorted by Bank Family
TEST_MANIFEST = {
  "akbank": [
    "https://www.axess.com.tr/axess/kampanyadetay/8/16182/tatilsepetinden-yapacaginiz-harcamalariniza-7500-tlye-varan-chip-para-nisan",
    "https://www.axess.com.tr/axess/kampanyadetay/8/16147/beyaz-esya-elektronik-ve-mobilya-harcamalariniza-2000-tlye-varan-chip-para-nisan"
  ],
  "garanti": [
    "https://milesandsmilesgarantibbva.com/kampanyalar/yurt-disi-giyim-harcamalariniza-1-500-tlye-varan-indirim-ayricaligi-nisan",
    "https://www.bonus.com.tr/kampanyalar/bonus-alisveris-eticaret-kampanyasi"
  ],
  "yapikredi": [
    "https://www.worldcard.com.tr/kampanyalar/bellonada-9-aya-varan-taksit-firsati-ocak",
    "https://www.worldcard.com.tr/kampanyalar/mondihomeda-pesin-fiyatina-9-aya-varan-taksit-firsati-ocak"
  ],
  "ziraat": [
    "https://www.bankkart.com.tr/kampanyalar/diger-kampanyalar/ilk-bankkart-kredi-kartiniza-5000-tl-bankkart-lira",
    "https://www.bankkart.com.tr/kampanyalar/e-ticaret/trendyolda-toplam-750-tl-bankkart-lira"
  ],
  "vakifbank": [
    "https://www.vakifkart.com.tr/kampanyalar/visa-ile-hepsiburada-harcamaniza-1000-tl-indirim-40059",
    "https://www.vakifkart.com.tr/kampanyalar/elektronik-esya-alisverisinize-1500-tl-worldpuan-40048"
  ],
  "paraf": [
    "https://www.paraf.com.tr/tr/kampanyalar/market/market-alisverislerinize-1250tl-parafpara.html",
    "https://www.paraf.com.tr/tr/kampanyalar/seyahat/ucak-bileti-harcamalariniza-2500-tl-parafpara.html"
  ],
  "isbankasi": [
    "https://www.maximum.com.tr/kampanyalar/maximumdan-birikimli-market-alisverislerinize-maxipuan-kampanyasi",
    "https://www.maximum.com.tr/kampanyalar/maxiumumdan-etsde-maxipuan-firsati"
  ]
}

def run_mass_verification():
    from playwright.sync_api import sync_playwright
    
    results = {}
    
    with sync_playwright() as p:
        # We need a browser to get REALLY clean HTML (Full Body) for diagnostic
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        
        for bank, urls in TEST_MANIFEST.items():
            results[bank] = []
            for url in urls:
                print(f"🔍 Testing [{bank.upper()}]: {url}")
                try:
                    page = context.new_page()
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    
                    # Capture Exactly what our standardized scrapers see
                    full_html = page.content()
                    # Find og:title automatically
                    og_title = page.eval_on_selector("meta[property='og:title']", "el => el.content") or page.title()
                    
                    # AI Standard Pipeline Call
                    ai_data = parse_api_campaign(
                        title=og_title,
                        short_description=None,
                        content_html=full_html,
                        bank_name=bank.capitalize(),
                        tracking_url=url,
                        og_title=og_title
                    )
                    
                    if ai_data:
                        results[bank].append({
                            "url": url,
                            "data": ai_data
                        })
                    else:
                        print(f"   ❌ FAILED AI Extraction for {url}")
                    
                    page.close()
                except Exception as e:
                    print(f"   ❌ ERROR for {url}: {e}")
                
        browser.close()

    # Save Results
    with open("scratch/mass_verification_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print("\n✅ Mass Verification Diagnostic Complete.")
    print("Results saved to scratch/mass_verification_results.json")

if __name__ == "__main__":
    run_mass_verification()
