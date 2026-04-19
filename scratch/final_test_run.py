import sys
import os
import json
from datetime import datetime

# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.ai_parser_golden import parse_api_campaign

# Load content from read_url_content outputs
# step 655 was Samsung
# step 658 was Garanti
samsung_content_path = "/Users/hipoglisemi/.gemini/antigravity/brain/aee77ccc-5d76-43ad-87af-ee16593d80f4/.system_generated/steps/655/content.md"
garanti_content_path = "/Users/hipoglisemi/.gemini/antigravity/brain/aee77ccc-5d76-43ad-87af-ee16593d80f4/.system_generated/steps/658/content.md"

def read_content(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

samsung_html = read_content(samsung_content_path)
garanti_html = read_content(garanti_content_path)

TESTS = [
    {
        "name": "Samsung Maximum Campaign",
        "html": samsung_html,
        "og_title": "Samsung.com'da Seçili Telefon, Tablet, Saat ve Kulaklıklarda Sepette %5 İndirim! | Maximum",
        "bank": "İşbankası",
        "url": "https://www.maximum.com.tr/kampanyalar/samsung-comda-secili-telefon-tablet-saat-ve-kulakliklarda-indirim-firsati"
    },
    {
        "name": "Garanti Miles&Smiles Campaign",
        "html": garanti_html,
        "og_title": "Miles&Smiles Garanti BBVA - Yurt dışı giyim harcamalarınıza 1.500 TL’ye varan indirim ayrıcalığı!",
        "bank": "Garanti",
        "url": "https://milesandsmilesgarantibbva.com/kampanyalar/yurt-disi-giyim-harcamalariniza-1-500-tlye-varan-indirim-ayricaligi-nisan"
    }
]

results = []
for test in TESTS:
    print(f"\n🧠 Running AI Parse for: {test['name']}")
    res = parse_api_campaign(
        title=test['og_title'],
        short_description=None,
        content_html=test['html'],
        bank_name=test['bank'],
        tracking_url=test['url'],
        og_title=test['og_title']
    )
    results.append({
        "test_name": test['name'],
        "url": test['url'],
        "result": res
    })

# Output as JSON for easy reporting
with open("scratch/final_verification_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n✅ Verification Complete. Check scratch/final_verification_results.json")
