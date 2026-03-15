import os
import json
import sys
import datetime
from sqlalchemy import create_engine, text # type: ignore

# Add project root to sys.path to ensure src imports work
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.utils.gemini_client import generate_with_rotation # type: ignore

# ─── Configuration ───────────────────────────────────────────────────────────
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please provide it for database connectivity.")

PROMPT_TEMPLATE = """
Sen bir finans ve bankacılık uzmanısın. Kullanıcılar için "{sector_name}" sektöründeki en karlı kredi kartı kampanyalarını karşılaştırarak "Hap Bilgi" şeklinde bir tablo oluşturmalısın.

SİZE SAĞLANAN KAMPANYALAR:
{campaign_list}

KURALLAR:
1. Koşulları ve ödülleri tek tipleştir (örn: "2.500 TL harcamaya 100 TL puan").
2. En karlı ve popüler olan ilk 10-15 kampanyayı seç.
3. Banka logoları ve kart isimlerini net belirt (Axess, Bonus, Maximum, Miles&Smiles vb.).
4. Çıktı SADECE geçerli bir JSON array olmalıdır. Format:
[
  {{
    "card": "Banka/Kart Adı (örn: Akbank Axess)",
    "condition": "Kısa ve net koşul (örn: 2.000 TL ve üzeri harcamaya)",
    "reward": "Kazanılacak Ödül/Puan (örn: 150 TL Chip-Para)",
    "max_reward": "Maksimum kazanılacak TL tutarı (örn: 1.500 TL)",
    "reward_category": "puan/mil/taksit",
    "campaign_id": "Orijinal Liste ID'si",
    "is_troy": true/false (Eğer Troy kartlara özel ek avantaj varsa true yap)
  }}
]

Analiz yaparken gerçekten "karlı" olanları başa al. Sadece JSON döndür, açıklama yapma.
"""

import time

def clean_json_response(text: str) -> str:
    """Extraer JSON de bloques de código markdown si existen."""
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    if "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()

def call_ai_with_retry(prompt: str, max_retries: int = 5) -> str:
    """
    Robust AI call with internal key rotation and external retries.
    Mirrors AIParser logic for RPD/RPM resilience.
    """
    for attempt in range(max_retries):
        try:
            # Respect RPM (Requests Per Minute) - 2.5 Flash Lite has only 10 RPM
            time.sleep(2.0)
            
            response = generate_with_rotation(
                prompt, 
                temperature=0.0,
                model="gemini-3.1-flash-lite-preview"
            )
            return response
        except Exception as e:
            error_str = str(e).lower()
            # If we fall through here, it means generate_with_rotation failed for ALL keys
            is_limit = any(x in error_str for x in ["429", "resource exhausted", "quota", "rate_limit", "503"])
            
            if is_limit and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"   ⚠️ Tüm anahtarların limiti doldu veya 503 hatası. {wait_time}s bekleniyor... (Deneme {attempt+1}/{max_retries})")
                time.sleep(wait_time)
                continue
            raise e
    
    raise RuntimeError("AI yanıt üretemedi (Maksimum deneme sayısına ulaşıldı)")

def generate_comparisons():
    engine = create_engine(DB_URL)
    
    with engine.connect() as conn:
        # 1. Aktif sektörleri getir
        result = conn.execute(text("SELECT id, name FROM sectors WHERE is_active = true ORDER BY sort_order ASC"))
        sectors = result.fetchall()
        
        for sector_id, sector_name in sectors:
            print(f"[{sector_name}] Analiz ediliyor...")
            
            # 2. Sektöre ait en popüler 30 kampanyayı getir
            query = text("""
                SELECT id, title, reward_text, view_count, reward_value
                FROM campaigns 
                WHERE sector_id = :s_id AND is_active = true 
                AND (end_date IS NULL OR end_date >= CURRENT_DATE)
                ORDER BY view_count DESC, reward_value DESC NULLS LAST
                LIMIT 30
            """)
            campaigns = conn.execute(query, {"s_id": sector_id}).fetchall()
            
            if not campaigns:
                print(f"[{sector_name}] Kampanya bulunamadı, atlanıyor.")
                continue
            
            campaign_list_str = "\n".join([
                f"- ID: {c.id}, Başlık: {c.title}, Ödül: {c.reward_text}"
                for c in campaigns
            ])
            
            # 3. AI Karşılaştırma Analizi
            prompt = PROMPT_TEMPLATE.format(sector_name=sector_name, campaign_list=campaign_list_str)
            try:
                # Gemini 2.5 Flash Lite (User specified model) - Wrapped in retry for RPD/RPM resilience
                response = call_ai_with_retry(prompt)
                
                if not isinstance(response, str):
                    print(f"[{sector_name}] Geçersiz AI yanıtı atlanıyor.")
                    continue
                    
                json_text = clean_json_response(response)
                table_data = json.loads(json_text)
                
                # 4. Veritabanına Kaydet (Upsert)
                # Akakçe gibi günlük tablo oluşturduğumuz için tarih bazlı kaydediyoruz
                today = datetime.date.today()
                
                upsert_query = text("""
                    INSERT INTO comparison_snapshots (snapshot_date, type, target_id, target_name, data)
                    VALUES (:date, 'sector', :id, :name, :data)
                    ON CONFLICT (snapshot_date, type, target_id) 
                    DO UPDATE SET 
                        data = EXCLUDED.data, 
                        target_name = EXCLUDED.target_name,
                        created_at = CURRENT_TIMESTAMP
                """)
                
                conn.execute(upsert_query, {
                    "date": today,
                    "id": str(sector_id),
                    "name": sector_name,
                    "data": json.dumps(table_data, ensure_ascii=False)
                })
                conn.commit()
                print(f"[SUCCESS] {sector_name} tablosu güncellendi.")
                
            except Exception as e:
                print(f"[ERROR] {sector_name} işlenirken hata oluştu: {str(e)}")

        # 5. Aktif ve en popüler markaları getir (En az 3 kampanyası olanlar)
        brand_query = text("""
            SELECT b.id, b.name, b.slug, COUNT(cb.campaign_id) as count
            FROM brands b
            JOIN campaign_brands cb ON b.id = cb.brand_id
            JOIN campaigns c ON cb.campaign_id = c.id
            WHERE c.is_active = true AND (c.end_date IS NULL OR c.end_date >= CURRENT_DATE)
            GROUP BY b.id, b.name, b.slug
            HAVING COUNT(cb.campaign_id) >= 3
            ORDER BY count DESC
            LIMIT 12
        """)
        brands = conn.execute(brand_query).fetchall()
        
        for brand_id, brand_name, brand_slug, count in brands:
            print(f"[Marka: {brand_name}] Analiz ediliyor ({count} kampanya)...")
            
            # Markaya ait kampanyaları getir
            query = text("""
                SELECT c.id, c.title, c.reward_text, c.reward_value
                FROM campaigns c
                JOIN campaign_brands cb ON c.id = cb.campaign_id
                WHERE cb.brand_id = :b_id AND c.is_active = true 
                AND (c.end_date IS NULL OR c.end_date >= CURRENT_DATE)
                ORDER BY c.reward_value DESC NULLS LAST
            """)
            campaigns = conn.execute(query, {"b_id": brand_id}).fetchall()
            
            campaign_list_str = "\n".join([
                f"- ID: {c.id}, Başlık: {c.title}, Ödül: {c.reward_text}"
                for c in campaigns
            ])
            
            prompt = PROMPT_TEMPLATE.format(sector_name=f"{brand_name} Marka", campaign_list=campaign_list_str)
            
            try:
                response = call_ai_with_retry(prompt)
                
                if not isinstance(response, str):
                    print(f"[{brand_name}] Geçersiz AI yanıtı atlanıyor.")
                    continue
                    
                json_text = clean_json_response(response)
                table_data = json.loads(json_text)
                
                today = datetime.date.today()
                
                upsert_query = text("""
                    INSERT INTO comparison_snapshots (snapshot_date, type, target_id, target_name, data)
                    VALUES (:date, 'brand', :id, :name, :data)
                    ON CONFLICT (snapshot_date, type, target_id) 
                    DO UPDATE SET 
                        data = EXCLUDED.data, 
                        target_name = EXCLUDED.target_name,
                        created_at = CURRENT_TIMESTAMP
                """)
                
                conn.execute(upsert_query, {
                    "date": today,
                    "id": brand_slug, # Markalar için slug kullanıyoruz target_id olarak
                    "name": brand_name,
                    "data": json.dumps(table_data, ensure_ascii=False)
                })
                conn.commit()
                print(f"[SUCCESS] {brand_name} markası tablosu güncellendi.")
                
            except Exception as e:
                print(f"[ERROR] Brand {brand_name} işlenirken hata: {str(e)}")

if __name__ == "__main__":
    generate_comparisons()
