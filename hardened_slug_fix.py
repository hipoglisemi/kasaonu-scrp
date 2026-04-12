import os, re, psycopg2, unicodedata
from dotenv import load_dotenv
load_dotenv()

def slugify(text):
    if not text: return ""
    text = str(text)
    replacements = {
        'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c',
        'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'Â': 'a', 'â': 'a', 'Î': 'i', 'î': 'i', 'Û': 'u', 'û': 'u',
        'Ê': 'e', 'ê': 'e', 'Ô': 'o', 'ô': 'o', 'I': 'i',
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
        
    text = unicodedata.normalize('NFKD', text)
    text = text.lower()
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()

def update_table_slugs(table_name, name_column):
    print(f"\n[{table_name.upper()}] İşleniyor...")
    cur.execute(f"SELECT id, {name_column}, slug FROM {table_name}")
    rows = cur.fetchall()
    updated = skipped = conflicts = 0

    for id, name, old_slug in rows:
        new_slug = slugify(name)
        
        # Brands için özel temizlik (timestamp eki)
        if table_name == 'brands':
            new_slug = re.sub(r'-\d{8,}$', '', new_slug)

        if new_slug == old_slug:
            skipped += 1
            continue
            
        # Çakışma kontrolü
        cur.execute(f"SELECT id FROM {table_name} WHERE slug = %s AND id != %s", (new_slug, id))
        if cur.fetchone():
            original_new = new_slug
            new_slug = f"{new_slug}-2"
            # 2. seviye çakışma kontrolü
            cur.execute(f"SELECT id FROM {table_name} WHERE slug = %s AND id != %s", (new_slug, id))
            if cur.fetchone():
                print(f"  ⚠️ KRİTİK ÇAKIŞMA: {name} (Slug: {original_new}) - Atlandı")
                conflicts += 1
                continue
        
        try:
            cur.execute(f"UPDATE {table_name} SET slug = %s WHERE id = %s", (new_slug, id))
            print(f"  {str(old_slug):<25} → {new_slug}")
            updated += 1
        except Exception as e:
            print(f"  ❌ HATA ({name}): {e}")
            conn.rollback()
            continue

    conn.commit()
    print(f">> {table_name}: Güncellenen: {updated} | Atlanan: {skipped} | Çakışma: {conflicts}")

# Ana işlem döngüsü
update_table_slugs('cards', 'name')
update_table_slugs('sectors', 'name')
update_table_slugs('brands', 'name')

conn.close()
print("\nTüm tablolar başarıyla normalize edildi!")
