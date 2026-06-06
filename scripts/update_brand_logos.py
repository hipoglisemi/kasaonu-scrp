import os
import sys
import requests
from io import BytesIO
from PIL import Image
from thefuzz import fuzz
from google_play_scraper import search as play_search

# Add src to path so we can import from database and models
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from database import get_db_session
from models import Brand

PUBLIC_BRANDS_DIR = "/Users/hipoglisemi/Desktop/kartavantaj/public/logos/brands"

def is_valid_match(brand_name, app_title):
    b_name = brand_name.lower().strip()
    a_title = app_title.lower().strip()
    
    # 1. Substring match is usually the safest for app names (e.g. "Migros" in "Migros - Sanal Market")
    if b_name in a_title:
        return True
        
    # 2. Fuzzy match
    ratio = fuzz.token_sort_ratio(b_name, a_title)
    if ratio >= 65:
        return True
        
    return False

def download_image_and_save(image_url, slug):
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        
        # Open image with Pillow
        img = Image.open(BytesIO(response.content))
        
        # Convert to RGB
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.convert('RGBA').split()[3])
            img = background
        else:
            img = img.convert('RGB')
            
        os.makedirs(PUBLIC_BRANDS_DIR, exist_ok=True)
        file_path = os.path.join(PUBLIC_BRANDS_DIR, f"{slug}.webp")
        img.save(file_path, "WEBP", quality=80, method=6)
        print(f"  [+] Saved {file_path}")
        return True
    except Exception as e:
        print(f"  [-] Failed to download/save image from {image_url}: {e}")
        return False

def search_app_store(brand_name):
    url = f"https://itunes.apple.com/search?term={brand_name}&entity=software&country=tr&limit=1"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get('resultCount', 0) > 0:
            result = data['results'][0]
            app_title = result.get('trackName', '')
            if is_valid_match(brand_name, app_title):
                return result.get('artworkUrl512')
            else:
                print(f"  [App Store] Skipped due to low match: '{brand_name}' != '{app_title}'")
    except Exception as e:
        print(f"  [!] App Store API error for {brand_name}: {e}")
    return None

def search_play_store(brand_name):
    try:
        results = play_search(brand_name, lang="tr", country="tr")
        if results and len(results) > 0:
            result = results[0]
            app_title = result.get('title', '')
            if is_valid_match(brand_name, app_title):
                icon_url = result.get('icon')
                if icon_url:
                    if "=" in icon_url:
                        icon_url = icon_url.split("=")[0] + "=s512-rw"
                    return icon_url
            else:
                print(f"  [Google Play] Skipped due to low match: '{brand_name}' != '{app_title}'")
    except Exception as e:
        print(f"  [!] Play Store scraper error for {brand_name}: {e}")
    return None

def main():
    print("Starting Strict Brand Logo Refresh...")
    db = get_db_session()
    
    try:
        brands = db.query(Brand).all()
        print(f"Total brands found in DB: {len(brands)}")
        
        updated_count = 0
        
        force_all = len(sys.argv) > 1 and sys.argv[1] == '--force-all'
        
        for brand in brands:
            needs_update = False
            file_path = os.path.join(PUBLIC_BRANDS_DIR, f"{brand.slug}.webp")
            
            if force_all:
                needs_update = True
                print(f"\n[{brand.name}] - Force update requested.")
            elif not brand.logo_url:
                needs_update = True
                print(f"\n[{brand.name}] - Missing logo_url in DB.")
            elif not os.path.exists(file_path):
                needs_update = True
                print(f"\n[{brand.name}] - File missing from disk ({file_path}).")
                
            if needs_update:
                print(f"  Searching for logo...")
                image_url = None
                
                # 1. Try App Store
                image_url = search_app_store(brand.name)
                
                if image_url:
                    print(f"  [App Store] Found matched icon: {image_url}")
                else:
                    # 2. Try Google Play Store
                    image_url = search_play_store(brand.name)
                    if image_url:
                        print(f"  [Google Play] Found matched icon: {image_url}")
                
                # 3. Download and Save
                if image_url:
                    success = download_image_and_save(image_url, brand.slug)
                    if success:
                        brand.logo_url = f"/logos/brands/{brand.slug}.webp"  # type: ignore
                        db.commit()
                        updated_count += 1
                else:
                    print(f"  [-] Could not find any confident logo match for {brand.name}.")

        print(f"\nFinished! Successfully updated/refreshed logos for {updated_count} brands.")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
