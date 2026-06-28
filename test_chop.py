import requests
import re
from src.services.text_cleaner import clean_campaign_text

url = "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-galataportta-otopark-1-tl"
html = requests.get(url, verify=False).text
# Run clean_campaign_text with prints inside it, or just copy its exact logic for niche
from bs4 import BeautifulSoup
soup = BeautifulSoup(html, "html.parser")
for element in soup(["script", "style", "nav", "footer", "header", "noscript", "meta", "iframe", "svg", "link", "aside", "title"]):
    element.decompose()
raw_text = soup.get_text(separator="\n", strip=True)
raw_text = "Sayfa Başlığı: Silver logolu Mastercard’ınıza özel Galataport’ta otopark 1 TL! | Kampanyalar: Adios Card ile Kazançlı Fırsatlar\n\n" + raw_text
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

final_text = final_text[1607:].strip() # After title chop

niche_nav_chop_markers = [
    "Crystal Kart İle Kazanmanın En Kolay Yolu",
    "Crystal Dünyası Crystal Nedir",
    "Ara Crystal Dünyası",
    "Crystal Nedir? Crystal Kredi Kartı Başvurusu",
    "Yurt İçi Anlaşmalı Otel Restoran İndirimleri",
    "Crystal Ek Kart Varlığa Bağlı Crystal Ayrıcalıkları",
    "Adios Kart İle Kazanmanın En Kolay Yolu",
    "Ara Adios Dünyası Adios Nedir",
    "Adios Dünyası Adios Nedir",
    "Adios Nedir? Adios Ayrıcalıkları",
    "Adios Nedir? Adios Kredi Kartı Başvuru",
    "Kampanyalar: Adios Card ile Kazançlı",
    "Play Kart İle Kazanmanın En Kolay Yolu",
    "Play Nedir? Play Kredi Kartı Başvuru",
    "Play Kredi Kartı Başvuru Puan Puan Kazanma",
    "Kampanyalar: Yapı Kredi Play Kampanyaları",
    "Yapı Kredi Play Kampanyaları - G",
]
for marker in niche_nav_chop_markers:
    match = re.search(re.escape(marker), final_text, re.IGNORECASE)
    if match:
        print(f"Matched '{marker}' at {match.start()}")
