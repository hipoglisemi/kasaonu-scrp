import urllib.request
from bs4 import BeautifulSoup

url = "https://www.teb.com.tr/sizin-icin/beymen-6/"

try:
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}
    )
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        
    soup = BeautifulSoup(html, 'html.parser')
    
    print("--- MOST SPECIFIC CONTENT TAG CONTAINING 'Kampanya Detayları' ---")
    el = soup.find(lambda tag: tag.get_text() and "Kampanya Detayları" in tag.get_text() and not any("Kampanya Detayları" in child.get_text() for child in tag.find_all(recursive=False)))
    if el:
        print(f"Tag: {el.name} | ID: {el.get('id')} | Classes: {el.get('class')}")
        curr = el.parent
        for i in range(5):
            if curr:
                print(f"  Parent {i+1}: {curr.name} | ID: {curr.get('id')} | Classes: {curr.get('class')}")
                curr = curr.parent
except Exception as e:
    print(f"❌ Error: {e}")
