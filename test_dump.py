import requests
from bs4 import BeautifulSoup

url = "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl"
html = requests.get(url, verify=False).text
soup = BeautifulSoup(html, "html.parser")

for element in soup(["script", "style", "nav", "footer", "header", "noscript", "meta", "iframe", "svg", "link", "aside", "title"]):
    element.decompose()

raw_text = soup.get_text(separator="\n", strip=True)
print("--- RAW TEXT ---")
print(raw_text[-2000:])
