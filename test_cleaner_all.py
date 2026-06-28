import requests
from src.services.text_cleaner import clean_campaign_text

urls = [
    ("https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl", "Silver logolu Mastercard’ınıza özel Galataport’ta otopark 1 TL!"),
    ("https://www.crystalcard.com.tr/kampanyalar/vakkoda-pesin-fiyatina-6-taksit", "Vakko’da peşin fiyatına 6 taksit!"),
    ("https://www.maximum.com.tr/kampanyalar/petlasta-taksit-firsati", "Petlas’ta 6 Taksit Fırsatı")
]

for url, title in urls:
    html = requests.get(url, verify=False).text
    cleaned = clean_campaign_text(html, title=title)
    print(f"\n--- {url.split('/')[2]} ---")
    print(cleaned[-400:])
