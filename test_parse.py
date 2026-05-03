from src.scrapers.akbank_wings import AkbankWingsScraper
import json

scraper = AkbankWingsScraper()

print("Testing 15372...")
try:
    res_15372 = scraper._process_campaign("https://www.wingscard.com.tr/kampanyalar/idas-mobilyada-9-taksit-firsati", force=True)
    print("Result 15372:", res_15372)
except Exception as e:
    print("Error 15372:", e)

print("\nTesting 15374...")
try:
    res_15374 = scraper._process_campaign("https://www.wingscard.com.tr/kampanyalar/pazarama-tatilde-indirim-01", force=True)
    print("Result 15374:", res_15374)
except Exception as e:
    print("Error 15374:", e)
