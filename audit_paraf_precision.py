import os
import sys
import json
import time
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
3. "eligible_cards": Kampanyaya dahil olan geçerli Paraf kartlarını listele (Örn: Paraf, Parafly, Parafree, Paraf Genç, Paraf Debit, Paraf Esnaf, Paraf KOBİ, Paraf Business, Eczacı Paraf, Halkcard vb.). 
   - 🚨 Hariç tutulan (dahil değildir denilen) kartları kesinlikle buraya ekleme!
   - 🚨 Eğer metinde "Halkcard dahil değildir" veya "Paraf Genç dahil değildir" gibi bir hariç tutma varsa, bunları "eligible_cards" listesine ASLA ekleme!

Yanıtını YALNIZCA aşağıdaki JSON formatında ver, başka hiçbir açıklama veya metin ekleme:
{
    "header_type": "Tespit edilen başlık",
    "card_section_text": "Metinden izole edilen kart geçerlilik bölümü...",
    "eligible_cards": ["Paraf", "Parafly", "Parafree"]
}
"""

def analyze_campaign(camp):
    if not camp.clean_text or len(camp.clean_text) < 30:
        return {
            "id": camp.id,
            "title": camp.title,
            "header_type": "Metin Yetersiz",
            "card_section_text": "Kampanya metni bulunamadı veya çok kısa.",
            "db_eligible_cards": camp.eligible_cards or "Boş",
            "proposed_cards": []
        }
        
    prompt = f"Banka Adı: Halkbank / Paraf\n\nKampanya Metni:\n{camp.clean_text[:4000]}\n\nLütfen kurallara göre JSON dön."
    
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
            return {
                "id": camp.id,
                "title": camp.title,
                "header_type": data.get("header_type", "Bulunamadı (Giriş Metni Taranıyor)"),
                "card_section_text": data.get("card_section_text", "Metinden kartların geçtiği bölüm..."),
                "db_eligible_cards": camp.eligible_cards or "Boş",
                "proposed_cards": data.get("eligible_cards", [])
            }
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(2 * (attempt + 1))
            else:
                time.sleep(1)
                
    return {
        "id": camp.id,
        "title": camp.title,
        "header_type": "Hata",
        "card_section_text": "Analiz sırasında hata oluştu.",
        "db_eligible_cards": camp.eligible_cards or "Boş",
        "proposed_cards": []
    }

def main():
    db = next(get_db())
    
    # Active Halkbank/Paraf campaigns
    campaigns = db.query(Campaign).join(Campaign.card).join(Card.bank).filter(
        Bank.slug == "halkbank",
        Campaign.is_active == True
    ).order_by(Campaign.id.desc()).all()
    
    total = len(campaigns)
    print(f"Starting audit for {total} active Paraf campaigns...")
    
    results = []
    
    # Run with 8 threads (to match Gemini keys pool)
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_camp = {executor.submit(analyze_campaign, c): c for c in campaigns}
        
        count = 0
        for future in as_completed(future_to_camp):
            count += 1
            res = future.result()
            results.append(res)
            if count % 10 == 0 or count == total:
                print(f"Progress: {count}/{total} completed.")
                
    # Sort results by campaign ID descending to keep consistent order
    results.sort(key=lambda x: x["id"], reverse=True)
    
    # Generate Markdown Report
    report_path = "/Users/hipoglisemi/Desktop/kartavantaj/paraf_precision_audit_report.md"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 💳 Kartavantaj Paraf Kampanya Kart Eşleştirme Raporu (Hassas Denetim)\n\n")
        f.write(f"Bu rapor, sistemdeki tüm **{total}** Paraf (Halkbank) kampanyasının web sitesinden kazınan ham metnindeki (`cleanText`) **\"Kampanyaya Dahil Olan Kartlar\"** bölümünü izole ederek çıkartılan kart listesini listeler.\n\n")
        f.write(f"> [!IMPORTANT]\n")
        f.write(f"> Metin içindeki **hariç tutulan** (dahil olmayan) kartlar tamamen elenmiş ve sadece dahil olan kartlar resmi metindeki **ilk geçiş sırasına göre** listelenmiştir.\n\n")
        f.write(f"---\n\n")
        
        for res in results:
            f.write(f"### 🏷️ Kampanya #{res['id']} - {res['title']}\n")
            f.write(f"- **Bulunan Başlık Tipi:** `\"{res['header_type']}\"`\n")
            f.write(f"- **Metinden İzole Edilen Dahil Olan Bölüm:**\n")
            # Format blockquote beautifully
            clean_section = res['card_section_text'].replace('\n', ' ').strip()
            f.write(f"  > *\"{clean_section}\"*\n")
            
            # Format proposed cards beautifully as a clean comma-separated list
            proposed_str = ", ".join(res["proposed_cards"]) if res["proposed_cards"] else "Boş"
            f.write(f"- **Geçerli Kartlar Kolonu (Nihai):** `{proposed_str}`\n\n")
            f.write(f"---\n\n")
            
    print(f"Audit completed! Report successfully saved to {report_path}")

if __name__ == "__main__":
    main()
