import os
import psycopg2
from dotenv import load_dotenv
from src.utils.gemini_client import generate_with_rotation

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
# Use the requested lite model for efficient bulk processing
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

def get_connection():
    return psycopg2.connect(DB_URL)

def generate_seo_content(name, type="bank"):
    """Yapay zeka ile banka veya kart için 4 bölümlü SEO içeriği üretir."""
    print(f"✍️  {name} ({type}) için SEO içeriği üretiliyor...")
    
    prompt = f"""
    Sen KartAvantaj'ın kıdemli SEO ve finans editörüsün. 
    Görevin: "{name}" adlı {type} için Google'da üst sıralara çıkacak, 
    kullanıcılara değer katan, profesyonel bir tanıtım metni yazmak.
    
    KURALLAR:
    1. Dil: Kusursuz Türkçe. Samimi ama güven verici bir ton.
    2. Yapı: Aşağıdaki 4 başlık altında topla ve her başlık başına çift yıldız (**) koy.
       Bölümler: 
       - **Kurum/Banka Hakkında**: Tarihçe, vizyon ve güvenilirlik.
       - **Ürünler/Kredi Kartları**: Sunulan temel finansal ürünler.
       - **Kampanya Kategorileri**: Sıkça düzenlenen indirim ve puan türleri.
       - **Kullanıcı Avantajları**: Neden tercih edilmeli, ne avantaj sağlar?
    3. Uzunluk: Her bölüm en az 75-100 kelime olmalı (Toplam 400+ kelime).
    4. Format: Paragraflar arasında çift satır boşluk bırak. **Başlık**: İçerik şeklinde başla.
    5. Yasaklar: Dış link verme, uydurma kampanya verisi kullanma (genel konuş).
    
    SADECE metni döndür. Başka hiçbir şey yazma.
    """
    
    try:
        content = generate_with_rotation(
            prompt=prompt,
            model=MODEL,
            temperature=0.7,
            max_output_tokens=2000
        )
        return content.strip()
    except Exception as e:
        print(f"❌  AI Üretim Hatası ({name}): {e}")
        return None

def process_missing_seos():
    conn = get_connection()
    try:
        cur = conn.cursor()
        
        # 1. Banks
        cur.execute("SELECT id, name FROM banks WHERE seo_summary IS NULL OR seo_summary = ''")
        banks = cur.fetchall()
        print(f"🔍  SEO özeti eksik {len(banks)} banka bulundu.")
        for b_id, b_name in banks:
            summary = generate_seo_content(b_name, "banka")
            if summary:
                cur.execute("UPDATE banks SET seo_summary = %s WHERE id = %s", (summary, b_id))
                conn.commit()
                print(f"✅  {b_name} güncellendi.")

        # 2. Card Details
        query = """
            SELECT cd.id, c.name 
            FROM card_details cd 
            JOIN cards c ON cd.card_id = c.id 
            WHERE cd.seo_summary IS NULL OR cd.seo_summary = ''
        """
        cur.execute(query)
        details = cur.fetchall()
        print(f"🔍  SEO özeti eksik {len(details)} kart detayı bulundu.")
        for d_id, c_name in details:
            summary = generate_seo_content(c_name, "kredi kartı")
            if summary:
                cur.execute("UPDATE card_details SET seo_summary = %s WHERE id = %s", (summary, d_id))
                conn.commit()
                print(f"✅  {c_name} güncellendi.")

    except Exception as e:
        print(f"❌  Hata: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    process_missing_seos()
