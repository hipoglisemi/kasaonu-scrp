import os
import time
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

def get_unique_unsplash_images(count=30, fallback_offset=0):
    """Fetch `count` random unique images from Unsplash API."""
    if not UNSPLASH_ACCESS_KEY:
        return []
    
    # We use a broad set of keywords and orientation landscape to get good blog assets
    keywords = "finance, money, business, technology, lifestyle, abstract"
    try:
        res = requests.get(
            "https://api.unsplash.com/photos/random",
            params={
                "query": keywords,
                "orientation": "landscape",
                "count": count,
                "client_id": UNSPLASH_ACCESS_KEY
            },
            timeout=10
        )
        if res.status_code == 200:
            return [photo["urls"]["regular"] for photo in res.json()]
        else:
            print(f"⚠️ API Hatası: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"⚠️ Bağlantı Hatası: {e}")
    return []

def main():
    if not DB_URL:
        print("❌ DATABASE_URL bulunamadı.")
        return

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("SELECT id, title, image_url FROM blogs")
    blogs = cur.fetchall()
    
    print(f"🔍 Toplam {len(blogs)} blog bulundu. Eşsiz görseller havuzdan seçiliyor...")

    # Build a pool of at least 60 images (max 30 per request)
    image_pool = set()
    attempts = 0
    while len(image_pool) < len(blogs) and attempts < 10:
        new_urls = get_unique_unsplash_images(count=30)
        for url in new_urls:
            # Strip query params like 'crop', 'w' to only match base ID for true uniqueness check
            # but Unsplash id is in the URL, actually regular URL is fine as is
            base_url = url.split("?")[0] 
            # We must verify we haven't added this photo before
            if not any(base_url in existing for existing in image_pool):
                image_pool.add(url)
        print(f"Havuzdaki benzersiz resim sayısı: {len(image_pool)}")
        attempts += 1
        time.sleep(1) # Prevent rate limiting

    image_pool = list(image_pool) # Convert back to list to pop
    updated_count = 0

    for blog_id, title, current_url in blogs:
        if len(image_pool) > 0:
            new_url = image_pool.pop(0)
            cur.execute("UPDATE blogs SET image_url = %s WHERE id = %s", (new_url, blog_id))
            updated_count += 1
            print(f"✅ ID:{blog_id} eşsiz görsel atandı: {title[:30]}...")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\n✨ Operasyon Tamamlandı: {updated_count} blog için sıfır tekrarla yepyeni eşsiz görseller atandı!")

if __name__ == "__main__":
    main()
