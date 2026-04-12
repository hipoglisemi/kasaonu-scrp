import json, psycopg2, os, random
with open('unsplash_pool.json', 'r') as f:
    raw_data = json.load(f)

from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

def get_image_from_pool(title):
    t = str(title).lower()
    cat = 'finance'
    if 'uçak' in t or 'seyahat' in t or 'otel' in t: cat = 'travel'
    elif 'market' in t or 'gıda' in t: cat = 'grocery'
    elif 'e-ticaret' in t or 'alışveriş' in t: cat = 'shopping'
    elif 'eğitim' in t or 'üniversite' in t: cat = 'finance'
    elif 'akaryakıt' in t or 'araç' in t or 'otomotiv' in t: cat = 'driving'
    elif 'sağlık' in t or 'kozmetik' in t: cat = 'health'
    elif 'teknoloji' in t or 'elektronik' in t: cat = 'technology'
    elif 'mobilya' in t or 'dekorasyon' in t: cat = 'interior-design'
    
    lst = raw_data.get(cat)
    if not lst or len(lst) == 0:
        lst = raw_data['finance']
    
    img_id = random.choice([x for x in lst if len(x) > 5])
    return f"https://images.unsplash.com/photo-{img_id}?w=1200&q=80&auto=format&fit=crop"

cur.execute("SELECT id, title FROM blogs")
for row in cur.fetchall():
    cur.execute("UPDATE blogs SET image_url=%s WHERE id=%s", (get_image_from_pool(row[1]), row[0]))

conn.commit()
conn.close()
print("✅ DB updated cleanly!")
