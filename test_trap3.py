from src.services.card_validator import CardValidator
from src.services.ai_parser_golden import BANK_CARD_KEYWORDS
from src.services.text_cleaner import clean_campaign_text
import requests
from bs4 import BeautifulSoup

url = 'https://www.wingscard.com.tr/kampanyalar/pazarama-tatilde-indirim-01'
r = requests.get(url)
soup = BeautifulSoup(r.content, 'html.parser')
raw_text = clean_campaign_text(str(soup.find('body')))

validator = CardValidator(BANK_CARD_KEYWORDS)
text_normalized = validator._normalize(raw_text)
import re

privacy_keywords = ["toplanacaktir", "islenecektir", "aydinlatma metni", "kisisel veri", "veri sorumlusu"]
infra_keywords = ["pos", "posu", "pos'u", "sistemi", "uye isyeri", "uyeisyeri", "pos sistemi"]
app_keywords = ["mobil", "uygulama", "uygulamasi", "uygulamasindan", "internet sube", "web sitesi", "online", "subesi"]

all_keywords = privacy_keywords + infra_keywords + app_keywords

for c in ["axess", "wings", "free", "ticari", "bank'o card", "ek kartlar", "sanal kartlar"]:
    card_idx = text_normalized.find(c)
    if card_idx != -1:
        window = text_normalized[card_idx:card_idx+200]
        pattern = rf"(?<![a-z0-9])(?:{'|'.join(re.escape(k) for k in all_keywords)})(?![a-z0-9])"
        match = re.search(pattern, window)
        if match:
            print(f"[{c}] Matched trap: {match.group(0)}")
