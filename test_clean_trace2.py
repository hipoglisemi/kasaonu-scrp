import requests
import re
from bs4 import BeautifulSoup

url = "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl"
html = requests.get(url, verify=False).text

from src.services.text_cleaner import clean_campaign_text
print(clean_campaign_text(html, title="Silver logolu Mastercard’ınıza özel Galataport’ta otopark 1 TL!"))

