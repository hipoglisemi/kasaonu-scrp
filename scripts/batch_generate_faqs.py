import os
import sys
import json
import time
import psycopg2

# Add project root to python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
from src.utils.gemini_client import generate_with_rotation

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL must be set in .env")

BLOG_MODEL = os.getenv("BLOG_MODEL", "gemini-3.6-flash")

def generate_faqs(topic_title, html_content):
    """Makale için 5 adet FAQ üret."""
    prompt = f"""
Sen bir SEO ve içerik uzmanısın.
Aşağıda başlığı ve HTML içeriğinin bir kısmı verilen makale için Google FAQPage Schema'sına uygun tam 5 adet soru ve cevap üret.

BAŞLIK: {topic_title}
İÇERİK ÖZETİ: {html_content[:1500]}

KURALLAR:
1. Sorular kullanıcıların Google'da arayacağı tarzda olsun (Örn: "Maximum kart aidatı ne kadar?", "Öğrenci kredi kartı limiti neye göre belirlenir?").
2. Cevaplar doğrudan, net ve tatmin edici olsun (1-2 cümle).
3. SADECE JSON DİZİSİ (Array) döndür. Markdown işaretleri, ```json, veya ekstra açıklama KULLANMA.
4. Mutlaka tam 5 adet soru ve cevap olmalıdır.
5. JSON Formatı tam olarak aşağıdaki gibi olmalıdır:
[
  {{ "question": "Soru 1?", "answer": "Cevap 1" }},
  {{ "question": "Soru 2?", "answer": "Cevap 2" }},
  {{ "question": "Soru 3?", "answer": "Cevap 3" }},
  {{ "question": "Soru 4?", "answer": "Cevap 4" }},
  {{ "question": "Soru 5?", "answer": "Cevap 5" }}
]
"""
    try:
        response_text = generate_with_rotation(
            prompt=prompt,
            model=BLOG_MODEL,
            temperature=0.3,
            max_output_tokens=1000,
        )
        clean_text = response_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        
        clean_text = clean_text.strip()
        
        # Test if it is valid JSON
        faqs_array = json.loads(clean_text)
        if isinstance(faqs_array, list) and len(faqs_array) >= 1:
            return faqs_array
        return []
    except Exception as e:
        print(f"FAQ Uretme Hatasi ({topic_title}): {str(e)}")
        return []

def main():
    print("=" * 60)
    print(" 🚀 BLOG SSS (FAQ) TOPLU ÜRETİM ARACI BAŞLIYOR...")
    print("=" * 60)
    
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, content_html, slug 
        FROM blogs 
        WHERE faqs IS NULL OR faqs::text = '[]' OR faqs::text = '"{}"'
        ORDER BY id DESC
    """)
    blogs = cursor.fetchall()
    
    total = len(blogs)
    print(f"Toplam SSS'siz Blog Bulundu: {total}")
    
    success_count = 0
    fail_count = 0
    
    for idx, blog in enumerate(blogs, 1):
        blog_id, title, content_html, slug = blog
        print(f"\n[{idx}/{total}] SSS Üretiliyor: {title} (ID: {blog_id})")
        
        faqs = generate_faqs(title, content_html)
        
        if faqs and len(faqs) > 0:
            faqs_json = json.dumps(faqs, ensure_ascii=False)
            try:
                cursor.execute("""
                    UPDATE blogs 
                    SET faqs = %s 
                    WHERE id = %s
                """, (faqs_json, blog_id))
                conn.commit()
                print(f"✅ Başarılı ({len(faqs)} adet SSS eklendi)")
                success_count += 1
            except Exception as e:
                conn.rollback()
                print(f"❌ Veritabanı Kayıt Hatası: {str(e)}")
                fail_count += 1
        else:
            print("⚠️ Başarısız (Yapay zeka geçerli JSON üretemedi)")
            fail_count += 1
            
        # Rate limit protection
        time.sleep(2)
        
    print("=" * 60)
    print(f"🎉 İŞLEM TAMAMLANDI!")
    print(f"   Başarılı: {success_count}")
    print(f"   Başarısız: {fail_count}")
    print("=" * 60)
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
