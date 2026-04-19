import re
from sqlalchemy import text
from src.database import SessionLocal

def slugify(text_val):
    if not text_val:
        return ""
    # Map Turkish chars explicitly
    s = text_val.replace('İ', 'i').replace('I', 'i').replace('ı', 'i')
    s = s.replace('Ğ', 'g').replace('ğ', 'g')
    s = s.replace('Ü', 'u').replace('ü', 'u')
    s = s.replace('Ş', 's').replace('ş', 's')
    s = s.replace('Ö', 'o').replace('ö', 'o')
    s = s.replace('Ç', 'c').replace('ç', 'c')
    
    import unicodedata
    # NFD normalization
    s = unicodedata.normalize('NFD', s)
    # Strip combining marks
    s = re.sub(r'[\u0300-\u036f]', '', s)
    # Lowercase
    s = s.lower()
    # Replace non-alphanumeric with dash
    s = re.sub(r'[^a-z0-9]+', '-', s)
    # Strip trailing/leading dashes
    s = s.strip('-')
    # Remove multiple dashes
    s = re.sub(r'-+', '-', s)
    return s

def fix_slugs():
    db = SessionLocal()
    try:
        campaigns = db.execute(text("SELECT id, title, slug FROM \"campaigns\"")).fetchall()
        
        fixed_count = 0
        for c in campaigns:
            c_id = c[0]
            title = c[1]
            old_slug = c[2]
            
            # Known broken patterns
            is_broken = ('-i-' in old_slug or '-u-' in old_slug or '-s-' in old_slug 
                         or '-c-' in old_slug or '-g-' in old_slug or '-o-' in old_slug 
                         or old_slug.endswith('-i') or old_slug.endswith('-u')
                         or old_slug.startswith('i-') or old_slug.startswith('u-')
                         or old_slug.startswith('s-') or old_slug.startswith('o-')
                         or old_slug.startswith('g-'))
            
            if is_broken:
                new_base = slugify(title)
                # Ensure uniqueness
                final_slug = f"{new_base}-{c_id}"
                
                print(f"[{c_id}] {title}")
                print(f"  OLD: {old_slug}")
                print(f"  NEW: {final_slug}")
                
                db.execute(text("UPDATE \"campaigns\" SET slug = :s WHERE id = :id"), {"s": final_slug, "id": c_id})
                fixed_count += 1
                
        db.commit()
        print(f"\nFixed {fixed_count} broken slugs.")
    finally:
        db.close()

if __name__ == "__main__":
    fix_slugs()
