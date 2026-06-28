import requests
from src.services.text_cleaner import clean_campaign_text
import warnings
warnings.filterwarnings('ignore')

url = "https://www.maximum.com.tr/kampanyalar/petlas-ta-6-taksit-firsati-1"

response = requests.get(url, verify=False)
html = response.text

cleaned = clean_campaign_text(html, "Petlas’ta 6 Taksit Fırsatı", "Petlas")
print("--- CLEANED TEXT ---")
print(cleaned)

