import sys
import re

html_script = open("scratch/test_max_extract_full.py").read()

sys.path.append("/Users/hipoglisemi/Desktop/kartavantaj-scraper")
from src.services.text_cleaner import clean_campaign_text

with open('scratch/max_hepsi.html', 'r', encoding='utf-8') as f:
    html = f.read()

from bs4 import BeautifulSoup
soup = BeautifulSoup(html, "html.parser")

content_parts = []
selectors = [".page-content", "section div.container", ".detail-text", ".campaign-content", ".text-area", ".content", ".content-part", "table"]
for sel in selectors:
    containers = soup.select(sel)
    for container in containers:
        text = container.get_text(separator="\n", strip=True)
        if len(text) > 150 and "Ana Sayfa" not in text[:80] and "Maximum Mobil" not in text[:50]:
            is_duplicate = False
            for existing_part in content_parts:
                if text[:100] in existing_part or existing_part[:100] in text:
                    is_duplicate = True
                    break
            if not is_duplicate:
                content_parts.append(text)

raw_text = "\n---\n".join(content_parts)

tr_map = {ord('I'): 'ı', ord('İ'): 'i', ord('Ş'): 'ş', ord('Ğ'): 'ğ', ord('Ç'): 'ç', ord('Ö'): 'ö', ord('Ü'): 'ü'}
text_lower = raw_text.translate(tr_map).lower()

noise_markers = [
    r"çerez aydınlatma metni", r"zorunlu çerezler", r"daha fazla bilgi için", r"benzer (kampanyalar|fırsatlar)", r"diğer (kampanyalar|fırsatlar)", r"ilginizi çekebilecek kampanyalar", r"ilginizi çekebilir", r"sizin için seçtiklerimiz", r"popüler markalar", r"bizi takip edin", r"site haritası", r"tüm hakları saklıdır", r"copyright", r"en çok tercih edilen kredi kartlarını keşfedin", r"fırsatlardan hemen yararlanın", r"seveni, kullananı, bedavası en bol", r"başvurunuzu hemen yapın", r"deniz bonus.*en çok tercih edilen", r"axess mobil.*hemen indir", r"app store ile indir", r"google play ile indir", r"mesajınız gönderildi", r"ana sayfaya dön", r"merak ettikleriniz", r"sıkça sorulan sorular", r"başvurum nerede", r"kart şifresi al", r"faiz ve ücretler", r"hesap özeti açıklamaları", r"kişisel verilerin işlenmesi aydınlatma metni", r"bireysel müşteri aydınlatma metni", r"veri sorumlusu sıfatıyla", r"e-?mail toplama ve gönderim", r"kampanyayı paylaş", r"maximum mobil.*indir", r"bonusflaş.*indirmek için", r"bonusflaş.*ı indirin", r"cüzdan\s+kampanyalar\s+ödemeler\s+kartlar", r"qr kod okuyucu", r"sosyal medya\s+her hakkı", r"her hakkı.*\.a\.ş", r"çerez politikası\s+bize ulaşın", r"bize ulaşın\s+sosyal medya", r"biten kampanyalar", r"şekerbank\s+troy\s+thy\s+kampanyası", r"kampanyası\s+\w+\s+kampanyası\s+\w+\s+kampanyası", r"retreat kampanyası\s+restoran kampanyası", r"bi\s+dünya\s+fırsat\s+şimdi\s+koçtaş", r"tümü\s*\(\d+\)\s*eğitim\s*\(\d+\)", r"ilk bakışta türk telekom", r"hemen\s+indir\s+veya\s+app\s+store", r"jüzdan.*ı\s+indir", r"prev\s+next\s+\w+\s+servis", r"detaylı\s+bilgi\s+prev\s+next", r"ilginizi çekebilecek diğer kampanyalar", r"benzer fırsatları kaçırmayın", r"diğer kampanyalara göz atın", r"vodafone\s+yanımda.*indir", r"turkcell\s+dijital\s+operatör", r"444 0 333 shop&fly kolay seyahat hattı", r"çeşitli markalardaki dilediğiniz ayrıcalığı keşfedin", r"popüler aramalar", r"bize ulaşın sosyal medya", r"incelemek için tıklayın", r"hemen giriş yapın", r"daha fazla kampanya", r"giriş yaptıktan sonra", r"kampanya detayına geri dön", r"ödeme kanallarını göster", r"çok nays şeyler paylaşıyoruz", r"neler yapabilirisin, nasıl kazanırsın", r"nays dünyasını keşfet", r"altın al/sat biriktir", r"sevdiklerini nays'a davet et"
]

for m in noise_markers:
    match = re.search(m, text_lower)
    if match:
        print(f"Matched marker: {m} at index {match.start()}")

# Also check og_title
title = "Hepsiburada’da Peşin Fiyatına 6 Taksit Fırsatı!"
safe_title_regex = re.escape(title.lower().translate(tr_map))
match_t = re.search(safe_title_regex, text_lower)
if match_t:
    print(f"Matched TITLE exactly at {match_t.start()}")
else:
    print("NO exact title match found in text_lower!")
