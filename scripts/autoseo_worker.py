import os
import sys

# Add project root to python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import psycopg2
from dotenv import load_dotenv
from src.utils.gemini_client import generate_with_rotation

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
# Default olarak hızlı ve ucuz olan 2.5 Flash kullan
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
if "3.5" in MODEL:
    MODEL = "gemini-3.1-flash-lite"

def get_connection():
    return psycopg2.connect(DB_URL)

def generate_seo_content(name, type="bank"):
    """Yapay zeka ile banka, kart veya kategori için 4 bölümlü SEO içeriği üretir."""
    print(f"✍️  {name} ({type}) için SEO içeriği üretiliyor...")
    
    prompt = f"""
    Sen KartAvantaj'ın kıdemli SEO ve finans editörüsün. 
    Görevin: "{name}" adlı {type} için Google'da üst sıralara çıkacak, 
    kullanıcılara değer katan, profesyonel bir rehber yazmak.
    
    KURALLAR:
    1. Dil: Kusursuz Türkçe. Samimi ama güven verici bir ton.
    2. Yapı: Aşağıdaki 4 başlık altında topla ve her başlık başına çift yıldız (**) koy.
    3. Akıllı Linkleme: 
       - Metin içine ASLA "ID" içeren veya geçici kampanya linki (Örn: /kampanya/axess-123) koyma.
       - En güncel kampanyaları göstermek istediğin yere mutlaka [[GUNCEL_KAMPANYALAR]] etiketini koy.
       - Sabit sayfalara (Örn: /banka/axess veya /kategori/market) link verebilirsin.
    4. Bölümler: 
       - **Hakkında**: {name} dünyasına çok kapsamlı bir giriş, tarihçe ve temel mantık.
       - **Popüler Uygulamalar/Ürünler**: Öne çıkan özellikler, yenilikler ve teknolojik detaylar.
       - **Kampanya Türleri**: Genellikle hangi alanlarda indirim/puan verilir, müşteriye nasıl avantaj sağlar?
       - **Kullanıcı İpuçları**: Tasarrufu maksimize etmek için uzman önerileri ve stratejiler.
    5. Uzunluk: ÇOK ÖNEMLİ! Her bölüm en az 150-200 kelime uzunluğunda, son derece detaylı, ansiklopedik ve bilgi açısından çok doyurucu olmalıdır. Kısa ve yüzeysel geçiştirmeler yapma. (Toplam en az 800+ kelime olmalı).
    6. Format: Paragraflar arasında çift satır boşluk bırak. Başlıkları kalın yap.
    
    SADECE metni döndür. Başka hiçbir şey yazma.
    """
    
    try:
        content = generate_with_rotation(
            prompt=prompt,
            model=MODEL,
            temperature=0.7,
            max_output_tokens=4000
        )
        return content.strip()
    except Exception as e:
        print(f"❌  AI Üretim Hatası ({name}): {e}")
        return None

def process_missing_seos():
    conn = get_connection()
    try:
        cur = conn.cursor()
        
        # 0. Auto-create card_details for cards that don't have it
        cur.execute("""
            INSERT INTO card_details (card_id, created_at, updated_at)
            SELECT id, NOW(), NOW()
            FROM cards
            WHERE id NOT IN (SELECT card_id FROM card_details)
        """)
        conn.commit()
        print("💳 Missing card_details rows auto-created.")
        
        # 1. Banks
        cur.execute("SELECT id, name FROM banks WHERE seo_summary IS NULL OR TRIM(seo_summary) = '' OR LENGTH(seo_summary) < 500")
        banks = cur.fetchall()
        print(f"🔍  SEO özeti eksik/kısa {len(banks)} banka bulundu.")
        for b_id, b_name in banks:
            b_name_clean = b_name.strip()
            summary = generate_seo_content(b_name_clean, "banka")
            if summary:
                cur.execute("UPDATE banks SET seo_summary = %s WHERE id = %s", (summary, b_id))
                conn.commit()
                print(f"✅  {b_name_clean} (Banka) güncellendi.")

        # 2. Sectors (Categories)
        cur.execute("SELECT id, name FROM sectors WHERE ai_summary IS NULL OR TRIM(ai_summary) = '' OR LENGTH(ai_summary) < 500")
        sectors = cur.fetchall()
        print(f"🔍  SEO içeriği eksik/kısa {len(sectors)} sektör bulundu.")
        for s_id, s_name in sectors:
            s_name_clean = s_name.strip()
            content = generate_seo_content(s_name_clean, "kampanya kategorisi")
            if content:
                cur.execute("UPDATE sectors SET ai_summary = %s WHERE id = %s", (content, s_id))
                conn.commit()
                print(f"✅  {s_name_clean} (Sektör) güncellendi.")

        # 3. Card Details
        query = """
            SELECT cd.id, c.name 
            FROM card_details cd 
            JOIN cards c ON cd.card_id = c.id 
            WHERE cd.seo_summary IS NULL OR TRIM(cd.seo_summary) = '' OR LENGTH(cd.seo_summary) < 500
        """
        cur.execute(query)
        details = cur.fetchall()
        print(f"🔍  SEO özeti eksik/kısa {len(details)} kart detayı bulundu.")
        for d_id, c_name in details:
            c_name_clean = c_name.strip()
            summary = generate_seo_content(c_name_clean, "kredi kartı")
            if summary:
                cur.execute("UPDATE card_details SET seo_summary = %s WHERE id = %s", (summary, d_id))
                conn.commit()
                print(f"✅  {c_name_clean} (Kart) güncellendi.")

    except Exception as e:
        print(f"❌  Hata: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    process_missing_seos()
