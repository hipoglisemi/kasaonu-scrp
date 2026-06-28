import requests
from src.services.text_cleaner import clean_campaign_text

url = "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl"
html = requests.get(url, verify=False).text

# Bypass title-based chopping by not passing the title
cleaned = clean_campaign_text(html)

print("--- FULL CLEANED TEXT (NO TITLE) ---")
print(cleaned)
