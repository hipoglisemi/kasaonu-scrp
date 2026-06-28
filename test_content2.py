import requests
import re
from bs4 import BeautifulSoup
url = "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl"
html = requests.get(url, verify=False).text
soup = BeautifulSoup(html, "html.parser")
content = soup.find(string=re.compile("13.11.2025"))
if content:
    parent = content.parent
    print(f"Content Parent: {parent.name}, class: {parent.get('class')}")
    print(f"Content Grandparent: {parent.parent.name}, class: {parent.parent.get('class')}")
    print(f"Content GGrandparent: {parent.parent.parent.name}, class: {parent.parent.parent.get('class')}")
