import os
import sys
import json
import time
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker, joinedload

# Setup paths and environment
sys.path.append(os.getcwd())
load_dotenv()

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
Sen uzman bir kampanya koşulları analizcisisin. Verilen kampanya metnini okuyarak HANGİ KARTLARIN KAMPANYAYA DAHİL OLDUĞUNU (eligible_cards) ve HANGİ KARTLARIN DAHİL OLMADIĞINI (excluded_cards) tespit edeceksin. Ayrıca metinde bu kart bilgisinin/koşullarının geçtiği tam cümleleri (card_section_text) alacaksın.

KURALLAR:
1. Sadece metinde açıkça geçen kartları al.
2. Önce "Dahil Olan Kartlar" ve "Hariç Olan Kartlar" listesini zihninde oluştur.
3. Sonra "Dahil Olan Kartlar" listesinden, eğer bir kart aynı zamanda "Hariç Olan Kartlar" listesindeyse (örneğin "Tüm Axess kartlar geçerli, Axess Business hariç" ise Axess Business'ı çıkar).
4. İlgili bankanın adını da göz önünde bulundurarak çıkarımlarını yap.
5. "card_section_text" alanına, metinde kart koşullarının veya geçerlilik kurallarının geçtiği orijinal cümleyi/bölümü birebir kopyala.

Yanıtını YALNIZCA aşağıdaki JSON formatında ver, başka hiçbir metin ekleme:
{
    "eligible_cards": ["Kart 1", "Kart 2"],
    "excluded_cards": ["Kart 3"],
    "card_section_text": "Metinden kartların geçtiği bölüm..."
}
"""

def extract_cards_via_ai(clean_text: str, bank_name: str) -> tuple:
    prompt = f"Banka Adı: {bank_name}\n\nKampanya Metni:\n{clean_text[:3000]}\n\nLütfen sadece dahil olan ve hariç tutulan kartları ve ilgili cümleleri JSON formatında dön."
    
    max_retries = 5
    backoff = 2
    
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
            return data.get("eligible_cards", []), data.get("card_section_text", "")
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                sleep_time = (backoff ** attempt) + 5
                print(f"   ⚠️ Rate limit (429) hit. Retrying in {sleep_time}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(sleep_time)
            else:
                print(f"AI Error: {e}")
                return [], ""
    return [], ""

import re

def normalize_card_name(name: str) -> str:
    if not name or name == "-":
        return ""
    # 1. Lowercase and replace turkish characters
    name = name.lower()
    turkish_map = {
        "ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"
    }
    for tr, eng in turkish_map.items():
        name = name.replace(tr, eng)
    
    # 2. Replace whole words or common phrase combinations using regex with word boundaries
    noise_patterns = [
        r"\bbonus\s+ozellikli\b", r"\bozellikli\b", r"\bbonus\b", r"\bbireysel\b",
        r"\btumu\b", r"\btum\b", r"\bhepsi\b", r"\bkullanicilari\b", r"\bkullanicisi\b",
        r"\bmusterileri\b", r"\bmusterisi\b", r"\bsahipleri\b", r"\bsahibi\b",
        r"\blogolu\b", r"\bkazandiran\b", r"\blira\b", r"\bpuan\b", r"\btl\b",
        r"\bayricaligi\b", r"\bayricalik\b",
        r"\bkredi\s+kartlari\b", r"\bkredi\s+karti\b", r"\bkredi\b",
        r"\bkartlari\b", r"\bkartlar\b", r"\bkarti\b", r"\bkart\b"
    ]
    for pattern in noise_patterns:
        name = re.sub(pattern, "", name)
        
    # 3. Strip non-alphanumeric characters and collapse spaces
    name = re.sub(r'[^a-z0-9]', '', name)
    
    return name.strip()

import argparse

def main():
    parser = argparse.ArgumentParser(description="Audit campaign eligible cards against clean text via Gemini AI.")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of campaigns to audit.")
    args = parser.parse_args()

    db = next(get_db())
    
    query = db.query(Campaign).options(
        joinedload(Campaign.card).joinedload(Card.bank)
    ).filter(
        Campaign.clean_text != None,
        Campaign.is_active == True
    ).order_by(Campaign.id.desc())
    
    if args.limit is not None:
        query = query.limit(args.limit)
        
    campaigns = query.all()

    print(f"Total campaigns to audit: {len(campaigns)}")
    
    results_file = "card_audit_report.json"
    audit_results = []
    
    count = 0
    mismatch_count = 0
    
    for camp in campaigns:
        count += 1
        print(f"[{count}/{len(campaigns)}] Auditing ID: {camp.id} - {camp.title[:40]}...")
        
        # Bank adını bul
        bank_name = "Bilinmeyen Banka"
        if camp.card and camp.card.bank:
            bank_name = camp.card.bank.name
            
        current_cards_str = camp.eligible_cards or ""
        current_cards_list = [c.strip() for c in current_cards_str.split(",")] if current_cards_str else []
        
        # Sadece yeterli uzunlukta metni varsa AI'a gönder
        if not camp.clean_text or len(camp.clean_text) < 50:
            continue
            
        ai_cards, card_section = extract_cards_via_ai(camp.clean_text, bank_name)
        
        # Karşılaştırma yap (Büyük/Küçük harf duyarsız ve normalize edilmiş set karşılaştırması)
        current_set = {normalize_card_name(c) for c in current_cards_list if c}
        ai_set = {normalize_card_name(c) for c in ai_cards if c}
        
        # Boş elemanları filtrele
        current_set = {x for x in current_set if x}
        ai_set = {x for x in ai_set if x}
        
        # Eşitsizlik varsa
        if current_set != ai_set:
            mismatch_count += 1
            print(f"  ❌ MISMATCH DETECTED!")
            print(f"     DB: {current_cards_list}")
            print(f"     AI: {ai_cards}")
            print(f"     Text Section: {card_section}")
            
            audit_results.append({
                "campaign_id": camp.id,
                "title": camp.title,
                "url": camp.tracking_url,
                "db_cards": current_cards_list,
                "ai_proposed_cards": ai_cards,
                "card_section_in_text": card_section
            })
            
            # Raporu anlık kaydet
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(audit_results, f, ensure_ascii=False, indent=2)
                
        else:
            print(f"  ✅ MATCH")
            
        # API limitlerini korumak için küçük bekleme
        time.sleep(0.5)

    print(f"\\nAudit Completed. {mismatch_count} mismatches found out of {count} campaigns.")
    print(f"Report saved to {results_file}")

if __name__ == "__main__":
    main()
