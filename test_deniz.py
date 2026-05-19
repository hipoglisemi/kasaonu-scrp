import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from bs4 import BeautifulSoup

url = "https://www.denizbonus.com/kampanyalar/market-alisverislerinize-500-tl-bonus"
response = requests.get(url, verify=False, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(response.text, "html.parser")

for tag in soup.find_all(lambda t: t.name in ["h1", "h2", "h3", "h4", "h5", "h6", "strong", "div"] and t.text and "KATILMAK İÇİN" in t.text):
    print("Found KATILMAK ICIN in tag:", tag.name, "class:", tag.get("class"))
    if tag.name != "div":
        print(tag.parent.text[:200])

print("---")
print(soup.find('body').text[:500])
