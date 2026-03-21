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

class ShellScraper:
    BASE_URL = "https://www.shell.com.tr"
    TARGET_URL = "https://www.shell.com.tr/suruculer/shellden-avantajli-kampanyalar.html"
    SOURCE_NAME = "Shell"
    
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
            
        bank = db.query(Bank).filter(Bank.slug == "shell").first()
        if not bank:
            bank = Bank(
                name="Shell",
                slug="shell",
                logo_url="https://www.shell.com.tr/favicon.ico",
                is_active=True
            )
            db.add(bank)
            db.commit()
            db.refresh(bank)
        self.bank_cache = bank
        return bank

    def _get_or_create_card(self, db: Session, bank_id: int) -> Card:
        slug = "shell-clubsmart"
        if slug in self.card_cache:
            return self.card_cache[slug]
            
        card = db.query(Card).filter(Card.slug == slug).first()
        if not card:
            card = Card(
                bank_id=bank_id,
                name="Shell ClubSmart",
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
            time.sleep(3)

            # Accept cookies
            try:
                cookie_btn = self.driver.find_element(By.CSS_SELECTOR, ".cookie-accept-all, #accept-all-cookies")
                cookie_btn.click()
                time.sleep(1)
            except:
                pass

            # Collect cards - Shell uses .pal-brand1-subtle for current campaigns
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            cards = soup.select("a.pal-brand1-subtle")
            print(f"   🎯 Found {len(cards)} current campaign cards.")

            bank = self._get_or_create_bank(self.db)
            card = self._get_or_create_card(self.db, bank.id)

            processed_count = 0
            for card_soup in cards:
                if processed_count >= limit:
                    break

                try:
                    # Link
                    relative_url = card_soup.get("href")
                    if not relative_url:
                        continue
                    
                    detail_url = urljoin(self.BASE_URL, relative_url)
                    
                    # Title
                    title_tag = card_soup.select_one("h3 p, h3 span, h3")
                    title = title_tag.get_text(strip=True) if title_tag else "Shell Kampanyası"
                    
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
                    
                    # Try to get high-res image from detail page
                    # Selector found via research: .page-header img, but also common AEM structures
                    detail_img_tag = detail_soup.select_one(".page-header img, .page-header__image img, .hero-image img, .main-image img, .cmp-image__image")
                    
                    # If not found yet, try searching for any image that looks like a hero (large or in main)
                    if not detail_img_tag:
                        detail_img_tag = detail_soup.select_one("main img")
                        
                    if detail_img_tag:
                        detail_img_url = detail_img_tag.get("src") or detail_img_tag.get("data-src") or detail_img_tag.get("srcset")
                        if detail_img_url:
                            # If it's a srcset, take the last one (usually highest res)
                            if "," in detail_img_url:
                                detail_img_url = detail_img_url.split(",")[-1].strip().split(" ")[0]
                                
                            # Normalize URL
                            full_detail_img_url = urljoin(self.BASE_URL, detail_img_url)
                            
                            # If it's a Shell CDN URL, ensure high resolution
                            # Patterns: imwidth=..., .img.960. ..., .shellimg.960. ...
                            if "imwidth" in full_detail_img_url:
                                full_detail_img_url = re.sub(r"imwidth=\d+", "imwidth=1200", full_detail_img_url)
                                full_detail_img_url = re.sub(r"imdensity=\d+", "imdensity=1", full_detail_img_url) # Reset density as imwidth 1200 is absolute enough
                            
                            if ".img." in full_detail_img_url:
                                full_detail_img_url = re.sub(r"\.img\.\d+\.", ".img.1200.", full_detail_img_url)
                            
                            if ".shellimg." in full_detail_img_url:
                                full_detail_img_url = re.sub(r"\.shellimg\.\D*\d+\.", ".shellimg.1200.", full_detail_img_url)
                            
                            img_url = full_detail_img_url
                            print(f"      🖼️ Found high-res image: {img_url[:60]}...")

                    content_area = detail_soup.select_one("main, .main-content, .campaign-detail-content")
                    raw_html = str(content_area) if content_area else self.driver.page_source

                    # AI Parsing
                    ai_data = self.parser.parse_campaign_data(
                        raw_text=raw_html,
                        title=title,
                        bank_name="Shell",
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
                        ai_marketing_text=ai_data.get("description"),
                        conditions="\n".join(ai_data.get("conditions", [])),
                        image_url=img_url or ai_data.get("image_url"),
                        participation=ai_data.get("participation"),
                        eligible_cards=", ".join(ai_data.get("cards", [])),
                        start_date=start_dt,
                        end_date=end_dt,
                        tracking_url=detail_url,
                        is_active=True,
                        clean_text=ai_data.get("_clean_text"),
                        sector_id=self._get_sector_id(ai_data.get("sector", "akaryakit")),
                        category=ai_data.get("sector", "akaryakit")
                    )

                    self.db.add(new_campaign)
                    self.db.flush()

                    # Brand Matching
                    brand_names = ai_data.get("brands", [])
                    if "Shell" not in brand_names:
                        brand_names.append("Shell")
                        
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
        sector = self.db.query(Sector).filter(Sector.slug == sector_slug).first()
        if not sector:
            sector = self.db.query(Sector).filter(Sector.slug == "akaryakit").first()
        return sector.id if sector else None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit campaigns to process")
    args = parser.parse_args()
    
    scraper = ShellScraper()
    scraper.scrape(limit=args.limit)
