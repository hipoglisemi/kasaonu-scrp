import sys
import os
import json
from datetime import datetime

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.ai_parser_golden import parse_api_campaign

# Test Data (from browser subagent)
TEST_CAMPAIGNS = [
    {
        "id": "samsung_maximum",
        "url": "https://www.maximum.com.tr/kampanyalar/samsung-comda-secili-telefon-tablet-saat-ve-kulakliklarda-indirim-firsati",
        "og_title": "Samsung.com'da Seçili Telefon, Tablet, Saat ve Kulaklıklarda Sepette %5 İndirim! | Maximum",
        "bank_name": "İşbankası",
        "desc": "Samsung.com'da telefon, tablet, saat ve kulaklıklarda %5 indirim fırsatı"
    },
    {
        "id": "garanti_miles",
        "url": "https://milesandsmilesgarantibbva.com/kampanyalar/yurt-disi-giyim-harcamalariniza-1-500-tlye-varan-indirim-ayricaligi-nisan",
        "og_title": "Miles&Smiles Garanti BBVA - Yurt dışı giyim harcamalarınıza 1.500 TL’ye varan indirim ayrıcalığı!",
        "bank_name": "Garanti",
        "desc": "Yurtdışı giyim harcamalarına 1.500 TL indirim"
    }
]

# We need the full body content. Since I cannot effectively "pass" the browser subagent's massive HTML 
# direct to a python script without local file, I will use a simple playwright fetch inside this script 
# to mimic the REAL scraper environment I just built.

def run_test():
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        
        results = []
        for camp in TEST_CAMPAIGNS:
            print(f"\n🚀 Testing URL: {camp['url']}")
            page = context.new_page()
            page.goto(camp['url'], wait_until="networkidle", timeout=60000)
            
            # This is EXACTLY what we do in the standardized scrapers now:
            full_html = page.content()
            og_title = camp['og_title']
            
            # Run through the Autofix-Standard Pipeline (Golden Parser)
            print(f"🧠 Parsing through Autofix-Standard Pipeline...")
            ai_data = parse_api_campaign(
                title=og_title,
                short_description=camp['desc'],
                content_html=full_html,
                bank_name=camp['bank_name'],
                tracking_url=camp['url'],
                og_title=og_title
            )
            
            results.append({
                "id": camp['id'],
                "url": camp['url'],
                "ai_result": ai_data
            })
            page.close()
        
        browser.close()
    
    # Export results for report
    with open("scratch/comparison_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # Print a nice summary table
    print("\n" + "="*80)
    print(f"{'URL':<20} | {'BRAND':<15} | {'SECTOR':<15} | {'CARDS'}")
    print("-" * 80)
    for res in results:
        ai = res['ai_result']
        url_short = res['url'].split('/')[-1][:20]
        brands = ", ".join(ai.get('brands', [])) or "None"
        sector = ai.get('sector', 'None')
        cards = ", ".join(ai.get('cards', [])) or "None"
        print(f"{url_short:<20} | {brands:<15} | {sector:<15} | {cards}")
    print("="*80)

if __name__ == "__main__":
    run_test()
