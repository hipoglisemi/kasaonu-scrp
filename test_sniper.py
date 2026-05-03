from src.services.card_validator import CardValidator
from src.services.ai_parser_golden import BANK_CARD_KEYWORDS
from src.services.text_cleaner import clean_campaign_text
import requests
import re
from bs4 import BeautifulSoup

url = 'https://www.wingscard.com.tr/kampanyalar/idas-mobilyada-9-taksit-firsati'
r = requests.get(url)
soup = BeautifulSoup(r.content, 'html.parser')
raw_text = clean_campaign_text(str(soup.find('body')))

validator = CardValidator(BANK_CARD_KEYWORDS)
text_normalized = validator._normalize(raw_text)

for kc in BANK_CARD_KEYWORDS["akbank"]:
    kc_norm = validator._normalize(kc)
    if kc_norm in text_normalized:
        title_norm = validator._normalize(raw_text.split('\n')[0])
        is_in_title = kc_norm in title_norm
        has_card_suffix = re.search(rf"{kc_norm}\s+(?:kart|card|kredi|ticari)", text_normalized)
        print(f"[{kc_norm}] is_in_title: {is_in_title}, has_card_suffix: {bool(has_card_suffix)}")
