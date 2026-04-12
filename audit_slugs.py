import os, re, psycopg2
from dotenv import load_dotenv
load_dotenv()

def slugify(text):
    if not text: return ""
    text = text.replace('İ', 'i').replace('Ğ', 'g').replace('Ü', 'u')
    text = text.replace('Ş', 's').replace('I', 'i').replace('Ö', 'o').replace('Ç', 'c')
    text = text.lower()
    text = text.replace('ğ', 'g').replace('ü', 'u').replace('ş', 's')
    text = text.replace('ı', 'i').replace('ö', 'o').replace('ç', 'c')
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

tables = [
    ('banks', 'name'),
    ('cards', 'name'),
    ('sectors', 'name'),
    ('brands', 'name'),
]

for table, name_col in tables:
    try:
        cur.execute(f"SELECT id, {name_col}, slug FROM {table}")
        rows = cur.fetchall()
        bozuk = [(id, name, slug, slugify(name)) 
                 for id, name, slug in rows 
                 if slug and slugify(name) != slug]
        if bozuk:
            print(f"\n❌ {table} tablosu - {len(bozuk)} bozuk slug:")
            for id, name, old, new in bozuk[:10]:
                print(f"  ID:{id} | {name} | {old} → {new}")
            if len(bozuk) > 10:
                print(f"  ... (+{len(bozuk)-10} kayıt daha)")
        else:
            print(f"✅ {table} tablosu temiz")
    except Exception as e:
        print(f"⚠️ {table} tablosu hatası: {e}")

conn.close()
