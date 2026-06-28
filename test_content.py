import requests
from bs4 import BeautifulSoup
url = "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl"
html = requests.get(url, verify=False).text
soup = BeautifulSoup(html, "html.parser")
h1 = soup.find("h1")
print(f"H1: {h1}")
print(f"H1 Parent: {h1.parent.name}, class: {h1.parent.get('class')}")
print(f"H1 Grandparent: {h1.parent.parent.name}, class: {h1.parent.parent.get('class')}")

content = soup.find(text="13.11.2025 -")
if content:
    parent = content.parent
    print(f"Content Parent: {parent.name}, class: {parent.get('class')}")
    print(f"Content Grandparent: {parent.parent.name}, class: {parent.parent.get('class')}")
    print(f"Content GGrandparent: {parent.parent.parent.name}, class: {parent.parent.parent.get('class')}")
