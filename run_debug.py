import requests
from debug_cleaner_temp import clean_campaign_text
url = "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl"
html = requests.get(url, verify=False).text
clean_campaign_text(html, title="Silver logolu Mastercard’ınıza özel Galataport’ta otopark 1 TL!")
