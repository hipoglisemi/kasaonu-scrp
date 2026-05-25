import sys
import os
import time
import requests
import json
from dotenv import load_dotenv

# Setup paths and environment
sys.path.insert(0, "/Users/hipoglisemi/Desktop/kartavantaj-scraper")
load_dotenv("/Users/hipoglisemi/Desktop/kartavantaj-scraper/.env")

from src.database import get_db
from src.models import Campaign
from src.services.text_cleaner import clean_campaign_text
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

MODEL_NAME = os.getenv("GEMINI_FAST_MODEL", "gemini-3.1-flash-lite")

SYSTEM_INSTRUCTION = """
Sen uzman bir banka kampanya koşulları denetçisisin. Verilen kampanya metnini (cleanText) inceleyerek HANGİ KARTLARIN DAHİL OLDUĞUNU (eligible_cards), hangi başlık altından çıkarıldığını (header_type) ve metinde bu kart listesinin geçtiği ham cümleyi/paragrafı (card_section_text) tespit edeceksin.

KURALLAR:
1. "header_type": Metinde geçen başlığı tam olarak tespit et. Örnek: "Kampanyaya dahil olan kartlar", "Kampanyaya dahil olan kartlar ve işlemler", "Kampanyaya katılabilen kartlar". Eğer doğrudan bir başlık yoksa ve giriş kısmından çıkarıyorsan "Bulunamadı (Giriş Metni Taranıyor)" yaz.
2. "card_section_text": Metinde kartların ve koşulların geçtiği orijinal bölümü/paragrafı kelimesi kelimesine kopyala.
3. "eligible_cards": Kampanyaya dahil olan geçerli Yapı Kredi kartlarını listele (Örn: Worldcard, World, Play, adios, Crystal, World Eko, World Gold, World Platinum, TLcard, Yapı Kredi bireysel kredi kartları, Yapı Kredi banka kartları, Vakıfbank Worldcard, Albaraka Worldcard, Anadolubank Worldcard, Business, Sanal kartlar, Ek kartlar, TROY logolu kartlar, Mastercard logolu kartlar, Visa logolu kartlar vb.). 
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

def main():
    db = next(get_db())
    c = db.query(Campaign).filter(Campaign.id == 15978).first()
    if not c:
        print("Campaign 15978 not found in database!")
        return
        
    url = c.tracking_url
    print(f"Rescraping Campaign #{c.id}: {c.title}")
    print(f"URL: {url}")
    
    html = None
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200:
            html = resp.text
            print(f"Successfully fetched HTML via requests! Size: {len(html)} bytes")
        else:
            print(f"Failed with status code: {resp.status_code}")
    except Exception as e:
        print(f"Error fetching URL: {e}")
            
    if not html:
        print("Failed to fetch HTML. Aborting.")
        return
        
    # Use clean_campaign_text to get clean text
    clean_text = clean_campaign_text(html)
    print(f"Extracted clean text ({len(clean_text)} chars):")
    print("-" * 50)
    print(clean_text[:400])
    print("-" * 50)
    
    prompt = f"Banka Adı: Yapı Kredi / World\n\nKampanya Metni:\n{clean_text[:4000]}\n\nLütfen kurallara göre JSON dön."
    
    # Retry loop with key rotation
    parsed_successfully = False
    for i, key in enumerate(API_KEYS):
        print(f"Attempting parsing with Gemini API Key #{i}...")
        try:
            client = genai.Client(api_key=key)
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
            print(f"Gemini raw response: {data}")
            
            ai_cards = data.get("eligible_cards", [])
            
            # Apply validation logic
            from src.services.card_validator import CardValidator
            from src.services.ai_parser_golden import BANK_CARD_KEYWORDS
            validator = CardValidator(BANK_CARD_KEYWORDS)
            
            validated_cards = validator.validate(ai_cards, clean_text, "yapı kredi")
            eligible_cards_str = ", ".join(validated_cards)
            
            print(f"Validated Cards: {validated_cards}")
            print(f"Eligible Cards String: '{eligible_cards_str}'")
            
            # Update campaign in DB
            c.clean_text = clean_text
            c.eligible_cards = eligible_cards_str
            c.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")
            
            db.commit()
            print("🎉 SUCCESS: Campaign #15978 successfully updated in database!")
            parsed_successfully = True
            break
        except Exception as e:
            print(f"Error on API key #{i}: {e}")
            if "429" in str(e) or "quota" in str(e).lower():
                print("Rate limit reached. Rotating key...")
                continue
            else:
                break
                
    if not parsed_successfully:
        print("❌ FAILED: All Gemini API keys failed or rate-limited.")
        db.rollback()

if __name__ == "__main__":
    main()
