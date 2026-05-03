import sys
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
sys.path.insert(0, project_root)

from src.services.ai_parser_golden import get_golden_parser, clean_campaign_text
import requests

url = "https://www.axess.com.tr/ticarikartlar/kampanyadetay/8/22144/ilk-kez-axess-businessa-basvuranlara-dijital-reklam-harcamalarinda-50-indirim-firsati"
# Use the same logic as data_quality_autofix
from data_quality_autofix import fetch_html
html = fetch_html(url)
text = clean_campaign_text(html, title="İlk kez Axess Business’a Başvuranlara Dijital Reklam Harcamalarında %50 İndirim Fırsatı!")

print("--- AI WILL SEE THIS TEXT ---")
print(text)
print("--- END OF TEXT ---")

if "wings" in text.lower():
    print("❌ FOUND 'WINGS' IN CLEANED TEXT!")
else:
    print("✅ 'WINGS' NOT FOUND IN CLEANED TEXT.")
