import os
import time
import random
import re
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urljoin

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sqlalchemy.orm import Session # type: ignore
from bs4 import BeautifulSoup # type: ignore
from dotenv import load_dotenv # type: ignore
from selenium import webdriver # type: ignore
from selenium.webdriver.chrome.webdriver import WebDriver # type: ignore
from selenium_stealth import stealth # type: ignore
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore

# Database & Services
from src.database import get_db_session # type: ignore
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand # type: ignore
from src.services.ai_parser import AIParser # type: ignore
from src.services.brand_matcher import get_or_create_brands_list # type: ignore
from src.utils.logger_utils import log_scraper_execution # type: ignore
from src.utils.scraper_utils import should_skip_campaign # type: ignore
from src.utils.slug_generator import get_unique_slug # type: ignore

load_dotenv()

class PetrolOfisiScraper:
    BASE_URL = "https://www.petrolofisi.com.tr"
    TARGET_URL = "https://www.petrolofisi.com.tr/kampanyalar"
    SOURCE_NAME = "Petrol Ofisi"
    
    def __init__(self):
        self.driver: Optional[WebDriver] = None
        self.db: Optional[Session] = None
        self.parser = AIParser()
        
        # Caches
        self.bank_cache: Optional[Bank] = None
        self.card_cache: Dict[str, Card] = {}
        self.brand_cache: Dict[str, Brand] = {}

    def setup_driver(self):
        """Initialize Selenium with Stealth Mode."""
        if self.driver:
            return

        print("   🔌 Initializing Browser Driver (Chrome + Stealth)...")
        options = webdriver.ChromeOptions()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        options.add_argument("--remote-debugging-port=9222") # Better stability in some headless environments
        
        if os.getenv("DOCKER_MODE") == "true" or os.environ.get("HEADLESS") == "1":
            options.add_argument('--headless=new')

        # Add a small delay before starting driver to ensure Xvfb is ready
        time.sleep(1)
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(60) # Prevent indefinite hangs
        
        stealth(self.driver,
                languages=["tr-TR", "tr"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
                )

    def _get_or_create_bank(self, db: Session) -> Bank:
        if self.bank_cache:
            return self.bank_cache
            
        bank = db.query(Bank).filter(Bank.slug == "petrol-ofisi").first()
        if not bank:
            bank = Bank(
                name="Petrol Ofisi",
                slug="petrol-ofisi",
                logo_url="https://www.petrolofisi.com.tr/assets/images/logo.png",
                is_active=True
            )
            db.add(bank)
            db.commit()
            db.refresh(bank)
        self.bank_cache = bank
        return bank

    def _get_or_create_card(self, db: Session, bank_id: int) -> Card:
        slug = "petrol-ofisi-kart"
        if slug in self.card_cache:
            return self.card_cache[slug]
            
        card = db.query(Card).filter(Card.slug == slug).first()
        if not card:
            card = Card(
                bank_id=bank_id,
                name="Petrol Ofisi Kart",
                slug=slug,
                is_active=True
            )
            db.add(card)
            db.commit()
            db.refresh(card)
        self.card_cache[slug] = card
        return card

    def scrape(self, limit: Optional[int] = None):
        """Main scrape entry point. If limit is None, fetches all."""
        print(f"🚀 Starting {self.SOURCE_NAME} Scraper...")
        self.db = get_db_session()
        
        limit = limit or 999 # Safe high default for 'all'
        
        stats = {
            "total_found": 0,
            "total_saved": 0,
            "total_skipped": 0,
            "total_failed": 0,
            "errors": []
        }

        try:
            self.setup_driver()
            if not self.driver:
                raise Exception("Failed to initialize driver")

            self.driver.get(self.TARGET_URL)
            time.sleep(5) # Give more time for heavy JS

            # Accept cookies if any overlay appears
            try:
                # Specific "ANLADIM" button observed in browser test
                cookie_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-accept, #CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, .btn.btn-primary:has-text('ANLADIM')"))
                )
                cookie_btn.click()
                time.sleep(1)
            except:
                pass

            # Handling "Daha Fazla Göster"
            print("   ⏳ Loading all campaigns (Clicking 'Daha Fazla Göster')...")
            click_count = 0
            while click_count < 10: # Safety break
                try:
                    # Selector for Petrol Ofisi 'Daha fazla göster' button
                    btn = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "button.show-more, .btn.btn-primary.show-more"))
                    )
                    
                    if not btn.is_displayed():
                        break
                        
                    # Scroll to button
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(1)
                    
                    try:
                        btn.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", btn)
                        
                    click_count += 1
                    print(f"   🖱️ Clicked 'Show More' {click_count} times.")
                    time.sleep(3) # Give more time for PO list to expand
                except:
                    # Button no longer exists or not clickable
                    break

            # Collect cards
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            # Petrol Ofisi cards verified selector: .card-campaign
            cards = soup.select(".card-campaign")
            print(f"   🎯 Found {len(cards)} potential campaign cards.")

            bank = self._get_or_create_bank(self.db)
            card = self._get_or_create_card(self.db, bank.id)

            processed_count = 0
            for card_soup in cards:
                if processed_count >= limit:
                    break

                try:
                    # Link & Title
                    link_tag = card_soup.select_one("a[href*='/kampanyalar/']")
                    if not link_tag:
                        continue
                        
                    relative_url = link_tag.get("href")
                    if not relative_url:
                        continue

                    # Skip non-campaign links
                    if "biten-kampanyalar" in relative_url or relative_url.endswith("/kampanyalar") or relative_url == "/kampanyalar/":
                        continue

                    detail_url = urljoin(self.BASE_URL, relative_url)
                    
                    title_tag = card_soup.select_one(".card-title, h5, h4, .title")
                    title = title_tag.get_text(strip=True) if title_tag else ""
                    
                    if not title or title.lower() == "kampanyalar":
                        # If card title fails, we'll try to get it from detail page later or use a better fallback
                        title = "Petrol Ofisi Kampanyası"
                    
                    # Image
                    img_tag = card_soup.select_one("img")
                    img_url = urljoin(self.BASE_URL, img_tag.get("src")) if img_tag else None

                    # Check DB/Blocklist
                    if should_skip_campaign(self.db, detail_url):
                        stats["total_skipped"] += 1
                        continue

                    # Visit Detail Page
                    print(f"   [{(processed_count+1)}] Processing: {detail_url}")
                    self.driver.get(detail_url)
                    time.sleep(2)
                    
                    detail_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                    content_area = detail_soup.select_one("main, .content, .campaign-detail")
                    raw_html = str(content_area) if content_area else self.driver.page_source

                    # AI Parsing
                    ai_data = self.parser.parse_campaign_data(
                        raw_text=raw_html,
                        title=title,
                        bank_name="Petrol Ofisi",
                        tracking_url=detail_url
                    )

                    if not ai_data or ai_data.get("_ai_failed"):
                        print(f"      ⚠️ AI parsing failed for: {title}")
                        stats["total_failed"] += 1
                        continue

                    # Create Campaign & Slug
                    campaign_slug = get_unique_slug(title, self.db, Campaign)
                    
                    new_campaign = Campaign(
                        card_id=card.id,
                        slug=campaign_slug,
                        title=ai_data.get("title", title),
                        reward_text=ai_data.get("reward_text"),
                        reward_value=ai_data.get("reward_value"),
                        reward_type=ai_data.get("reward_type"),
                        description=ai_data.get("description"),
                        conditions="\n".join(ai_data.get("conditions", [])),
                        image_url=img_url or ai_data.get("image_url"),
                        participation=ai_data.get("participation"),
                        eligible_cards=", ".join(ai_data.get("cards", [])),
                        start_date=datetime.strptime(ai_data["start_date"], "%Y-%m-%d").date() if ai_data.get("start_date") else None,
                        end_date=datetime.strptime(ai_data["end_date"], "%Y-%m-%d").date() if ai_data.get("end_date") else None,
                        tracking_url=detail_url,
                        is_active=True,
                        clean_text=ai_data.get("_clean_text"),
                        sector_id=self._get_sector_id(ai_data.get("sector", "akaryakit"))
                    )

                    self.db.add(new_campaign)
                    self.db.flush() # Get ID

                    # Brand Matching
                    brand_names = ai_data.get("brands", [])
                    if "Petrol Ofisi" not in brand_names:
                        brand_names.append("Petrol Ofisi")
                        
                    brand_ids = get_or_create_brands_list(
                        self.db,
                        brand_names,
                        self.brand_cache
                    )

                    for b_id in brand_ids:
                        cb = CampaignBrand(campaign_id=new_campaign.id, brand_id=b_id)
                        self.db.add(cb)

                    self.db.commit()
                    stats["total_saved"] += 1
                    processed_count += 1
                    print(f"      ✅ Saved: {title}")

                except Exception as e:
                    print(f"      ❌ Error processing card: {e}")
                    stats["total_failed"] += 1
                    stats["errors"].append(str(e))
                    self.db.rollback()

        except Exception as e:
            print(f"   ❌ Scraper Crashed: {e}")
            stats["status"] = "FAILED"
            stats["errors"].append(str(e))
        finally:
            if self.driver:
                self.driver.quit()
            if self.db:
                self.db.close()
            
        # Log Result
        log_scraper_execution(
            db=self.db,
            scraper_name=self.SOURCE_NAME,
            status=stats.get("status", "SUCCESS"),
            total_found=len(cards) if 'cards' in locals() else 0,
            total_saved=stats["total_saved"],
            total_skipped=stats["total_skipped"],
            total_failed=stats["total_failed"],
            error_details={"errors": stats["errors"]} if stats["errors"] else None
        )
        print(f"🏁 Finished {self.SOURCE_NAME}. Saved: {stats['total_saved']}, Skipped: {stats['total_skipped']}, Failed: {stats['total_failed']}")

    def _get_sector_id(self, sector_slug: str) -> Optional[int]:
        """Maps AI sector slug to DB sector ID."""
        sector = self.db.query(Sector).filter(Sector.slug == sector_slug).first()
        if not sector:
            sector = self.db.query(Sector).filter(Sector.slug == "akaryakit").first()
        return sector.id if sector else None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit campaigns to process")
    args = parser.parse_args()
    
    scraper = PetrolOfisiScraper()
    scraper.scrape(limit=args.limit)
