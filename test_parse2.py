from src.services.text_cleaner import clean_campaign_text
import requests
from bs4 import BeautifulSoup

url = 'https://www.wingscard.com.tr/kampanyalar/pazarama-tatilde-indirim-01'
r = requests.get(url)
soup = BeautifulSoup(r.content, 'html.parser')
raw_text = clean_campaign_text(str(soup.find('body')))
print(raw_text[:1000])
