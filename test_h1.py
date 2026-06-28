import requests
from bs4 import BeautifulSoup
url = "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl"
html = requests.get(url, verify=False).text
soup = BeautifulSoup(html, "html.parser")
h1s = soup.find_all("h1")
for h1 in h1s:
    print(f"H1 classes: {h1.get('class')}, id: {h1.get('id')}")
    print(f"Parent classes: {h1.parent.get('class')}")
