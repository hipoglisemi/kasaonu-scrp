import requests
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def scrape_oliz_web():
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = requests.get('https://www.oliz.com.tr/oliz_avantajlari', headers=headers, verify=False)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    campaigns = soup.find_all('div', class_='allcampaigns__list-item')
    print(f"Found {len(campaigns)} campaigns on the web!")
    
    for c in campaigns[:5]: # just print 5
        title = c.find('h4')
        brand = c.find('h3')
        img = c.find('img')
        
        print(f"---")
        if brand: print(f"Brand: {brand.text.strip()}")
        if title: print(f"Title: {title.text.strip()}")
        if img and img.get('src'): print(f"Image: {img.get('src')}")

scrape_oliz_web()
