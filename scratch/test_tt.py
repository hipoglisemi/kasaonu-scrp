import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.scrapers.turktelekom import TurkTelekomScraper

scraper = TurkTelekomScraper()

# Mock discovery to just return one of the failing links to test our fix!
scraper._scrape_list_all = lambda: [
    {"url": "javascript:;", "title": "Bozuk Link Test"},
    {"url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/faturasiz-talimatli-tl-yukleme-kampanyasi", "title": "Real Link Test"}
]
scraper.run()
