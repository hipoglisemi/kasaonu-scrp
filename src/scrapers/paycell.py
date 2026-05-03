import os
import sys
import json
import re
import time
import random
import traceback
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any, cast
from urllib.parse import urljoin
from bs4 import BeautifulSoup # type: ignore

from selenium import webdriver # type: ignore
from selenium.webdriver.chrome.service import Service # type: ignore
from webdriver_manager.chrome import ChromeDriverManager # type: ignore
from selenium.webdriver.chrome.options import Options # type: ignore
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore
from selenium_stealth import stealth # type: ignore

# Ensure src in path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from dotenv import load_dotenv # type: ignore
    load_dotenv(os.path.join(project_root, '.env'), override=True)
except Exception:
    pass

try:
    from src.models import Campaign, Bank, Card, Sector, Brand, CampaignBrand # type: ignore
    from src.database import get_db_session # type: ignore
    from src.services.ai_parser import AIParser # type: ignore
    from src.services.ai_parser_golden import parse_api_campaign  # type: ignore
    from src.utils.slug_generator import get_unique_slug # type: ignore
    from src.utils.scraper_utils import upsert_campaign, is_url_blocked # type: ignore
    from src.utils.logger_utils import log_scraper_execution # type: ignore
except ImportError:
    pass

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
            campaign_list = self._collect_campaign_links(limit=limit)
            print(f"✅ Found {len(campaign_list)} unique candidate campaigns.")
            
            if limit:
                limit_val = limit
                campaign_list = [campaign_list[i] for i in range(min(len(campaign_list), limit_val))]

            total_found = len(campaign_list)
            total_saved = 0
            total_revived = 0
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
                        if is_url_blocked(db, url):
                            print(f"   🚫 Skipped (Blocklisted): {url}")
                            total_skipped += 1
                            continue
                        
                        existing = db.query(Campaign).filter(Campaign.tracking_url == url).first()
                        if not force and existing and existing.is_active:
                             print(f"   ⏭️  Skipped (Already exists and active)")
                             total_skipped += 1
                             continue

                    # 2. Fetch Detail
                    dr = cast(Any, self.driver)
                    if dr:
                        dr.get(url)
                        time.sleep(5)
                        # Aggressive Scroll for hydration
                        dr.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
                        time.sleep(1)
                        dr.execute_script("window.scrollTo(0, document.body.scrollHeight/1.5);")
                        time.sleep(1)
                        dr.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)
                    else:
                        print("   ❌ self.driver is None")
                        continue

                    dr = cast(Any, self.driver)
                    if not dr:
                        print("   ❌ self.driver is None")
                        continue
                    soup = BeautifulSoup(dr.page_source, "html.parser")

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

                    # og:title for Header Sniper
                    og_title_el = soup.find("meta", property="og:title")
                    og_title = og_title_el.get("content", "").strip() if og_title_el else title

                    # Full body HTML → parse_api_campaign centralised pipeline
                    body_el = soup.find("body")
                    raw_html = str(body_el) if body_el else dr.page_source

                    # 4. AI Parse
                    ai_data = parse_api_campaign(
                        title=title,
                        short_description=None,
                        content_html=raw_html,
                        bank_name=self.BANK_NAME,
                        scraper_sector=None,
                        tracking_url=url,
                        og_title=og_title
                    )

                    if not ai_data:
                        print(f"   ⚠️  AI parsing failed for {url}")
                        total_failed += 1
                        continue

                    # 5. Save
                    status = self._save_campaign(title, str(image_url) if image_url else self.DEFAULT_IMAGE_URL, url, ai_data, raw_html, force=force)
                    if status == "saved":
                        total_saved += 1
                    elif status == "revived":
                        total_revived += 1
                    elif status == "skipped":
                        total_skipped += 1
                    else:
                        total_failed += 1

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
                    total_revived=total_revived,
                    error_details={"errors": error_details} if error_details else None
                ) # type: ignore

        finally:
            dr = cast(Any, self.driver)
            if dr:
                dr.quit()

    def _collect_campaign_links(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        campaign_data = {}
        page = 1
        
        dr = cast(Any, self.driver)
        if not dr:
            print("   ❌ self.driver is None in _collect_campaign_links")
            return []

        print(f"   📄 Accessing initial page: {self.LIST_PAGE_URL}")
        dr.get(self.LIST_PAGE_URL)
        time.sleep(8)  # Wait for initial Next.js hydration
        
        while True:
            print(f"   📄 Scraping Page {page}...")
            
            # Aggressive scroll to trigger lazy images
            dr.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(1)
            dr.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            soup = BeautifulSoup(dr.page_source, "html.parser")
            
            # Find campaign cards
            found_on_page = 0
            cards = soup.select("#blogs .card") or soup.select(".card")
            
            if not cards:
                print("      ⚠️ No cards found on this page.")
            else:
                for card in cards:
                    link_el = card.find("a", href=True)
                    if not link_el: continue
                    
                    href = link_el["href"]
                    if "/kampanyalar/" in href and href.strip("/") != "kampanyalar":
                        full_url = urljoin(self.BASE_URL, href)
                        
                        img_el = card.select_one(".card-img-top") or card.find("img")
                        img_url = None
                        if img_el:
                            img_src = cast(str, img_el.get("src") or img_el.get("data-src") or img_el.get("srcset"))
                            if img_src:
                                if "," in img_src:
                                    img_src = img_src.split(",")[0].split(" ")[0]
                                img_url = urljoin(self.BASE_URL, img_src)
                                
                        if full_url not in campaign_data:
                            campaign_data[full_url] = img_url
                            total_on_page_for_ide = found_on_page + 1
                        found_on_page = total_on_page_for_ide # type: ignore
                            
                    limit_int = limit
                    if limit_int and len(campaign_data) >= limit_int:
                        print(f"      🛑 Limit of {limit_int} campaigns reached. Stopping link collection.")
                        return [{"url": url, "image_url": str(img) if img else self.DEFAULT_IMAGE_URL} for url, img in campaign_data.items()]
            
            print(f"      🔎 Found {found_on_page} new campaigns on page {page}.")
            
            # Check for Next Button
            try:
                # Based on observation, next button has class .page-link.next
                next_btn_selector = ".pagination-container .page-link.next"
                dr = cast(Any, self.driver)
                next_btn = dr.find_elements(By.CSS_SELECTOR, next_btn_selector) if dr else []
                
                if next_btn and next_btn[0].is_displayed():
                    print(f"      ➡️ Clicking Next Page button...")
                    # Scroll to button to ensure visibility
                    if dr:
                        dr.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn[0])
                        time.sleep(1)
                    next_btn[0].click()
                    
                    p_val = cast(int, page)
                    page = p_val + 1 # type: ignore
                    time.sleep(5)  # Wait for AJAX/SPA transition
                    
                    # Verify we didn't just click the same page again (redundant but safe)
                    continue
                else:
                    print("      🏁 No 'Next' button found or it's hidden. End of list.")
                    break
            except Exception as e:
                print(f"      ⚠️ Pagination error: {e}. Stopping.")
                break
                
        return [{"url": url, "image_url": str(img) if img else self.DEFAULT_IMAGE_URL} for url, img in campaign_data.items()]

    def _save_campaign(self, original_title: str, image_url: str, tracking_url: str, ai_data: Dict[str, Any], raw_text: str, force: bool = False) -> str:
        with get_db_session() as db:
            campaign = db.query(Campaign).filter(
                Campaign.tracking_url == tracking_url,
                Campaign.card_id == self.card_id
            ).first()
            
            if not campaign:
                final_title = ai_data.get("title") or original_title
                slug = get_unique_slug(final_title, db, Campaign)
                campaign = Campaign(
                    card_id=self.card_id,
                    slug=slug,
                    tracking_url=tracking_url,
                    is_active=True,
                    created_at=datetime.utcnow()
                )

            campaign.title = ai_data.get("title") or original_title
            campaign.description = ai_data.get("description") or campaign.title
            campaign.ai_marketing_text = ai_data.get("ai_marketing_text") or campaign.description
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
            
            # Use centralized upsert_campaign for revival and quality control
            campaign, op_status = upsert_campaign(db, campaign)
            db.commit()
            
            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title[:50]}...")
            
            db.refresh(campaign)

            # Handle Brands
            from src.services.brand_matcher import get_or_create_brands_list
            brand_ids = get_or_create_brands_list(
                db_session=db,
                brand_names=ai_data.get("brands", []),
                brand_cache=getattr(self, 'brand_cache', {}),
                sector_id=campaign.sector_id
            )

            try:
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

                return op_status
            except Exception as e:
                db.rollback()
                print(f"   ❌ Brand linking failed: {e}")
                return "error"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of campaigns")
    parser.add_argument("--force", action="store_true", help="Force update")
    args = parser.parse_args()
    
    scraper = PaycellScraper()
    scraper.run(limit=args.limit, force=args.force)
