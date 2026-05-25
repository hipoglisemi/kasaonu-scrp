import os
import sys
import json
import time
import re
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker, joinedload
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup paths and environment
sys.path.append("/Users/hipoglisemi/Desktop/kartavantaj-scraper")
load_dotenv("/Users/hipoglisemi/Desktop/kartavantaj-scraper/.env")

from src.database import get_db
from src.models import Campaign, Bank, Card
from google import genai
from google.genai import types

# Setup Gemini API Keys Pool
API_KEYS = []
if os.getenv("GEMINI_API_KEY"):
    API_KEYS.append(os.getenv("GEMINI_API_KEY"))
for i in range(1, 10):
    k = os.getenv(f"GEMINI_API_KEY_{i}")
    if k:
        API_KEYS.append(k)

if not API_KEYS:
    raise ValueError("No Gemini API keys found in environment!")

print(f"Loaded {len(API_KEYS)} API keys for rotation.")

_key_index = 0
def get_next_client():
    global _key_index
    key = API_KEYS[_key_index]
    _key_index = (_key_index + 1) % len(API_KEYS)
    return genai.Client(api_key=key)

MODEL_NAME = os.getenv("GEMINI_FAST_MODEL", "gemini-3.1-flash-lite")

SYSTEM_INSTRUCTION = """
Sen uzman bir banka kampanya koşulları denetçisisin. Verilen kampanya metnini (cleanText) inceleyerek HANGİ KARTLARIN DAHİL OLDUĞUNU (eligible_cards), hangi başlık altından çıkarıldığını (header_type) ve metinde bu kart listesinin geçtiği ham cümleyi/paragrafı (card_section_text) tespit edeceksin.

KURALLAR:
1. "header_type": Metinde geçen başlığı tam olarak tespit et. Örnek: "Kampanyaya dahil olan kartlar", "Kampanyaya dahil olan kartlar ve işlemler", "Kampanyaya katılabilen kartlar". Eğer doğrudan bir başlık yoksa ve giriş kısmından çıkarıyorsan "Bulunamadı (Giriş Metni Taranıyor)" yaz.
2. "card_section_text": Metinde kartların ve koşulların geçtiği orijinal bölümü/paragrafı kelimesi kelimesine kopyala.
3. "eligible_cards": Kampanyaya dahil olan geçerli Yapı Kredi kartlarını listele (Örn: Worldcard, World, Play, adios, Crystal, World Eko, World Platinum, Bireysel kredi kartları, Bireysel banka kartları, TLcard, Vakıfbank Worldcard, Albaraka Worldcard, Anadolubank Worldcard, Business, Sanal kartlar, Ek kartlar, TROY logolu kartlar, Mastercard logolu kartlar, Visa logolu kartlar vb.). 
   - 🚨 Hariç tutulan (dahil değildir denilen) kartları kesinlikle buraya ekleme!
   - 🚨 Eğer metinde "Vakıfbank Worldcard dahil değildir" veya "World Eko dahil değildir" gibi bir hariç tutma varsa, bunları "eligible_cards" listesine ASLA ekleme!
   - 🚨 Kartları metinde **ilk geçtikleri sıraya göre** listele! Sıralama metinle birebir aynı olmalı.

Yanıtını YALNIZCA aşağıdaki JSON formatında ver, başka hiçbir açıklama veya metin ekleme:
{
    "header_type": "Tespit edilen başlık",
    "card_section_text": "Metinden izole edilen kart geçerlilik bölümü...",
    "eligible_cards": ["Worldcard", "Play", "TLcard"]
}
"""

def normalize(name: str) -> str:
    if not name:
        return ""
    name = name.lower()
    turkish_map = {"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}
    for tr, eng in turkish_map.items():
        name = name.replace(tr, eng)
    # Apostrophe temizle ("TLcard'lar" → "TLcardlar", "World'le" → "Worldle")
    name = name.replace("'", "").replace("'", "")
    # Gürültü kelimeleri temizle
    for word in ["kartlari", "karti", "kartlar", "kart", "logolu", "ozellikli", "bireysel"]:
        name = re.sub(rf"\b{word}\b", "", name)
    return "".join(name.split())

def analyze_campaign(camp):
    if not camp.clean_text or len(camp.clean_text) < 30:
        return None
        
    prompt = f"Banka Adı: Yapı Kredi / World\n\nKampanya Metni:\n{camp.clean_text[:4000]}\n\nLütfen kurallara göre JSON dön."
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            client = get_next_client()
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.0,
                    response_mime_type="application/json"
                ),
            )
            data = json.loads(response.text)
            
            # Database values
            db_cards_str = camp.eligible_cards or ""
            db_cards = [c.strip() for c in db_cards_str.split(",") if c.strip()]
            ai_cards = data.get("eligible_cards", [])
            
            # Post-process AI cards using our proprietary validator to match database pipeline output
            from src.services.card_validator import CardValidator
            from src.services.ai_parser_golden import BANK_CARD_KEYWORDS
            validator = CardValidator(BANK_CARD_KEYWORDS)
            ai_cards = validator.validate(ai_cards, camp.clean_text, "yapı kredi")
            
            # Normalization and Comparison
            db_norm = [normalize(x) for x in db_cards if x]
            ai_norm = [normalize(x) for x in ai_cards if x]
            
            is_match = db_norm == ai_norm
            
            missing = []
            for card in ai_cards:
                if normalize(card) not in db_norm:
                    missing.append(card)
                    
            extra = []
            for card in db_cards:
                if normalize(card) not in ai_norm:
                    extra.append(card)
                    
            order_wrong = False
            if not missing and not extra and db_norm != ai_norm:
                order_wrong = True
                
            return {
                "id": camp.id,
                "title": camp.title,
                "url": camp.tracking_url,
                "header_type": data.get("header_type", "Bulunamadı (Giriş Metni Taranıyor)"),
                "card_section_text": data.get("card_section_text", ""),
                "db_cards": db_cards,
                "ai_proposed": ai_cards,
                "is_match": is_match,
                "missing": missing,
                "extra": extra,
                "order_wrong": order_wrong
            }
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(2 * (attempt + 1))
            else:
                time.sleep(1)
                
    return None

def main():
    db = next(get_db())
    
    campaigns = db.query(Campaign).join(Campaign.card).join(Card.bank).filter(
        Bank.slug == "yapi-kredi",
        Campaign.is_active == True
    ).order_by(Campaign.id.desc()).all()
    
    total = len(campaigns)
    print(f"Starting precision mismatch audit for {total} Yapı Kredi campaigns...")
    
    results = []
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_camp = {executor.submit(analyze_campaign, c): c for c in campaigns}
        
        count = 0
        for future in as_completed(future_to_camp):
            count += 1
            res = future.result()
            if res:
                results.append(res)
            if count % 10 == 0 or count == total:
                print(f"Progress: {count}/{total} audited.")
                
    results.sort(key=lambda x: x["id"], reverse=True)
    
    mismatch_list = [r for r in results if not r["is_match"]]
    mismatch_count = len(mismatch_list)
    match_count = total - mismatch_count
    
    report_path = "/Users/hipoglisemi/Desktop/kartavantaj/yapi_kredi_precision_mismatch_report.md"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 🔍 Yapı Kredi Kampanya Kart Eşleştirme Karşılaştırma Raporu (Hassas Denetim)\n\n")
        f.write(f"Bu denetim raporu, sistemdeki **{total}** aktif Yapı Kredi (Worldcard) kampanyasının veri tabanındaki `eligible_cards` sütunu ile metinden kelimesi kelimesine çıkarılan **AI Önerilen Sıralı Listeyi** karşılaştırır.\n\n")
        f.write(f"## 📊 Genel Özet\n")
        f.write(f"- **Toplam Denetlenen Kampanya:** `{total}`\n")
        f.write(f"- **Tam Eşleşen (Kusursuz):** `{match_count}` (%{round(match_count/total*100, 2)})\n")
        f.write(f"- **Uyuşmazlık Bulunan:** `{mismatch_count}` (%{round(mismatch_count/total*100, 2)})\n\n")
        
        f.write(f"> [!IMPORTANT]\n")
        f.write(f"> Hatalar üç sınıfta kategorize edilmiştir:\n")
        f.write(f"> 1. **Eksik Kartlar:** Banka metninde geçtiği halde DB'de yazılmayan kartlar.\n")
        f.write(f"> 2. **Fazla Kartlar:** Metinde geçmediği halde DB'de fazladan yazılmış olan kartlar.\n")
        f.write(f"> 3. **Hatalı Sıralama:** Kartlar doğru ancak metindeki resmi geçiş sırasına göre yazılmamış olanlar.\n\n")
        f.write(f"---\n\n")
        
        f.write(f"## 🚨 Uyuşmazlık Detayları\n\n")
        
        for res in mismatch_list:
            f.write(f"### 🏷️ Kampanya #{res['id']} - {res['title']}\n")
            f.write(f"- **Bulunan Başlık Tipi:** `\"{res['header_type']}\"`\n")
            f.write(f"- **Metinden İzole Edilen Dahil Olan Bölüm:**\n")
            clean_section = res['card_section_text'].replace('\n', ' ').strip()
            f.write(f"  > *\"{clean_section}\"*\n")
            
            f.write(f"- **Veri Tabanındaki Mevcut Kartlar:** `{', '.join(res['db_cards']) if res['db_cards'] else 'Boş'}`\n")
            f.write(f"- **AI Önerilen Sıralı Liste:** `{', '.join(res['ai_proposed']) if res['ai_proposed'] else 'Boş'}`\n")
            
            # Error descriptions
            errors = []
            if res["missing"]:
                errors.append(f"🔴 **Eksik Kartlar:** `{', '.join(res['missing'])}`")
            if res["extra"]:
                errors.append(f"🟡 **Fazla Kartlar (DB'de Fazla):** `{', '.join(res['extra'])}`")
            if res["order_wrong"]:
                errors.append(f"🟠 **Hatalı Sıralama:** (Kart isimleri doğru ama metindeki geçiş sırası yanlış)")
                
            f.write(f"- **Hata Teşhisi:**\n")
            for err in errors:
                f.write(f"  - {err}\n")
                
            f.write(f"\n---\n\n")
            
    print(f"Mismatch audit completed! Report saved to {report_path}")

if __name__ == "__main__":
    main()
