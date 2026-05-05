import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.scrapers.ziraat import ZiraatScraper

def force_repair_17032():
    scraper = ZiraatScraper()
    url = "https://www.bankkart.com.tr/kampanyalar/e-ticaret/n11de-6-taksit"
    
    print(f"🚀 Force Re-scraping and Repairing URL: {url}")
    # _process_campaign with force=True logic is already inside the scraper's _process_campaign if we pass dict
    res = scraper._process_campaign({"url": url, "list_end_date": "31.05.2026"})
    print(f"✅ Result: {res}")

if __name__ == "__main__":
    force_repair_17032()
