"""
Bulk energetic AI Marketing Text Regenerator (Hardened & Unique)
======================================================
Kampanyaları benzersiz, enerjik ve emojili metinlere dönüştürür.
- Başlık tekrarını yasaklar.
- 503 (High Demand) hatalarına karşı dirençlidir.
- Checkpoint sistemiyle kaldığı yerden devam eder.
"""
import os
import sys
import time
import re
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    print("❌ DATABASE_URL bulunamadı.")
    sys.exit(1)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

from src.utils.gemini_client import generate_with_rotation
from google.genai import types as genai_types

CHECKPOINT_FILE = "marketing_update_checkpoint.json"

# Enerjik & Benzersiz Prompt
MARKETING_PROMPT = """Sen yaratıcı bir kredi kartı kampanya yazarıısın. 
Görevin: Verilen kampanyayı 2-3 cümlelik, ÇOK ENERJİK, SAMİMİ ve EMOJİLİ bir dille pazarlamak.

🚨 KRİTİK KURALLAR:
1. BAŞLIĞI ASLA TEKRARLAMA: Kampanya başlığını metin içinde aynen bir daha kullanma. "X kampanyası ile..." gibi klişe girişlerden kaçın.
2. ÖRNEK TON: "Manisa'da ulaşım bizden! 🚌 Hafta içi yapacağınız ilk yolculuğun ücretini QNB olarak biz karşılıyoruz. 💳 Sakın bu fırsatı kaçırmayın! 🎉" gibi direkt ve canlı ol.
3. EMOJİ KULLANIMI: Cümle sonlarına ve aralarına mutlaka 2-3 tane ilgili emoji yerleştir.
4. SOMUT DEĞER: Harcama limiti veya ödül miktarını (Örn: 500 TL, %20) metnin içine doğal bir şekilde yedir.
5. ŞABLONDAN KAÇIN: "Harcadıkça kazanın" gibi standart kalıplar yerine her seferinde farklı bir kurgu (hikayeleştirme) kullan.

Kampanya Başlığı: {title}
Kampanya Detayları: {description}
Ödül Bilgisi: {reward_text}
"""

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                return json.load(f).get("processed_ids", [])
        except:
            return []
    return []

def save_checkpoint(processed_ids):
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump({"processed_ids": processed_ids}, f)

# 🚨 MODEL AYARI: Kullanıcı isteği üzerine 3.1 Flash Lite Preview kullanılmaktadır.
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

def generate_marketing_text(title: str, description: str, reward_text: str) -> str:
    prompt = MARKETING_PROMPT.format(
        title=title or "Kampanya",
        description=(description or "")[:400],
        reward_text=reward_text or "Özel Fırsat"
    )
    
    config = genai_types.GenerateContentConfig(
        temperature=1.0, # Daha fazla çeşitlilik için artırıldı
        max_output_tokens=400
    )
    
    # 5 deneme hakkı ve artan bekleme süreleri
    for attempt in range(5):
        try:
            result = generate_with_rotation(prompt=prompt, model=GEMINI_MODEL, config=config)
            if result:
                text_res = str(result).strip()
                text_res = text_res.strip('"').strip("'").strip()
                text_res = re.sub(r'^```.*\n?', '', text_res)
                text_res = re.sub(r'\n?```$', '', text_res)
                # Başlık metnin içinde geçiyorsa temizlemeye çalış (Basit bir kontrol)
                if title and title.lower() in text_res.lower()[:len(title)+10]:
                    text_res = text_res.replace(title, "").replace(title.upper(), "").strip()
                return text_res.strip()
        except Exception as e:
            err_msg = str(e).lower()
            wait_time = (attempt + 1) * 20 # 20s, 40s, 60s...
            if "503" in err_msg or "high demand" in err_msg:
                print(f"\n   ⚠️ Google Yoğunluğu (503). {wait_time} saniye bekleniyor... (Deneme {attempt+1}/5)")
                time.sleep(wait_time)
            else:
                print(f"\n   ⚠️ Beklenmedik Hata: {err_msg[:60]}")
                time.sleep(5)
    return ""

def main():
    print("🚀 Benzersiz AI Marketing Text Operasyonu (V2) Başlıyor...")
    print("=" * 60)
    
    processed_ids = load_checkpoint()
    
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id, title, description, reward_text 
            FROM campaigns 
            WHERE is_active = true AND is_approved = true AND id <= 8128
            ORDER BY id DESC
        """)).fetchall()
        
        total = len(rows)
        todo_rows = [r for r in rows if r.id not in processed_ids]
        
        print(f"📊 Toplam: {total} | Kalan: {len(todo_rows)} | Atlanan: {len(processed_ids)}")
        
        updated = 0
        failed = 0
        
        for i, row in enumerate(todo_rows):
            camp_id = row.id
            title = row.title or ""
            
            print(f"   🔄 [{i+1}/{len(todo_rows)}] ID:{camp_id} - {title[:40]}...", end=" ", flush=True)
            
            new_text = generate_marketing_text(title, row.description, row.reward_text)
            
            if new_text and len(new_text) > 80:
                conn.execute(
                    text("UPDATE campaigns SET ai_marketing_text = :txt, updated_at = NOW() WHERE id = :id"),
                    {"txt": new_text, "id": camp_id}
                )
                conn.commit()
                processed_ids.append(camp_id)
                save_checkpoint(processed_ids)
                updated += 1
                print(f"✅")
                print(f"      📝 {new_text[:120]}...")
            else:
                failed += 1
                print(f"❌")
            
            time.sleep(1.5) 
        
        print("\n" + "=" * 60)
        print(f"🏁 TAMAMLANDI! {updated} kampanya başarıyla güncellendi.")

if __name__ == "__main__":
    main()
