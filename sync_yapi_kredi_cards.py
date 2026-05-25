"""
Yapı Kredi Eligible Cards - AI Destekli Kesin Tarama (v2)
===========================================================
YAKLAŞIM:
  - AI'ya çok spesifik bir Yapı Kredi odaklı prompt gönderilir.
  - System prompt: Sadece açıkça "dahil/geçerli" denilen kart türlerini listele.
  - "World Mobil", "Worldpuan", "World POS" gibi ibareler kart DEĞİLDİR.
  - "ek kartlar ile yapılan harcamalar dahildir" → "ek kartlar" kart DEĞİLDİR,
    bu bir işlem kapsamı ifadesidir (kapsama giren işlemler, kart değil).
  - Sonuçlar CardValidator'dan geçirilir (prefix distribution, dedup).
  - AI olmadan yapılamaz çünkü bağlam (context) gerekli.
"""

import sys, json, time
sys.path.insert(0, "/Users/hipoglisemi/Desktop/kartavantaj-scraper")

from dotenv import load_dotenv
load_dotenv("/Users/hipoglisemi/Desktop/kartavantaj-scraper/.env")

import os
from src.database import get_db
from src.models import Campaign, Bank, Card
from src.services.card_validator import CardValidator
from src.services.ai_parser_golden import BANK_CARD_KEYWORDS
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types

# ─────────────────────────────────────────────────────────────
# API Key Rotation
# ─────────────────────────────────────────────────────────────
API_KEYS = [k for k in [os.getenv("GEMINI_API_KEY")] + [os.getenv(f"GEMINI_API_KEY_{i}") for i in range(1, 10)] if k]
print(f"Loaded {len(API_KEYS)} API keys for rotation.")
_key_idx = 0

def get_client():
    global _key_idx
    key = API_KEYS[_key_idx % len(API_KEYS)]
    _key_idx += 1
    return genai.Client(api_key=key)

MODEL = "gemini-3.1-flash-lite"

# ─────────────────────────────────────────────────────────────
# System Prompt — Yapı Kredi Odaklı, Kesin Kural Tabanlı
# ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
Sen Yapı Kredi kampanya metinlerini analiz eden bir uzman sistemsin.

Görevin: Verilen kampanya metnini okuyarak, kampanyaya HANGİ KART TÜRLERİNİN DAHİL OLDUĞUNU tespit etmek.

## KART TESPİT KURALLARI

### Geçerli kart belirteçleri (bunları listele):
- "Crystal kart", "Crystal", "Metal Crystal"
- "adios", "adios Premium"
- "Yapı Kredi Play", "Play Kredi Kartı"
- "Worldcard", "world" (sadece kart olarak geçiyorsa)
- "Vakıfbank Worldcard", "Albaraka Worldcard", "Anadolubank Worldcard"
- "bireysel kredi kartları", "bireysel kredi kartı"
- "bireysel TLcard", "bireysel TLcard'lar", "TLcard", "tl card"
- "Mastercard logolu bireysel kredi kartları", "Mastercard logolu TLcard"
- "TROY logolu bireysel kredi kartları", "Visa logolu bireysel kredi kartları"
- "Mastercard logolu metal Crystal kart", "Mastercard logolu Crystal kart"
- "debit kart", "banka kartı", "banka kartları"
- "ek kartlar", "sanal kartlar" (SADECE ana kart zaten listedeyse, bağımsız EKLEME)
- "Silver logolu Mastercard"
- "Yapı Kredi bireysel kredi kartları"

### KART DEĞİL — asla listeye ekleme:
- "World Mobil" → uygulama adı, kart değil
- "Worldpuan" → puan birimi, kart değil
- "World POS" → POS terminali, kart değil
- "World Pay" → ödeme sistemi, kart değil
- "World Üye İşyeri" → işyeri ağı, kart değil
- "Worldcard kampanyası" → kampanya adı, kart değil
- "bireysel müşteriler" → müşteri segmenti, kart değil
- "tüm kartlar" → çok genel, Yapı Kredi'ye özgü değil

### BAĞLAM KURALLARI:
1. "ek kartlar ile yapılan harcamalar dahildir" → "ek kartlar" EKLENİR (işlem kapsamı ama kart da dahil)
2. "ek kartlar dahil değildir" → EKLENMEZ
3. "Crystal kart müşterileri" → "Crystal" EKLENİR
4. "bireysel kredi kartı ile yapılan alışverişler geçerlidir" → "bireysel kredi kartları" EKLENİR
5. Mastercard/TROY/Visa prefix'i açıkça yazıyorsa, prefix'siz genel kart EKLENMEz
   - Örn: "Mastercard logolu bireysel kredi kartları" yazıyorsa sadece "bireysel kredi kartları" EKLENMEz
6. "Crystal kartı ile" → sadece Crystal, "Yapı Kredi bireysel kredi kartları" EKLENMEz

## ÇIKTI FORMATI
Sadece kart adlarını JSON array olarak döndür. Sırası metindeki geçiş sırasına göre olmalı.
Örnek: ["Crystal kart", "ek kartlar"]
Kart bulunamadıysa: []
"""

def process_campaign(camp):
    text = camp.clean_text or camp.description or ""
    if not text.strip():
        return {"id": camp.id, "title": camp.title, "old": camp.eligible_cards, "new_raw": [], "error": "BOŞ METİN"}

    client = get_client()
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=f"Kampanya Metni:\n{text[:3000]}",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "eligible_cards": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"}
                            }
                        },
                        "required": ["eligible_cards"]
                    }
                )
            )
            data = json.loads(response.text)
            ai_cards = data.get("eligible_cards", [])
            return {"id": camp.id, "title": camp.title, "old": camp.eligible_cards, "new_raw": ai_cards, "error": None}
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(3 * (attempt + 1))
            else:
                time.sleep(1)
    return {"id": camp.id, "title": camp.title, "old": camp.eligible_cards, "new_raw": [], "error": "MAX_RETRY"}


def main():
    db = next(get_db())
    validator = CardValidator(BANK_CARD_KEYWORDS)

    campaigns = db.query(Campaign).join(Campaign.card).join(Card.bank).filter(
        Bank.slug == "yapi-kredi",
        Campaign.is_active == True
    ).all()

    total = len(campaigns)
    print(f"Taranacak kampanya: {total}")
    print("=" * 60)

    results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(process_campaign, c): c for c in campaigns}
        done = 0
        for future in as_completed(futures):
            done += 1
            res = future.result()
            results.append(res)
            if done % 30 == 0 or done == total:
                print(f"  İlerleme: {done}/{total}")

    # Doğrulama ve DB güncelleme
    updated = 0
    errors = []
    no_cards = []

    for res in results:
        if res["error"]:
            errors.append(res)
            continue

        c = db.query(Campaign).filter(Campaign.id == res["id"]).first()
        if not c:
            continue

        text = c.clean_text or c.description or ""

        # CardValidator'dan geçir (prefix distribution, dedup)
        validated = validator.validate(res["new_raw"], text, "yapı kredi")
        new_eligible = ", ".join(validated) if validated else None

        if not validated:
            no_cards.append(res)

        if new_eligible != c.eligible_cards:
            print(f"✏️  #{c.id} {c.title[:50]}")
            print(f"     ESKİ: {c.eligible_cards}")
            print(f"     YENİ: {new_eligible}")
            c.eligible_cards = new_eligible
            updated += 1

    db.commit()

    print("\n" + "=" * 60)
    print(f"✅ Güncellenen: {updated}/{total}")
    if errors:
        print(f"\n⚠️  Hata olan kampanyalar ({len(errors)}):")
        for e in errors:
            print(f"  - #{e['id']} [{e['error']}] {e['title'][:50]}")
    if no_cards:
        print(f"\n⚠️  Kart bulunamayan kampanyalar ({len(no_cards)}):")
        for n in no_cards:
            print(f"  - #{n['id']} | DB was: {n['old']} | {n['title'][:50]}")
    print("\nSenkronizasyon tamamlandı.")


if __name__ == "__main__":
    main()
