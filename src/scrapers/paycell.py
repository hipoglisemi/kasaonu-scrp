import os
import sys
import json
import re
import time
import random
import traceback
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium_stealth import stealth

# Ensure src in path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_root, '.env'), override=True)
except Exception:
    pass

from src.models import Campaign, Bank, Card, Sector, Brand, CampaignBrand
from src.database import get_db_session
from src.services.ai_parser import AIParser
from src.utils.slug_generator import get_unique_slug
from src.utils.scraper_utils import should_skip_campaign, is_url_blocked
from src.utils.logger_utils import log_scraper_execution

class PaycellScraper:
    BASE_URL = "https://paycell.com.tr"
    LIST_PAGE_URL = "https://paycell.com.tr/kampanyalar"
    BANK_NAME = "Paycell"
    BANK_SLUG = "paycell"
    CARD_NAME = "Paycell Kart"
    CARD_SLUG = "paycell-kart"
    DEFAULT_IMAGE_URL = "https://paycell.com.tr/images/logo/paycell_logo_2-1-03.png"

    def __init__(self):
        self.parser = AIParser()
        self.bank_id = self._get_or_create_bank()
        self.card_id = self._get_or_create_card()
        self.driver = None

    def _get_or_create_bank(self) -> int:
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == self.BANK_SLUG).first()
            if not bank:
                bank = db.query(Bank).filter(Bank.name.ilike(f"%{self.BANK_NAME}%")).first()
            
            if not bank:
                print(f"⚠️  Bank '{self.BANK_NAME}' not found, creating...")
                bank = Bank(name=self.BANK_NAME, slug=self.BANK_SLUG, is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
            return bank.id

    def _get_or_create_card(self) -> int:
        with get_db_session() as db:
            card = db.query(Card).filter(Card.slug == self.CARD_SLUG).first()
            if not card:
                card = db.query(Card).filter(
                    Card.name.ilike(f"%{self.CARD_NAME}%"),
                    Card.bank_id == self.bank_id
                ).first()
            
            if not card:
                print(f"⚠️  Card '{self.CARD_NAME}' not found, creating...")
                card = Card(
                    name=self.CARD_NAME, 
                    slug=self.CARD_SLUG, 
                    bank_id=self.bank_id, 
                    is_active=True,
                    card_type="prepaid"
                )
                db.add(card)
                db.commit()
                db.refresh(card)
            return card.id

    def setup_driver(self):
        options = Options()
        if os.environ.get("HEADLESS") != "0":
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        stealth(self.driver,
            languages=["tr-TR", "tr"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )

    def run(self, limit: Optional[int] = None, force: bool = False):
        print(f"🚀 Starting {self.BANK_NAME} Scraper...")
        self.setup_driver()
        
        try:
            campaign_list = self._collect_campaign_links()
            print(f"✅ Found {len(campaign_list)} unique candidate campaigns.")
            
            if limit:
                campaign_list = campaign_list[:limit]

            total_found = len(campaign_list)
            total_saved = 0
            total_skipped = 0
            total_failed = 0
            error_details = []

            for i, item in enumerate(campaign_list):
                url = item["url"]
                list_image_url = item["image_url"]
                print(f"[{i+1}/{total_found}] Processing: {url}")
                
                try:
                    # 1. Check if already exists or blocked
                    with get_db_session() as db:
                        if not force and should_skip_campaign(db, url, card_id=self.card_id):
                            print(f"   ⏭️  Skipped (Already exists or blocked)")
                            total_skipped += 1
                            continue
                        if is_url_blocked(db, url):
                            print(f"   🚫 Skipped (Blocklisted)")
                            total_skipped += 1
                            continue

                    # 2. Fetch Detail
                    self.driver.get(url)
                    time.sleep(5)
                    
                    # Aggressive Scroll for hydration
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
                    time.sleep(1)
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/1.5);")
                    time.sleep(1)
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)

                    soup = BeautifulSoup(self.driver.page_source, "html.parser")

                    # 3. Extract Data
                    title_el = soup.find("h1") or soup.find("h2", class_="blog-outer-head")
                    title = title_el.get_text(strip=True) if title_el else ""
                    
                    # Detail Image Extraction
                    image_url = None
                    # Try to find specific detail banner
                    detail_img = soup.select_one(".page-detail-banner img") or \
                                 soup.select_one(".blog img:not([src*='icon'])") or \
                                 soup.select_one(".pay-container img:not([src*='icon'])") or \
                                 soup.select_one("main img.img-fluid:not(.expired-campaign)")
                    
                    if detail_img:
                        src = detail_img.get("src") or detail_img.get("data-src")
                        if src:
                            image_url = urljoin(self.BASE_URL, src)
                    
                    # Fallback Logic: Use list_image_url if detail image is missing or generic
                    if not image_url or "logo" in image_url.lower() or "paycell_logo" in image_url:
                        if list_image_url:
                            print(f"   ℹ️  Detail image missing or generic, falling back to list image: {list_image_url}")
                            image_url = list_image_url
                        else:
                            image_url = self.DEFAULT_IMAGE_URL

                    # Body content
                    # Based on research, Next.js might use 'main' or specific card-body
                    content_part = soup.select_one("main") or soup.select_one(".card-body")
                    if not content_part:
                        content_part = soup.body
                    
                    raw_text = content_part.get_text(separator="\n", strip=True) if content_part else ""

                    # 4. AI Parse
                    ai_data = self.parser.parse_campaign_data(
                        raw_text=raw_text,
                        bank_name=self.BANK_NAME,
                        title=title
                    )

                    if not ai_data:
                        print(f"   ⚠️  AI parsing failed for {url}")
                        total_failed += 1
                        continue

                    # 5. Save
                    status = self._save_campaign(title, image_url, url, ai_data, raw_text, force=force)
                    if status == "saved":
                        total_saved += 1
                    elif status == "skipped":
                        total_skipped += 1
                    else: total_failed += 1

                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    total_failed += 1
                    error_details.append({"url": url, "error": str(e)})

                time.sleep(random.uniform(1, 3))

            # Log execution
            status_msg = "SUCCESS" if total_failed == 0 else ("PARTIAL" if total_saved > 0 else "FAILED")
            with get_db_session() as db:
                log_scraper_execution(
                    db=db,
                    scraper_name="paycell",
                    status=status_msg,
                    total_found=total_found,
                    total_saved=total_saved,
                    total_skipped=total_skipped,
                    total_failed=total_failed,
                    error_details={"errors": error_details} if error_details else None
                )

        finally:
            if self.driver:
                self.driver.quit()

    def _collect_campaign_links(self) -> List[Dict[str, str]]:
        campaign_data = {}
        page = 1
        
        while True:
            url = f"{self.LIST_PAGE_URL}?paged={page}"
            print(f"   📄 Scraping Page {page}: {url}")
            self.driver.get(url)
            time.sleep(8) # Wait for Next.js hydration
            
            # Simple scroll to trigger lazy images
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            
            # Find campaign cards
            # Pattern: <a href="/kampanyalar/slug"> with <img class="card-img-top">
            found_on_page = 0
            cards = soup.select("#blogs .card") or soup.select(".card")
            
            if not cards:
                print("      ⚠️ No cards found on this page. Stopping pagination.")
                break
                
            for card in cards:
                link_el = card.find("a", href=True)
                if not link_el: continue
                
                href = link_el["href"]
                if "/kampanyalar/" in href and href.strip("/") != "kampanyalar":
                    full_url = urljoin(self.BASE_URL, href)
                    
                    img_el = card.select_one(".card-img-top") or card.find("img")
                    img_url = None
                    if img_el:
                        # Check multiple attributes for the image URL
                        img_src = img_el.get("src") or img_el.get("data-src") or img_el.get("srcset")
                        if img_src:
                            # If it's a srcset, take the first/largest URL
                            if "," in img_src:
                                img_src = img_src.split(",")[0].split(" ")[0]
                            img_url = urljoin(self.BASE_URL, img_src)
                            
                    if full_url not in campaign_data:
                        campaign_data[full_url] = img_url
                        found_on_page += 1
            
            print(f"      🔎 Found {found_on_page} new campaigns on page {page}.")
            
            # Check for next page button or if no new campaigns found
            next_btn = soup.select_one(".swiper-button-next:not(.swiper-button-disabled)")
            # Or check if pagination numbers exist and we haven't reached the end
            # Based on user screen, it has numbers [1, 2, 3... 7]
            pagination_active = soup.select(".pagination") or soup.select(".swiper-pagination") or soup.select_one(".swiper-button-next")
            
            if found_on_page == 0 or page >= 10: # Safety break
                break
                
            page += 1
            time.sleep(2)
            
        return [{"url": url, "image_url": img} for url, img in campaign_data.items()]

    def _save_campaign(self, original_title: str, image_url: str, tracking_url: str, ai_data: Dict[str, Any], raw_text: str, force: bool = False) -> str:
        with get_db_session() as db:
            campaign = db.query(Campaign).filter(
                Campaign.tracking_url == tracking_url,
                Campaign.card_id == self.card_id
            ).first()
            
            is_new = False
            if not campaign:
                is_new = True
                final_title = ai_data.get("title") or original_title
                slug = get_unique_slug(final_title, db, Campaign)
                campaign = Campaign(
                    card_id=self.card_id,
                    slug=slug,
                    tracking_url=tracking_url,
                    is_active=True,
                    created_at=datetime.utcnow()
                )
                db.add(campaign)
            elif not force:
                return "skipped"

            campaign.title = ai_data.get("title") or original_title
            campaign.description = ai_data.get("description") or campaign.title
            campaign.reward_text = ai_data.get("reward_text")
            campaign.reward_value = ai_data.get("reward_value")
            campaign.reward_type = ai_data.get("reward_type")
            
            if ai_data.get("start_date"):
                try: campaign.start_date = datetime.strptime(ai_data["start_date"], "%Y-%m-%d")
                except: pass
            if not campaign.start_date: campaign.start_date = datetime.utcnow()
                
            if ai_data.get("end_date"):
                try: campaign.end_date = datetime.strptime(ai_data["end_date"], "%Y-%m-%d")
                except: pass

            campaign.conditions = "\n".join(ai_data.get("conditions", []))
            campaign.participation = ai_data.get("participation")
            campaign.eligible_cards = ", ".join(ai_data.get("cards", [])) if isinstance(ai_data.get("cards"), list) else self.CARD_NAME

            sector_slug = ai_data.get("sector", "diger")
            sector = db.query(Sector).filter(Sector.slug == sector_slug).first()
            if sector: campaign.sector_id = sector.id

            if image_url and (not campaign.image_url or "logo" in campaign.image_url.lower() or force):
                campaign.image_url = image_url
            
            campaign.clean_text = raw_text
            campaign.updated_at = datetime.utcnow()

            # Handle Brands
            brand_ids = self._get_or_create_brands(db, ai_data.get("brands", []), campaign.sector_id)

            try:
                db.commit()
                db.refresh(campaign)

                # Link Brands
                processed_brands = []
                for b_id in brand_ids:
                    existing_link = db.query(CampaignBrand).filter_by(campaign_id=campaign.id, brand_id=b_id).first()
                    if not existing_link:
                        cb = CampaignBrand(campaign_id=campaign.id, brand_id=b_id)
                        db.add(cb)
                        processed_brands.append(str(b_id))
                
                if processed_brands:
                    db.commit()

                print(f"   ✅ {'Saved' if is_new else 'Updated'}: {campaign.title[:50]} (Brands: {len(brand_ids)})")
                return "saved"
            except Exception as e:
                db.rollback()
                print(f"   ❌ Save Error: {e}")
                return "error"

    def _get_or_create_brands(self, db, names: List[str], sector_id: Optional[int]) -> List[Any]:
        import uuid
        ids = []
        if not names: return ids

        for n in names:
            key = n.strip()
            if not key or key.lower() == self.BANK_NAME.lower(): continue
            
            slug_val = re.sub(r'[^a-z0-9-]', '-', key.lower()).strip('-')
            brand = db.query(Brand).filter(Brand.slug == slug_val).first()
            
            if not brand:
                brand = Brand(
                    id=uuid.uuid4(),
                    name=key,
                    slug=slug_val,
                    is_active=True
                )
                db.add(brand)
                db.flush()
            ids.append(brand.id)
        return ids

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of campaigns")
    parser.add_argument("--force", action="store_true", help="Force update")
    args = parser.parse_args()
    
    scraper = PaycellScraper()
    scraper.run(limit=args.limit, force=args.force)
