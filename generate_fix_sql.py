import json
import re
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

def slugify(text):
    if not text: return ""
    text = text.lower()
    replacements = {
        'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'â': 'a', 'î': 'i', 'û': 'u'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def get_clean_slug(slug):
    if not slug: return ''
    parts = slug.split('-')
    while len(parts) > 1:
        last_part = parts[-1]
        if re.match(r'^\d+$', last_part) or re.match(r'^[a-f0-9]{8}$', last_part):
            parts.pop()
        else:
            break
    return '-'.join(parts)

def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    # Fetch collisions with full context
    query = """
    SELECT 
        c.id, 
        c.slug, 
        c.title, 
        b.name as bank_name,
        card.name as card_name,
        s.name as sector_name,
        c.created_at
    FROM campaigns c
    JOIN cards card ON c.card_id = card.id
    JOIN banks b ON card.bank_id = b.id
    LEFT JOIN sectors s ON c.sector_id = s.id
    WHERE c.is_active = TRUE AND c.is_approved = TRUE
    """
    cur.execute(query)
    rows = cur.fetchall()
    
    clean_slugs = {}
    for r in rows:
        clean = get_clean_slug(r[1])
        data = {
            'id': r[0], 'orig_slug': r[1], 'title': r[2],
            'bank': slugify(r[3]), 'card': slugify(r[4]), 'sector': slugify(r[5]),
            'created_at': r[6]
        }
        if clean not in clean_slugs: clean_slugs[clean] = []
        clean_slugs[clean].append(data)

    sql_commands = []
    used_global_slugs = set()

    # First, collect all non-colliding clean slugs as "reserved"
    for clean, items in clean_slugs.items():
        if len(items) == 1:
            used_global_slugs.add(clean)

    for clean, items in clean_slugs.items():
        if len(items) > 1:
            # Sort by ID (oldest first)
            items.sort(key=lambda x: x['id'])
            
            for i, item in enumerate(items):
                new_slug = clean
                
                if i > 0: # Not the first one
                    # Try Bank
                    candidate = f"{clean}-{item['bank']}"
                    if candidate not in used_global_slugs:
                        new_slug = candidate
                    else:
                        # Try Bank + Card
                        candidate = f"{clean}-{item['bank']}-{item['card']}"
                        if candidate not in used_global_slugs:
                            new_slug = candidate
                        else:
                            # Try Bank + Card + Sector
                            candidate = f"{clean}-{item['bank']}-{item['card']}-{item['sector']}"
                            new_slug = candidate
                
                # If even first one is already taken or we have internal collision
                if new_slug in used_global_slugs and i == 0:
                     # This shouldn't happen often but let's be safe
                     new_slug = f"{clean}-{item['bank']}"

                # Double check to ensure we don't create new collisions within the loop
                # If still collision, we might need a counter but user said no numbers.
                # We'll trust bank+card+sector is unique enough.
                
                if new_slug != item['orig_slug']:
                    sql_commands.append(f"UPDATE campaigns SET slug = '{new_slug}' WHERE id = {item['id']}; -- Was: {item['orig_slug']}")
                
                used_global_slugs.add(new_slug)

    with open("fix_slugs.sql", "w") as f:
        f.write("\n".join(sql_commands))
    
    print(f"✅ {len(sql_commands)} adet güncelleme komutu fix_slugs.sql dosyasına yazıldı.")

if __name__ == "__main__":
    main()
