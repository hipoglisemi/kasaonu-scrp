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

class OpetScraper:
    BASE_URL = "https://www.opet.com.tr"
    TARGET_URL = "https://www.opet.com.tr/kampanyalar"
    SOURCE_NAME = "Opet"
    
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
        options.page_load_strategy = 'eager'
        
        if os.getenv("DOCKER_MODE") == "true" or os.environ.get("HEADLESS") == "1":
            options.add_argument('--headless=new')

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(90)
        
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
            
        bank = db.query(Bank).filter(Bank.slug == "opet").first()
        if not bank:
            bank = Bank(
                name="Opet",
                slug="opet",
                logo_url="https://www.opet.com.tr/Assets/img/opet-logo.png",
                is_active=True
            )
            db.add(bank)
            db.commit()
            db.refresh(bank)
        self.bank_cache = bank
        return bank

    def _get_or_create_card(self, db: Session, bank_id: int) -> Card:
        slug = "opet-kart"
        if slug in self.card_cache:
            return self.card_cache[slug]
            
        card = db.query(Card).filter(Card.slug == slug).first()
        if not card:
            card = Card(
                bank_id=bank_id,
                name="Opet Kart",
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
            driver = self.driver
            driver.get(self.TARGET_URL)
            time.sleep(3)

            # Accept cookies if any overlay appears
            try:
                # Common selectors for Opet cookies
                cookie_btn = driver.find_element(By.CSS_SELECTOR, "#kabul-et, .cookie-accept, .btn-accept")
                cookie_btn.click()
                time.sleep(1)
            except:
                pass

            # Handling "Daha Fazla Göster"
            print("   ⏳ Loading all campaigns (Clicking 'Daha Fazla Göster')...")
            click_count = 0
            while click_count < 20:
                try:
                    # More robust selector covering different button variants
                    selectors = [
                        "a.btn.btn-primary.mx-auto", 
                        "div.btn-more", 
                        "a[href='#'].btn",
                        ".campaign-list-more a"
                    ]
                    
                    btn = None
                    for selector in selectors:
                        try:
                            found = WebDriverWait(self.driver, 3).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                            )
                            if found.is_displayed() and "DAHA FAZLA" in found.text.upper():
                                btn = found
                                break
                        except:
                            continue

                    if not btn:
                        break
                        
                    # Scroll to button
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(1)
                    
                    # Use JS click for reliability
                    self.driver.execute_script("arguments[0].click();", btn)
                        
                    click_count += 1
                    print(f"   🖱️ Clicked 'Show More' {click_count} times.")
                    time.sleep(3) # Wait for content to load
                except Exception as e:
                    break

            # Collect cards
            time.sleep(5) # Final wait for everything to render
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            cards = soup.select("a.position-relative.h-100, .campaign-item")
            
            if not cards:
                print("   ⚠️ No cards found with '.campaign-item'. Diagnostic info:")
                unique_classes = sorted(list(set([cls for el in soup.find_all(True) for cls in el.get("class", [])])))
                print(f"   📂 Found {len(unique_classes)} unique classes in DOM.")
                print(f"   📑 First 1000 chars of source: {self.driver.page_source[:1000]}")
                # Try fallback selector from previous version
                cards = soup.select("div.col-12.col-md-6.col-lg-3")
                if cards:
                    print(f"   💡 Fallback selector 'div.col-12.col-md-6.col-lg-3' found {len(cards)} cards.")

            print(f"   🎯 Found {len(cards)} potential campaign cards.")

            bank = self._get_or_create_bank(self.db)
            card = self._get_or_create_card(self.db, bank.id)

            processed_count = 0
            for card_soup in cards:
                if processed_count >= limit:
                    break

                try:
                    # Link & Title extraction
                    # Card itself might be the link, or it might contain a link
                    link_tag = card_soup if card_soup.name == "a" else card_soup.select_one("a[href*='kampanya'], a.position-relative, a[href*='/kampanyalar/']")
                    
                    if not link_tag and card_soup.name != "a":
                        link_tag = card_soup.select_one("a") # Fallback to any link
                        
                    if not link_tag or not link_tag.get("href"):
                        continue
                        
                    relative_url = link_tag.get("href")
                    detail_url = urljoin(self.BASE_URL, relative_url)
                    
                    # Title extraction
                    title = link_tag.get_text(strip=True)
                    if not title or len(title) < 5:
                        title_tag = card_soup.select_one("h3, h4, .title, .card-title")
                        title = title_tag.get_text(strip=True) if title_tag else "Opet Kampanyası"
                    
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
                    time.sleep(6) # Increased to allow React SPA to fully render campaign conditions
                    
                    detail_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                    # Main content area - Opet details are usually in .bg-light or .detail-content
                    content_area = detail_soup.select_one("main, .container, .detail-content")
                    raw_html = str(content_area) if content_area else self.driver.page_source

                    # AI Parsing
                    ai_data = self.parser.parse_campaign_data(
                        raw_text=raw_html,
                        title=title,
                        bank_name="Genel",
                        tracking_url=detail_url
                    )

                    if not ai_data or ai_data.get("_ai_failed"):
                        print(f"      ⚠️ AI parsing failed for: {title}")
                        stats["total_failed"] += 1
                        continue

                    # Create Campaign & Slug
                    campaign_slug = get_unique_slug(title, self.db, Campaign)
                    
                    # Convert dates safely
                    s_date = ai_data.get('start_date')
                    e_date = ai_data.get('end_date')
                    
                    try:
                        start_dt = datetime.strptime(s_date, "%Y-%m-%d").date() if s_date else None
                    except:
                        start_dt = None
                        
                    try:
                        end_dt = datetime.strptime(e_date, "%Y-%m-%d").date() if e_date else None
                    except:
                        end_dt = None

                    new_campaign = Campaign(
                        card_id=card.id,
                        slug=campaign_slug,
                        title=ai_data.get("title", title),
                        reward_text=ai_data.get("reward_text"),
                        reward_value=ai_data.get("reward_value"),
                        reward_type=ai_data.get("reward_type"),
                        description=ai_data.get("description"),
                        ai_marketing_text=ai_data.get("ai_marketing_text") or ai_data.get("description"),
                        conditions="\n".join(ai_data.get("conditions", [])),
                        image_url=img_url or ai_data.get("image_url"),
                        participation=ai_data.get("participation"),
                        eligible_cards=", ".join(ai_data.get("cards", [])),
                        start_date=start_dt,
                        end_date=end_dt,
                        tracking_url=detail_url,
                        is_active=True,
                        clean_text=ai_data.get("_clean_text"),
                        sector_id=self._get_sector_id(ai_data.get("sector")),
                        category=ai_data.get("sector", "diger")
                    )

                    self.db.add(new_campaign)
                    self.db.flush() # Get ID

                    # Brand Matching
                    brand_names = ai_data.get("brands", [])
                        
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

    def _get_sector_id(self, sector_slug: Optional[str]) -> Optional[int]:
        """Maps AI sector slug to DB sector ID."""
        if not sector_slug:
            return None
        sector = self.db.query(Sector).filter(Sector.slug == sector_slug).first()
        return sector.id if sector else None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit campaigns to process")
    args = parser.parse_args()
    
    scraper = OpetScraper()
    scraper.scrape(limit=args.limit)
