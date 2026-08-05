import os
import sys
import json
import psycopg2 # type: ignore
from dotenv import load_dotenv # type: ignore
import time

# Add project root to python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.gemini_client import generate_with_rotation # type: ignore

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL must be set in .env")

BLOG_MODEL = os.getenv("BLOG_MODEL", "gemini-3.6-flash")

def get_connection():
    return psycopg2.connect(DB_URL)

def generate_faqs(title: str, content: str) -> list:
    print(f"🔄 SSS Üretiliyor: {title}")
    prompt = f"""
Sen bir SEO ve içerik uzmanısın.
Aşağıda başlığı ve içeriği verilen blog yazısı için Google FAQPage (Sıkça Sorulan Sorular) Schema'sına uygun tam 5 adet soru ve cevap üret.

BAŞLIK: {title}
İÇERİK ÖZETİ (veya tam metin):
{content[:2000]}...

KURALLAR:
1. Sorular kullanıcıların Google'da arayacağı tarzda olsun (Örn: "Maximum kart aidatı ne kadar?", "Öğrenci kredi kartı limiti neye göre belirlenir?").
2. Cevaplar doğrudan, net ve tatmin edici olsun (1-2 cümle).
3. SADECE JSON DIZISI (Array) dondur. Markdown isaretleri, ```json, veya ekstra aciklama kullanma.
4. JSON Formatı asagidaki gibi olmalidir:
[
  {{ "question": "Soru 1?", "answer": "Cevap 1" }},
  {{ "question": "Soru 2?", "answer": "Cevap 2" }}
]
"""
    try:
        response_text = generate_with_rotation(
            prompt=prompt,
            model=BLOG_MODEL,
            temperature=0.3,
            max_output_tokens=1000,
        )
        # JSON temizleme
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        import re
        match = re.search(r'\[.*\]', clean_text, re.DOTALL)
        if match:
            clean_text = match.group(0)

        data = json.loads(clean_text)
        if isinstance(data, list) and len(data) > 0:
            return data
        return []
    except Exception as e:
        print(f"❌ Gemini veya Parse hatası: {e}")
        return []

def main():
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Sadece faqs'i boş olan (NULL veya boş array) yazıları getir
        cur.execute("""
            SELECT id, title, content_html 
            FROM blogs 
            WHERE faqs IS NULL OR faqs::text = '[]' OR faqs::text = 'null'
            ORDER BY id ASC
        """)
        blogs = cur.fetchall()
        print(f"📌 SSS'si eksik toplam {len(blogs)} blog bulundu.")

        updated_count = 0
        for blog in blogs:
            b_id, b_title, b_content = blog
            
            faqs = generate_faqs(b_title, b_content)
            
            if faqs and len(faqs) > 0:
                cur.execute(
                    "UPDATE blogs SET faqs = %s::jsonb WHERE id = %s",
                    (json.dumps(faqs, ensure_ascii=False), b_id)
                )
                conn.commit()
                print(f"✅ Başarılı: {b_title} (ID: {b_id}) - {len(faqs)} soru eklendi.")
                updated_count += 1
            else:
                print(f"⚠️ Atlandı: {b_title} (ID: {b_id})")
            
            time.sleep(2) # Rate limit için bekle
            
        print(f"\n🎉 İşlem tamamlandı. Toplam {updated_count} blog yazısına SSS eklendi.")
    except Exception as e:
        print(f"❌ Veritabanı okuma hatası: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
