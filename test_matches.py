import requests
import re
from src.services.text_cleaner import clean_campaign_text

url = "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl"
html = requests.get(url, verify=False).text
# We can bypass clean_campaign_text and just run the title logic
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, "html.parser")
for element in soup(["script", "style", "nav", "footer", "header", "noscript", "meta", "iframe", "svg", "link", "aside", "title"]):
    element.decompose()
raw_text = soup.get_text(separator="\n", strip=True)
raw_text = "Sayfa Başlığı: Silver logolu Mastercard’ınıza özel Galataport’ta otopark 1 TL!\n\n" + raw_text
raw_text = re.sub(r'[ \t]+', ' ', raw_text)
lines = raw_text.split('\n')
flattened = []
current_p = ""
for line in lines:
    l = line.strip()
    if not l: continue
    if re.match(r'^[\s\-_•*]*[A-ZÇĞİÖŞÜ0-9]', l) and len(l) > 1:
        if current_p: flattened.append(current_p)
        current_p = l
    else:
        if current_p: current_p += " " + l
        else: current_p = l
if current_p: flattened.append(current_p)
final_text = "\n".join(flattened)

title_to_find = "Silver logolu Mastercard’ınıza özel Galataport’ta otopark 1 TL!"
words = title_to_find.split()
first_few_words = " ".join(words[:3])

print(f"first_few_words: {first_few_words}")
matches = list(re.finditer(re.escape(first_few_words), final_text, re.IGNORECASE))
for i, m in enumerate(matches):
    print(f"Match {i}: start={m.start()}, text={final_text[m.start():m.start()+100]}")
