import requests
from src.services.text_cleaner import clean_campaign_text

url = "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl"
html = requests.get(url, verify=False).text

# To trace, let's copy the code of clean_campaign_text and add prints
# Or just use pdb? No, simpler to edit it locally temporarily.
