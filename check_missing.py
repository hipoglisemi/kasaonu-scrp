import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

three_days_ago = datetime.now() - timedelta(days=3)

cur.execute("""
    SELECT c.id, b.name, c.title, c.last_seen_at, c.is_active
    FROM campaigns c 
    JOIN master_banks b ON c.bank_id = b.id 
    WHERE c.is_active = true 
    AND c.is_approved = true 
    AND c.tracking_url IS NOT NULL 
    AND c.last_seen_at IS NOT NULL 
    AND c.last_seen_at < %s
    ORDER BY c.last_seen_at ASC
    LIMIT 10;
""", (three_days_ago,))

print(f"Toplam 136 kampanyadan ilk 10'u:")
for row in cur.fetchall():
    print(f"ID: {row[0]}, Banka: {row[1]}, Son Görülme: {row[3].strftime('%Y-%m-%d %H:%M:%S')}, Aktif Mi: {row[4]}, Başlık: {row[2][:50]}...")
