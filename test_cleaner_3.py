import requests
from bs4 import BeautifulSoup

urls = [
    "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl",
    "https://www.crystalcard.com.tr/kampanyalar/vakkoda-pesin-fiyatina-6-taksit",
    "https://www.maximum.com.tr/kampanyalar/petlasta-taksit-firsati"
]

for url in urls:
    html = requests.get(url, verify=False).text
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator="\n", strip=True)
    
    print(f"\n--- {url.split('/')[2]} ---")
    # Find the end of the main conditions
    if "adios" in url:
        idx = text.lower().find("tek taraflı değiştirme hakkına sahiptir")
    elif "crystal" in url:
        idx = text.lower().find("değiştirme yetkisine sahiptir")
    else:
        idx = text.lower().find("değiştirme hakkını saklı tutar")
        
    print(text[idx:idx+500])
