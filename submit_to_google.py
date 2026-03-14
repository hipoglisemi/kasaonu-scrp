import os
import json
import time
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL must be set in .env")

SEARCH_CONSOLE_KEY = os.getenv("SEARCH_CONSOLE_KEY")
if not SEARCH_CONSOLE_KEY:
    raise ValueError("SEARCH_CONSOLE_KEY must be set")

SITE_URL = "https://kartavantaj.com"
DAILY_LIMIT = 195
SCOPES = ["https://www.googleapis.com/auth/indexing"]


def get_indexing_service():
    key_data = json.loads(SEARCH_CONSOLE_KEY)
    credentials = service_account.Credentials.from_service_account_info(
        key_data, scopes=SCOPES
    )
    return build("indexing", "v3", credentials=credentials)


def get_connection():
    return psycopg2.connect(DB_URL)


def get_priority_urls():
    conn = get_connection()
    try:
        cur = conn.cursor()
        urls = []

        # 1. Son 24 saatte eklenen kampanyalar
        cur.execute("""
            SELECT slug FROM campaigns
            WHERE is_active = TRUE
              AND created_at >= NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
        """)
        for row in cur.fetchall():
            urls.append({"url": f"{SITE_URL}/kampanya/{row[0]}", "priority": 1, "reason": "Yeni kampanya"})

        # 2. Son 7 günde güncellenen kampanyalar
        cur.execute("""
            SELECT slug FROM campaigns
            WHERE is_active = TRUE
              AND updated_at >= NOW() - INTERVAL '7 days'
              AND created_at < NOW() - INTERVAL '24 hours'
            ORDER BY updated_at DESC
            LIMIT 50
        """)
        for row in cur.fetchall():
            urls.append({"url": f"{SITE_URL}/kampanya/{row[0]}", "priority": 2, "reason": "Güncellenen kampanya"})

        # 3. Eski kampanyalar — kalan limiti doldur
        remaining = max(0, DAILY_LIMIT - len(urls) - 10)
        if remaining > 0:
            cur.execute("""
                SELECT slug FROM campaigns
                WHERE is_active = TRUE
                  AND updated_at < NOW() - INTERVAL '7 days'
                ORDER BY id ASC
                LIMIT %s
            """, (remaining,))
            for row in cur.fetchall():
                urls.append({"url": f"{SITE_URL}/kampanya/{row[0]}", "priority": 3, "reason": "Eski kampanya"})

        # 4. Yayındaki bloglar
        # Use order by created_at or publishedAt (checking previous steps it was createdAt mainly used in DB)
        # But script says published_at, I better check schema again to be sure or use created_at to avoid error.
        # Actually published_at was removed from my last fix.
        cur.execute("SELECT slug FROM blogs WHERE is_published = TRUE ORDER BY created_at DESC")
        for row in cur.fetchall():
            urls.append({"url": f"{SITE_URL}/blog/{row[0]}", "priority": 2, "reason": "Blog"})

        # 5. Statik sayfalar
        for page in ["/", "/kampanyalar", "/bankalar", "/karsilastir", "/blog"]: # karsilastir optimized in previous tasks
            urls.append({"url": f"{SITE_URL}{page}", "priority": 1, "reason": "Statik sayfa"})

        return urls[:DAILY_LIMIT]
    finally:
        conn.close()


def submit_url(service, url, reason):
    try:
        service.urlNotifications().publish(body={"url": url, "type": "URL_UPDATED"}).execute()
        print(f"  ✅  [{reason}] {url}")
        return True
    except Exception as e:
        print(f"  ❌  [{reason}] {url} → {e}")
        return False


def main():
    print("🚀  Google Indexing Otomasyonu başlatıldı")
    print(f"📅  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    service = get_indexing_service()
    urls = get_priority_urls()
    urls.sort(key=lambda x: x["priority"])

    p1 = len([u for u in urls if u["priority"] == 1])
    p2 = len([u for u in urls if u["priority"] == 2])
    p3 = len([u for u in urls if u["priority"] == 3])

    print(f"📋  Toplam {len(urls)} URL gönderilecek")
    print(f"🔴  Öncelik 1 (yeni/statik): {p1}")
    print(f"🟡  Öncelik 2 (güncellenen/blog): {p2}")
    print(f"🟢  Öncelik 3 (eski): {p3}\n")

    success = 0
    failed = 0
    for i, item in enumerate(urls, 1):
        if submit_url(service, item["url"], item["reason"]):
            success += 1
        else:
            failed += 1
        if i % 10 == 0:
            time.sleep(1)

    print(f"\n{'='*50}")
    print(f"✅  Başarılı: {success} | ❌  Başarısız: {failed}")
    print(f"{'='*50}\n✨  Tamamlandı.")


if __name__ == "__main__":
    main()
