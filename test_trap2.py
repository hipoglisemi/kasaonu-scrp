from src.services.card_validator import CardValidator
from src.services.ai_parser_golden import BANK_CARD_KEYWORDS
from src.services.text_cleaner import clean_campaign_text
import requests
from bs4 import BeautifulSoup

url = 'https://www.wingscard.com.tr/kampanyalar/idas-mobilyada-9-taksit-firsati'
r = requests.get(url)
soup = BeautifulSoup(r.content, 'html.parser')
raw_text = clean_campaign_text(str(soup.find('body')))

validator = CardValidator(BANK_CARD_KEYWORDS)
text_normalized = validator._normalize(raw_text)

for c in ["axess", "wings", "free", "ticari"]:
    card_idx = text_normalized.find(c)
    if card_idx != -1:
        window = text_normalized[card_idx:card_idx+200]
        print(f"[{c}] window: {repr(window)}")
