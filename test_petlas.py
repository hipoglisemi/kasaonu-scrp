import requests
from src.services.text_cleaner import clean_campaign_text

url = "https://www.maximum.com.tr/kampanyalar/petlas-ta-6-taksit-firsati"

response = requests.get(url, verify=False)
html = response.text

cleaned = clean_campaign_text(html)
print("--- CLEANED TEXT ---")
print(cleaned)

