import os
import sys

# Add project root to python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import re
import psycopg2
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from src.utils.gemini_client import generate_with_rotation

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
MODEL_NAME = os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3-flash-preview")

def get_connection():
    return psycopg2.connect(DB_URL)

def get_active_campaigns_for_context(bank_name=None, sector_name=None, limit=5):
    """Biten kampanyanın yerine koyulacak en iyi aktif kampanyaları bulur."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT c.title, c.reward_text, c.slug, b.name as bank_name
            FROM campaigns c
            LEFT JOIN banks b ON b.id = (SELECT bank_id FROM cards WHERE id = c.card_id LIMIT 1)
            LEFT JOIN sectors s ON s.id = c.sector_id
            WHERE c.is_active = TRUE 
        """
        params = []
        if bank_name:
            query += " AND b.name ILIKE %s"
            params.append(f"%{bank_name}%")
        if sector_name:
            query += " AND s.name ILIKE %s"
            params.append(f"%{sector_name}%")
        
        query += " ORDER BY c.quality_score DESC NULLS LAST LIMIT %s"
        params.append(limit)
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        conn.close()

def refresh_blog_content(blog_id, content_html):
    """Blog içeriğindeki ölü linkleri bulur ve AI ile içeriği tazeler."""
    soup = BeautifulSoup(content_html, 'html.parser')
    links = soup.find_all('a', href=re.compile(r'kartavantaj\.com/kampanya/'))
    
    if not links:
        return None

    needs_update = False
    conn = get_connection()
    cur = conn.cursor()
    
    for link in links:
        slug = link['href'].split('/')[-1]
        cur.execute("SELECT is_active, title, reward_text FROM campaigns WHERE slug = %s", (slug,))
        row = cur.fetchone()
        
        # Eğer kampanya aktif değilse veya veritabanında yoksa güncelle
        if not row or not row[0]:
            print(f"⚠️  Pasif Kampanya Tespit Edildi: {slug}")
            needs_update = True
            
            # Eski kampanya bilgisi
            old_info = f"{row[1] if row else 'Bilinmeyen Kampanya'}: {row[2] if row else ''}"
            
            # Yeni alternatifleri al (rastgele bir sektör/banka varsayımı veya blog başlığına göre)
            # Şimdilik genel en iyi aktifleri alalım (ileride geliştirilebilir)
            new_campaigns = get_active_campaigns_for_context(limit=2)
            new_info = "\n".join([f"- {c[3]} {c[0]}: {c[1]} (Link: https://kartavantaj.com/kampanya/{c[2]})" for c in new_campaigns])
            
            # Paragrafı bul ve AI'ya ver
            parent_p = link.find_parent(['p', 'li', 'h2', 'h3'])
            if parent_p:
                old_text = str(parent_p)
                prompt = f"""
Sen KartAvantaj editörüsün. Aşağıdaki HTML bloğunda geçen kampanya süresi dolduğu için artık geçersizdir.
GÖREV: Bu HTML bloğunu, makalenin genel akışını bozmadan, YENİ kampanya bilgileriyle güncelle.

ESKİ KAMPANYA: {old_info}
YENİ KAMPANYA(LAR):
{new_info}

GÜNCELLENECEK HTML BLOĞU:
{old_text}

KURALLAR:
1. Sadece sana verilen YENİ kampanya linklerini kullan. (https://kartavantaj.com/kampanya/...)
2. Metin doğal olsun, "X bitti yerine Y geldi" deme. Sanki her zaman Y'den bahsediyormuşsun gibi yaz.
3. SADECE güncellenmiş HTML kodunu döndür.
"""
                new_text = generate_with_rotation(prompt=prompt, model=MODEL_NAME)
                # BeautifulSoup ile yeni metni enjekte et (Basit replace)
                content_html = content_html.replace(old_text, new_text)
                print(f"✅  Metin AI ile tazelendi.")

    conn.close()
    return content_html if needs_update else None

def main():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title, content_html FROM blogs WHERE is_published = TRUE")
    blogs = cur.fetchall()
    
    for blog_id, title, html in blogs:
        print(f"🔍 Denetleniyor: {title}")
        updated_html = refresh_blog_content(blog_id, html)
        if updated_html:
            cur.execute("UPDATE blogs SET content_html = %s WHERE id = %s", (updated_html, blog_id))
            conn.commit()
            print(f"✨ BLOG GÜNCELLENDİ (LİNK VE METİN): {title}")

    conn.close()

if __name__ == "__main__":
    main()
