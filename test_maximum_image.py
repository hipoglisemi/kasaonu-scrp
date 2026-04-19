import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

url = "https://www.maximiles.com.tr/kampanyalar/manisa-da-hafta-ici-her-gun-ilk-ulasimin-is-bankasi-troy-logolu-kartlarla-ucretsiz"
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers)
soup = BeautifulSoup(resp.content, "html.parser")

og_img = soup.find("meta", property="og:image")
if og_img:
    print("META OG IMAGE:", og_img.get("content"))
    
    # Check all images on page
for img in soup.find_all("img"):
    print("IMG HTML:", str(img)[:100])
