import requests
from src.services.text_cleaner import clean_campaign_text
url = "https://www.crystalcard.com.tr/kampanyalar/vakkoda-pesin-fiyatina-6-taksit"
html = requests.get(url, verify=False).text
cleaned = clean_campaign_text(html, title="Vakko’da peşin fiyatına 6 taksit!")
print("--- FULL CLEANED TEXT ---")
print(cleaned)
