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

cur.execute("SELECT id, name, slug FROM banks")
rows = cur.fetchall()

print(f"{'Eski Slug':<20} | {'Yeni Slug':<20} | {'Durum'}")
print("-" * 60)

for id, name, old_slug in rows:
    new_slug = slugify(name)
    if new_slug != old_slug:
        print(f"{str(old_slug):<20} | {new_slug:<20} | DÜZELTİLDİ")
        cur.execute("UPDATE banks SET slug = %s WHERE id = %s", (new_slug, id))
    else:
        print(f"{str(old_slug):<20} | {new_slug:<20} | OK")

conn.commit()
conn.close()
print("\nBanka slug normalizasyonu tamamlandı!")
