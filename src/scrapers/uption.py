
import os
import time
import random
import re
import json
import sys
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urljoin

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sqlalchemy.orm import Session # type: ignore
from sqlalchemy.exc import IntegrityError # type: ignore
from bs4 import BeautifulSoup # type: ignore
from dotenv import load_dotenv # type: ignore
from selenium import webdriver # type: ignore
from selenium.webdriver.chrome.webdriver import WebDriver # type: ignore
from selenium.webdriver.chrome.service import Service # type: ignore
from webdriver_manager.chrome import ChromeDriverManager # type: ignore
from selenium_stealth import stealth # type: ignore
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore

# Database & Services
from src.database import get_db_session # type: ignore
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand # type: ignore
from src.services.ai_parser import parse_api_campaign # type: ignore
from src.utils.logger_utils import log_scraper_execution # type: ignore
from src.utils.scraper_utils import should_skip_campaign # type: ignore
from src.utils.slug_generator import get_unique_slug # type: ignore
from src.services.brand_matcher import get_or_create_brands_list # type: ignore

try:
    from pyvirtualdisplay import Display # type: ignore
    HAS_VIRTUAL_DISPLAY = True
except ImportError:
    HAS_VIRTUAL_DISPLAY = False
    def Display(*args, **kwargs): return None

load_dotenv()

class UptionScraper:
    BASE_URL = "https://www.uption.com.tr"
    CAMPAIGNS_URL = "https://www.uption.com.tr/kampanyalar"
    BANK_NAME = "Uption"
    CARD_NAME = "Uption Kart"

    def __init__(self):
        self.driver: Optional[WebDriver] = None
        self.display: Optional[Any] = None
        self.db: Optional[Session] = None
        
        # Caches
        self.bank_cache: Optional[Bank] = None
        self.card_cache: Dict[str, Card] = {}
        self.sector_cache: Dict[str, Sector] = {}
        self.brand_cache: Dict[str, Brand] = {}

    def setup_driver(self):
        """Initialize Selenium with Stealth Mode."""
        if self.driver:
            return

        if sys.platform.startswith('linux') and HAS_VIRTUAL_DISPLAY:
            try:
                self.display = Display(visible=0, size=(1920, 1080))
                if self.display:
                    self.display.start() # type: ignore
            except Exception as e:
                print(f"⚠️ Failed to start virtual display: {e}")

        print("   🔌 Initializing Browser Driver (Chrome + Stealth)...")
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            
            stealth(self.driver,
                languages=["tr-TR", "tr"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
            print("   ✅ Browser launched successfully.")
        except Exception as e:
            print(f"   ❌ Failed to launch browser: {e}")
            raise e

    def close_driver(self):
        driver = self.driver
        if driver:
            print("   🛑 Closing Browser...")
            try:
                driver.quit()
            except:
                pass
            self.driver = None
            
        display = self.display
        if display:
            try:
                display.stop()
            except:
                pass
            self.display = None

    def run(self, limit: Optional[int] = None, force: bool = False):
        print(f"🚀 Starting Uption Scraper...")
        try:
            self.db = get_db_session()
            self._load_cache()
            self.setup_driver()

            driver = self.driver
            if driver:
                driver.get(self.CAMPAIGNS_URL)
                time.sleep(3)
                
                # Uption has tabs, but "Tüm Kampanyalar" is active by default.
                # If we need to click, we would do it here.
                
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                cards = soup.select('a.helpfull-tab-card')
                print(f"   🎯 Found {len(cards)} strategy cards.")

                found_items = []
                for card in cards:
                    href = card.get('href')
                    if href:
                        url = urljoin(self.BASE_URL, href)
                        # Extract basic info from card
                        title_div = card.select_one('div')
                        item_title = title_div.get_text(strip=True) if title_div else ""
                        
                        img_el = card.select_one('img')
                        list_image = img_el.get('src') if img_el else ""
                        if list_image and not list_image.startswith('http'):
                            list_image = urljoin(self.BASE_URL, list_image)

                        found_items.append({
                            'url': url,
                            'title': item_title,
                            'list_image': list_image
                        })

                if limit and isinstance(limit, int):
                    found_items = list(found_items)[:limit] # type: ignore

                success_count = 0

                total_revived = 0
                skipped_count = 0
                failed_count = 0

                for i, item in enumerate(found_items, 1):
                    url = item['url']
                    print(f"   [{i}/{len(found_items)}] Processing: {url}")
                    
                    try:
                        res = self._process_campaign(item, force=force)
                        if res == "saved":
                            success_count += 1 # type: ignore
                        elif res == "skipped":
                            skipped_count += 1 # type: ignore
                        else:
                            failed_count += 1 # type: ignore
                    except Exception as e:
                        print(f"      ❌ Error: {e}")
                        failed_count += 1
                    
                    time.sleep(random.uniform(1, 2))

                log_scraper_execution(
                    db=self.db,
                    scraper_name="uption",
                    status="SUCCESS" if failed_count == 0 else "PARTIAL",
                    total_found=len(found_items),
                    total_saved=success_count,
                    total_skipped=skipped_count,
                    total_failed=failed_count, total_revived=total_revived
                )

        except Exception as e:
            print(f"❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.close_driver()
            db = self.db
            if db:
                db.close()

    def _load_cache(self):
        db = self.db
        if not db: return

        bank = db.query(Bank).filter(Bank.slug == "uption").first()
        if not bank:
            bank = Bank(name="Uption", slug="uption", is_active=True)
            db.add(bank)
            db.commit()
        self.bank_cache = bank

        for c in db.query(Card).filter(Card.bank_id == bank.id).all():
            self.card_cache[c.name.lower()] = c
            
        for s in db.query(Sector).all():
            self.sector_cache[s.slug] = s
            self.sector_cache[s.name.lower()] = s
            
        for b in db.query(Brand).all():
            self.brand_cache[b.name.lower()] = b

    def _process_campaign(self, item: Dict, force: bool = False) -> str:
        url = item['url']
        db = self.db
        driver = self.driver
        
        if not force and db:
            if should_skip_campaign(db, url):
                print(f"      ⏭️  Skipped (Already exists or blocked)")
                return "skipped"

        if not driver: return "failed"
        
        driver.get(url)
        time.sleep(2)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Detail extraction
        title_el = soup.select_one('h1') or soup.select_one('h2')
        title = title_el.get_text(strip=True) if title_el else item['title']
        
        # Content - Look for the rich text blocks (including the one with dates)
        content_parts = []
        h1_el = soup.select_one('h1.h1-landing-pages-2') or soup.select_one('h1')
        if h1_el:
            content_parts.append(f"TITLE: {h1_el.get_text(strip=True)}")
            
        # Uption often uses these cryptic Webflow classes
        selectors = [
            '.cms-content', 
            '.rich-text-block-3', 
            '.rich-text-v2', 
            '._18p-left-13p-top-margin-block',
            '.campaign-detail-content',
            '.w-richtext'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for el in elements:
                txt = el.get_text(separator='\n', strip=True)
                if len(txt) > 20: # Avoid tiny noise
                    content_parts.append(txt)
        
        if not content_parts:
            # Last resort
            content_div = soup.select_one('main') or soup.select_one('article') or soup.find('body')
            raw_content = content_div.get_text(separator='\n', strip=True) if content_div else title
        else:
            # Use dict.fromkeys to preserve order and remove potential duplicate blocks
            raw_content = "\n\n".join(dict.fromkeys(content_parts))

        # Higher quality image from detail page?
        detail_img_el = soup.select_one('img.campaign-detail-image') or \
                        soup.select_one('img.image-46') or \
                        soup.select_one('.w-richtext img')
        
        image_url = detail_img_el.get('src') if detail_img_el else item['list_image']
        if image_url and not image_url.startswith('http'):
            image_url = urljoin(self.BASE_URL, image_url)

        # AI Parse
        ai_data = parse_api_campaign(
            title=title,
            short_description=item['title'],
            content_html=raw_content,
            bank_name=self.BANK_NAME,
            tracking_url=url,
            force=force
        )

        if not ai_data:
            print("      ❌ AI parsing failed.")
            return "failed"

        self._save_campaign(ai_data, url, image_url)
        return locals().get("_op_status", "saved")

    def _save_campaign(self, data: Dict, url: str, image_url: str):
        db = self.db
        if not db: return
        
        bank_cache = self.bank_cache
        bank_id = bank_cache.id if bank_cache else None
        
        # Get or create card
        card_name = self.CARD_NAME
        card = self.card_cache.get(card_name.lower())
        if not card:
            card = Card(bank_id=bank_id, name=card_name, slug="uption-kart", is_active=True)
            db.add(card)
            db.flush()
            self.card_cache[card_name.lower()] = card

        # Sector
        sector_slug = data.get("sector", "diger")
        sector = self.sector_cache.get(sector_slug.lower()) or self.sector_cache.get("diger")
        
        # Date conversion
        start_date = None
        end_date = None
        if data.get("start_date"):
            try:
                start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
            except Exception:
                pass
        if data.get("end_date"):
            try:
                end_date = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
            except Exception:
                pass

        # Create Campaign
        try:
            slug = get_unique_slug(data.get("title", "uption-kampanya"), db, Campaign)
            
            campaign = Campaign(
                card_id=card.id if card else None,
                sector_id=sector.id if sector else None,
                slug=slug,
                title=data.get("title", "Uption Kampanya"),
                description=data.get("description", ""),
                ai_marketing_text=ai_data.get("ai_marketing_text") or data.get("description", ""),
                conditions="\n".join(data.get("conditions", [])) if data.get("conditions") else None,
                eligible_cards=", ".join(data.get("cards", [])) if data.get("cards") else None,
                participation=data.get("participation", "Uption mobil uygulaması üzerinden katılabilirsiniz."),
                reward_text=data.get("reward_text"),
                reward_value=data.get("reward_value"),
                reward_type=data.get("reward_type"),
                image_url=image_url,
                tracking_url=url,
                start_date=start_date,
                end_date=end_date,
                is_active=True,
                clean_text=data.get("_clean_text")
            )
            from src.utils.scraper_utils import upsert_campaign
            campaign, _op_status = upsert_campaign(db, campaign)
            db.flush() # Get campaign.id

            # Brands via brand_matcher
            brand_ids = get_or_create_brands_list(
                db_session=db,
                brand_names=data.get("brands", []),
                brand_cache=getattr(self, 'brand_cache', {}),
                sector_id=sector.id if sector else None
            )
            
            for bid in brand_ids:
                link = CampaignBrand(campaign_id=campaign.id, brand_id=bid)
                db.add(link)
            
            db.commit()
            print(f"      ✅ Saved: {campaign.title}")
            
        except Exception as e:
            if db: db.rollback()
            print(f"      ❌ Save error: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit campaigns")
    parser.add_argument("--force", action="store_true", help="Force run")
    args = parser.parse_args()
    
    scraper = UptionScraper()
    scraper.run(limit=args.limit, force=args.force)
