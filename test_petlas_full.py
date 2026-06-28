import requests
from src.services.text_cleaner import clean_campaign_text
import warnings
warnings.filterwarnings('ignore')

url = "https://www.maximum.com.tr/kampanyalar/petlasta-taksit-firsati"
html = requests.get(url, verify=False).text
cleaned = clean_campaign_text(html, title="Petlas’ta 6 Taksit Fırsatı")
print(cleaned)

