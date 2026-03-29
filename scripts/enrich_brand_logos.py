import os
import sys
import requests
from bs4 import BeautifulSoup
from thefuzz import fuzz, process
from slugify import slugify
from sqlalchemy import update
import logging

# Add src to path if needed
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from src.database import get_db_session
    from src.models import Brand
except ImportError:
    # Handle direct script execution
    sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
    from database import get_db_session
    from models import Brand

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

HOPI_BRANDS_URL = "https://www.hopi.com.tr/markalar"
GETKAMPANIA_LOGOS_BASE = "https://d353ysg0lognn3.cloudfront.net/brands/"

def get_hopi_brand_map():
    """Scrapes Hopi and returns a dict of {brand_name: logo_url}"""
    logger.info("Scraping Hopi brands...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "max-age=0",
        "Referer": "https://www.hopi.com.tr/",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1"
    }
    try:
        response = requests.get(HOPI_BRANDS_URL, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        
        brand_map = {}
        # Based on subagent research, brands are in .brand-list-item or similar
        brand_items = soup.select('.brand-list-item a, a[href*="-kampanyalari"]')
        
        for item in brand_items:
            img = item.find('img')
            name_span = item.find('span')
            
            # Defensive check for name
            name = None
            if name_span:
                name = name_span.get_text(strip=True)
            elif item.get('title'):
                name = item.get('title')
            elif img and img.get('alt'):
                name = img.get('alt')
            
            # Defensive check for logo
            logo = None
            if img:
                logo = img.get('src') or img.get('data-src') or img.get('data-original')
            
            if name and logo:
                # Ensure full URL
                if logo.startswith('//'):
                    logo = 'https:' + logo
                elif logo.startswith('/'):
                    logo = 'https://www.hopi.com.tr' + logo
                
                brand_map[name.strip()] = logo
                
        logger.info(f"Successfully parsed {len(brand_map)} brands from Hopi.")
        return brand_map
    except Exception as e:
        logger.error(f"Error scraping Hopi: {e}")
        return {}

def check_url(url):
    """Checks if a URL returns 200 via HEAD request"""
    try:
        res = requests.head(url, timeout=5)
        return res.status_code == 200
    except:
        return False

def enrich_logos(dry_run=True):
    db = get_db_session()
    try:
        brands = db.query(Brand).all()
        hopi_map = get_hopi_brand_map()
        hopi_names = list(hopi_map.keys())
        
        updated_count = 0
        missed_count = 0
        matches = []

        for brand in brands:
            found_logo = None
            source = None
            
            # 1. Try Hopi via fuzzy matching
            best_match_tuple = process.extractOne(brand.name, hopi_names, scorer=fuzz.token_set_ratio)
            if best_match_tuple and best_match_tuple[1] > 90:
                match_name = best_match_tuple[0]
                found_logo = hopi_map[match_name]
                source = "Hopi"
            
            # 2. If not found on Hopi, try GetKampania prediction
            if not found_logo:
                gk_url = f"{GETKAMPANIA_LOGOS_BASE}{brand.slug}.png"
                if check_url(gk_url):
                    found_logo = gk_url
                    source = "GetKampania"
            
            if found_logo:
                if brand.logo_url != found_logo:
                    matches.append(f"[MATCH] {brand.name} -> {source} ({found_logo})")
                    if not dry_run:
                        brand.logo_url = found_logo
                    updated_count += 1
            else:
                missed_count += 1
        
        for msg in matches:
            print(msg)
            
        logger.info(f"Summary: {updated_count} brands matched, {missed_count} missed.")
        
        if not dry_run and updated_count > 0:
            db.commit()
            logger.info("Changes committed to database.")
        else:
            logger.info("Dry run completed. No changes made.")
            
    finally:
        db.close()

if __name__ == "__main__":
    is_dry = "--commit" not in sys.argv
    enrich_logos(dry_run=is_dry)
