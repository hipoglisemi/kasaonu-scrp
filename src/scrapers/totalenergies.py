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
from src.services.ai_parser_golden import parse_api_campaign  # type: ignore
from src.utils.logger_utils import log_scraper_execution # type: ignore
from src.utils.scraper_utils import upsert_campaign, is_url_blocked # type: ignore
from src.utils.slug_generator import get_unique_slug # type: ignore

load_dotenv()

class TotalEnergiesScraper:
    BASE_URL = "https://totalenergiesistasyonlari.com.tr"
    TARGET_URL = "https://totalenergiesistasyonlari.com.tr/kampanyalar/"
    SOURCE_NAME = "TotalEnergies"
    
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
        options.page_load_strategy = 'eager' # Faster loads
        
        if os.getenv("DOCKER_MODE") == "true" or os.environ.get("HEADLESS") == "1":
            options.add_argument('--headless=new')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-setuid-sandbox')
            options.add_argument('--disable-software-rasterizer')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--no-sandbox')

        time.sleep(2)
        self.driver = webdriver.Chrome(options=options)
        if self.driver:
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
            
        bank = db.query(Bank).filter(Bank.slug == "totalenergies").first()
        if not bank:
            bank = Bank(
                name="TotalEnergies",
                slug="totalenergies",
                logo_url="https://totalenergiesistasyonlari.com.tr/favicon.ico",
                is_active=True
            )
            db.add(bank)
            db.commit()
            db.refresh(bank)
        self.bank_cache = bank
        return bank

    def _get_or_create_card(self, db: Session, bank_id: int) -> Card:
        slug = "club-totalenergies" # Fixed to the master card slug
        if slug in self.card_cache:
            return self.card_cache[slug]
            
        card = db.query(Card).filter(Card.slug == slug).first()
        if not card:
            card = Card(
                bank_id=bank_id,
                name="Club TotalEnergies",
                slug=slug,
                card_type="FUEL",
                is_active=True
            )
            db.add(card)
            db.commit()
            db.refresh(card)
        self.card_cache[slug] = card
        return card

    def scrape(self, limit: Optional[int] = None):
        """Main scrape logic for TotalEnergies."""
        print(f"🚀 Starting {self.SOURCE_NAME} Scraper...")
        self.setup_driver()
        self.db = get_db_session()
        
        results: Dict[str, Any] = {"SAVED": 0, "SKIPPED": 0, "FAILED": 0, "REVIVED": 0, "LOGS": []}
        
        try:
            driver = self.driver
            if not driver:
                raise Exception("Failed to initialize driver")
            
            assert driver is not None
            driver.get(self.TARGET_URL)
            time.sleep(3)
            
            # Handle cookies if any
            try:
                cookie_btn = driver.find_element(By.CSS_SELECTOR, ".cookie-accept, #accept-cookies")
                cookie_btn.click()
                time.sleep(1)
            except:
                pass

            # Getting all campaign cards
            source = driver.page_source
            soup = BeautifulSoup(source, "html.parser")
            card_elements = soup.select(".showcase__card--container")
            
            if not card_elements:
                # Try fallback
                card_elements = soup.select("[class*='showcase__card']")
            
            print(f"   🎯 Found {len(card_elements)} total potential campaign cards.")

            processed_count = 0
            for card_soup in card_elements:
                if limit is not None and processed_count >= limit:
                    break
                
                try:
                    # Distinguish Active vs Expired
                    # 1. Check for 'play_gray.svg' in the detail button icon
                    # 2. Check for grayscale filter in style
                    # 3. Check for specific classes
                    
                    is_expired = False
                    
                    # 1. Check classes (some have 'True' or 'expired' or 'grayscale' related classes)
                    classes = card_soup.get("class", [])
                    if any(c in ["True", "expire", "expired", "grayscale"] for c in classes):
                        is_expired = True
                    
                    # 2. Check icons in detail button
                    detail_btn = card_soup.select_one(".showcase__card-detail--button")
                    if detail_btn:
                        icon_img = detail_btn.select_one("img")
                        if icon_img and "play_gray.svg" in icon_img.get("src", ""):
                            is_expired = True
                    
                    # 3. Check for specific grayscale style indicators
                    style = str(card_soup.get("style", "")).lower()
                    if "grayscale" in style or "filter: gray" in style:
                        is_expired = True
                    
                    if is_expired:
                        title_text = card_soup.select_one(".showcase__card-detail--slogan").text.strip() if card_soup.select_one(".showcase__card-detail--slogan") else "Unknown Title"
                        print(f"   📉 Deactivating/Skipping expired campaign: {title_text[:50]}...")
                        
                        # Set to inactive if exists in DB
                        try:
                            # Normalize URL as we do for skipping
                            check_url = detail_url
                            existing_campaign = self.db.query(Campaign).filter(Campaign.tracking_url == check_url).first()
                            if existing_campaign and existing_campaign.is_active:
                                existing_campaign.is_active = False
                                self.db.commit()
                                print(f"      ✅ Successfully marked as INACTIVE in DB.")
                        except Exception as e:
                            print(f"      ⚠️ Could not update status: {e}")
                            self.db.rollback()
                            
                        results["SKIPPED"] += 1
                        continue

                    title_tag = card_soup.select_one(".showcase__card-detail--slogan")
                    if not title_tag:
                        continue
                    
                    title = title_tag.text.strip()
                    
                    # Extract Image URL from Listing Page
                    image_tag = card_soup.select_one(".showcase__card--image img") or card_soup.select_one("img")
                    listing_image_url = None
                    if image_tag:
                        listing_image_url = urljoin(self.BASE_URL, image_tag.get("src", ""))

                    if not detail_btn:
                        continue
                        
                    onclick = detail_btn.get("onclick", "")
                    match = re.search(r"window\.location\.href='([^']+)'", onclick)
                    if not match:
                        continue
                        
                    relative_url = match.group(1)
                    detail_url = urljoin(self.BASE_URL, relative_url)
                    
                    # Normalize URL (remove -2, -3 etc. from the end of the slug)
                    # example: .../kampanya-adi-3/ -> .../kampanya-adi
                    detail_url = re.sub(r'-\d+/?$', '', detail_url)
                    # Strip any trailing slash to avoid duplicate saves due to exact matches
                    detail_url = detail_url.rstrip('/')
                    # Skip if already exists and active
                    if is_url_blocked(self.db, detail_url):
                        print(f"      🚫 Skipped (Blocklisted): {detail_url}")
                        results["SKIPPED"] += 1
                        continue

                    existing = self.db.query(Campaign).filter(Campaign.tracking_url == detail_url).first()
                    if existing and existing.is_active and existing.is_approved:
                        print(f"   ⏩ Skipping (Already exists and active): {title[:50]}...")
                        results["SKIPPED"] += 1
                        continue

                    print(f"   🔎 Processing: {title[:50]}...")
                    
                    # Navigate to detail page
                    driver.get(detail_url)
                    time.sleep(3)
                    
                    # Check for 404/expired page
                    if "404" in driver.title or "Sayfa Bulunamadı" in driver.page_source:
                        print(f"   ⏭️ Skipping (404/Not Found): {detail_url}")
                        results["SKIPPED"] += 1
                        continue
                    
                    # Scroll for AI parsing
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                    time.sleep(1)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                    
                    detail_soup = BeautifulSoup(driver.page_source, "html.parser")

                    # og:title for Header Sniper
                    og_title_el = detail_soup.find("meta", property="og:title")
                    og_title = og_title_el.get("content", "").strip() if og_title_el else title

                    # AI Parsing
                    campaign_data = parse_api_campaign(
                        title=title,
                        short_description=None,
                        content_html=str(detail_soup),
                        bank_name="Genel",
                        scraper_sector=None,
                        tracking_url=detail_url,
                        og_title=og_title
                    )
                    
                    if not campaign_data or campaign_data.get('_ai_failed'):
                        print(f"   ❌ AI extraction failed (or returned error) for: {title}")
                        results["FAILED"] += 1
                        continue

                    # Final Title check (AI might find a better one)
                    final_title = campaign_data.get('title', title)
                    
                    # Create campaign
                    bank = self._get_or_create_bank(self.db)
                    card = self._get_or_create_card(self.db, bank.id)
                    
                    # Get Sector
                    sector_slug = campaign_data.get('sector')
                    sector = self.db.query(Sector).filter(Sector.slug == sector_slug).first()
                    sector_id = sector.id if sector else None

                    # Convert dates safely
                    s_date = campaign_data.get('start_date')
                    e_date = campaign_data.get('end_date')
                    
                    try:
                        start_dt = datetime.strptime(s_date, "%Y-%m-%d").date() if s_date else None
                    except:
                        start_dt = None
                        
                    try:
                        end_dt = datetime.strptime(e_date, "%Y-%m-%d").date() if e_date else None
                    except:
                        end_dt = None

                    campaign = Campaign(
                        card_id=card.id,
                        sector_id=sector_id,
                        title=final_title,
                        reward_text=campaign_data.get('reward_text'),
                        reward_value=campaign_data.get('reward_value'),
                        reward_type=campaign_data.get('reward_type'),
                        description=campaign_data.get('description', ''),
                        ai_marketing_text=campaign_data.get('ai_marketing_text') or campaign_data.get('description'),
                        conditions="\n".join(campaign_data.get('conditions', [])),
                        participation=campaign_data.get('participation'),
                        eligible_cards=", ".join(campaign_data.get('cards', [])),
                        category=campaign_data.get('sector', 'diger'),
                        image_url=listing_image_url or campaign_data.get('image_url'),
                        tracking_url=detail_url,
                        start_date=start_dt,
                        end_date=end_dt,
                        is_active=True,
                        slug=get_unique_slug(final_title, self.db, Campaign)
                    )
                    
                    # Use centralized upsert_campaign for revival and quality control
                    campaign, op_status = upsert_campaign(self.db, campaign)
                    self.db.commit()

                    if op_status == "revived":
                        print(f"      ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
                        results["REVIVED"] += 1
                    elif op_status == "saved":
                         print(f"      ✅ Saved: {campaign.title[:50]}...")
                         results["SAVED"] += 1
                    
                    self.db.refresh(campaign)
                    
                    # Matching Brands
                    brand_names = campaign_data.get('brands', [])
                        
                    brands_ids = get_or_create_brands_list(
                        db=self.db,
                        names=brand_names,
                        brand_cache=self.brand_cache
                    )
                    for b_id in brands_ids:
                        cb = CampaignBrand(campaign_id=campaign.id, brand_id=b_id)
                        self.db.add(cb)
                    
                    self.db.commit()
                    processed_count += 1
                    print(f"   ✅ Saved: {final_title}")
                    
                except Exception as e:
                    print(f"   ❌ Error processing card: {str(e)}")
                    results["FAILED"] += 1
                    if self.db:
                        self.db.rollback()

        except Exception as e:
            print(f"   ❌ Scraper Crashed: {str(e)}")
            if isinstance(results["LOGS"], list):
                results["LOGS"].append(str(e))
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            if self.db:
                try:
                    self.db.close()
                except:
                    pass
                
        print(f"🏁 Finished {self.SOURCE_NAME}. Saved: {results['SAVED']}, Skipped: {results['SKIPPED']}, Failed: {results['FAILED']}")
        log_scraper_execution(
            db=self.db,
            scraper_name=self.SOURCE_NAME,
            status="SUCCESS" if results["FAILED"] == 0 else "PARTIAL",
            total_found=results["SAVED"] + results["SKIPPED"] + results["FAILED"],
            total_revived=results["REVIVED"],
            error_details={"logs": results["LOGS"]} if results["LOGS"] else None
        )
        return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of campaigns")
    args = parser.parse_args()
    
    scraper = TotalEnergiesScraper()
    scraper.scrape(limit=args.limit)
