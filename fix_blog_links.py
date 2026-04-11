import os
import re
import psycopg2
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DB_URL)

def fix_links(html):
    if not html:
        return html
    
    soup = BeautifulSoup(html, 'html.parser')
    links = soup.find_all('a', href=re.compile(r'/kampanya/'))
    
    changed = False
    for link in links:
        href = link.get('href', '')
        # Pattern: /kampanya/banka-kategori-extra-id
        # We want to extract banka and kategori
        slug_part = href.replace('/kampanya/', '').split('-')
        
        # This is a heuristic based on slug structure
        # Most slugs are bank-brand-sector-id or similar
        # If we can't be precise, we at least link to the home or category
        
        new_href = "/" # Fallback
        
        # Simple heuristic: if we see a bank name in slug, use it
        banks = ['axess', 'bonus', 'maximum', 'world', 'paraf', 'cardfinans', 'wings', 'qnb', 'garanti', 'akbank', 'isbank', 'yapikredi']
        sectors = ['market', 'akaryakit', 'e-ticaret', 'giyim', 'restoran', 'seyahat', 'elektronik']
        
        found_bank = next((b for b in banks if b in href.lower()), None)
        found_sector = next((s for s in sectors if s in href.lower()), None)
        
        if found_bank and found_sector:
            new_href = f"/banka/{found_bank}/{found_sector}"
        elif found_bank:
            new_href = f"/banka/{found_bank}"
        elif found_sector:
            new_href = f"/kategori/{found_sector}"
        else:
            new_href = "/kampanyalar"

        print(f"  🔄 Converting: {href} -> {new_href}")
        link['href'] = new_href
        changed = True
    
    # Also add the dynamic widget tag at the end if we made changes
    if changed:
        new_tag = soup.new_tag("div")
        new_tag.string = "[[GUNCEL_KAMPANYALAR]]"
        soup.append(new_tag)
        
    return str(soup) if changed else html

def main():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, slug, content_html FROM blogs WHERE content_html LIKE '%/kampanya/%'")
        rows = cur.fetchall()
        print(f"🔍 Found {len(rows)} blogs with hardcoded links.")
        
        for b_id, slug, html in rows:
            print(f"Processing blog: {slug}")
            fixed_html = fix_links(html)
            if fixed_html != html:
                cur.execute("UPDATE blogs SET content_html = %s WHERE id = %s", (fixed_html, b_id))
                conn.commit()
                print(f"✅ Blog {slug} updated.")
            else:
                print(f"ℹ️ No changes needed for {slug}.")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
