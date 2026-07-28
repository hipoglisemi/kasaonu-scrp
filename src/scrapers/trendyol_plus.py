import os
import time
import re
import json
import sys
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load env variables
load_dotenv(os.path.join(project_root, '.env'))

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

from src.database import get_db_session
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand
from src.services.ai_parser_golden import parse_api_campaign
from src.utils.logger_utils import log_scraper_execution
from src.utils.scraper_utils import upsert_campaign, is_url_blocked
from src.utils.slug_generator import get_unique_slug
from src.services.brand_matcher import get_or_create_brands_list

class TrendyolPlusScraper:
    BASE_URL = "https://ty-plus.trendyol.com/"
    BANK_NAME = "Trendyol Plus"
    BANK_SLUG = "trendyol-plus"
    CARD_NAME = "Trendyol Plus"
    CARD_SLUG = "trendyol-plus"
    DEFAULT_IMAGE_URL = "https://cdn.dsmcdn.com/benefits/trendyol-plus/80c1980c/t-logo.svg"

    def __init__(self):
        self.driver = None
        self.db = None
        self.bank_id = None
        self.card_id = None
        self.brand_cache = {}
        self.sector_cache = {}

    def setup_driver(self):
        """Initialize standard Selenium Chrome driver in headless mode."""
        print("   🔌 Initializing Headless Chrome Browser...")
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            print("   ✅ Browser launched successfully.")
        except Exception as e:
            print(f"   ❌ Failed to launch browser: {e}")
            raise e

    def close_driver(self):
        if self.driver:
            print("   🛑 Closing Browser...")
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def _get_or_create_bank(self) -> int:
        bank = self.db.query(Bank).filter(Bank.slug == self.BANK_SLUG).first()
        if not bank:
            print(f"⚠️ Bank '{self.BANK_NAME}' not found, creating...")
            bank = Bank(name=self.BANK_NAME, slug=self.BANK_SLUG, is_active=True)
            self.db.add(bank)
            self.db.commit()
            self.db.refresh(bank)
        return bank.id

    def _get_or_create_card(self) -> int:
        card = self.db.query(Card).filter(Card.slug == self.CARD_SLUG).first()
        if not card:
            print(f"⚠️ Card '{self.CARD_NAME}' not found, creating...")
            card = Card(
                name=self.CARD_NAME,
                slug=self.CARD_SLUG,
                bank_id=self.bank_id,
                is_active=True,
                card_type="loyalty"
            )
            self.db.add(card)
            self.db.commit()
            self.db.refresh(card)
        return card.id

    def _load_cache(self):
        # Load brand cache
        for b in self.db.query(Brand).all():
            self.brand_cache[b.name.lower()] = b
        # Load sector cache
        for s in self.db.query(Sector).all():
            self.sector_cache[s.slug] = s
            self.sector_cache[s.name.lower()] = s

    def run(self, limit: Optional[int] = None, force: bool = False):
        print(f"🚀 Starting {self.BANK_NAME} Scraper...")
        
        total_found = 0
        total_saved = 0
        total_revived = 0
        total_skipped = 0
        total_failed = 0
        error_details = []
        
        try:
            self.db = get_db_session()
            self._load_cache()
            
            # Setup Bank and Card
            self.bank_id = self._get_or_create_bank()
            self.card_id = self._get_or_create_card()
            
            self.setup_driver()
            driver = self.driver
            
            driver.get(self.BASE_URL)
            time.sleep(5)  # Wait for React app to render
            
            # Find candidate elements
            buttons = driver.find_elements(By.TAG_NAME, "button")
            candidate_buttons = []
            
            for btn in buttons:
                try:
                    txt = btn.text.strip()
                    if not txt:
                        continue
                    # Filter out helper buttons and accordion menus
                    if "Sıkça Sorulan Sorular" in txt or txt in ["Trendyol Plus'lı ol!", "Üye Ol", "Giriş Yap"]:
                        continue
                    if txt in ["Trendyol Plus", "Starbucks", "YouTube", "EXXEN", "Spotify", "Shell", "Tatilsepeti", "Garenta", "Uber Eats Trendyol Go market", "Uber Eats Trendyol Go yemek", "ENUYGUN.com"]:
                        continue
                    
                    klass = btn.get_attribute("class")
                    is_campaign_card = False
                    
                    # Bottom grid cards
                    if klass and "rounded-2xl" in klass and "bg-white" in klass and "cursor-pointer" in klass:
                        is_campaign_card = True
                    # Top section cards (Shell, Enuygun, Pass, etc.)
                    elif klass and "w-full" in klass and "bg-transparent" in klass and ("Detay" in txt or "Pass" in txt or "fiyatlar" in txt or "indirim" in txt):
                        is_campaign_card = True
                        
                    if is_campaign_card:
                        candidate_buttons.append((btn, txt))
                except:
                    pass
            
            total_found = len(candidate_buttons)
            print(f"✅ Found {total_found} candidate campaign cards on page.")
            
            if limit:
                candidate_buttons = candidate_buttons[:limit]
                print(f"   Applying limit: processing first {len(candidate_buttons)} campaigns.")
                
            for idx, (btn, btn_txt) in enumerate(candidate_buttons):
                preview_name = btn_txt.split('\n')[0][:50]
                tracking_url = f"{self.BASE_URL}#campaign-{idx}"
                print(f"[{idx+1}/{len(candidate_buttons)}] Processing: {preview_name}")
                
                try:
                    # 1. Check if blocked
                    if is_url_blocked(self.db, tracking_url):
                        print(f"   🚫 Skipped (Blocklisted): {tracking_url}")
                        total_skipped += 1
                        continue

                    # 2. Check if already exists in active campaigns
                    existing = self.db.query(Campaign).filter(
                        Campaign.tracking_url == tracking_url,
                        Campaign.card_id == self.card_id
                    ).first()
                    if not force and existing and existing.is_active and existing.is_approved:
                        print(f"   ⏭️ Skipped (Already exists and active): {existing.title}")
                        total_skipped += 1
                        continue
                    
                    # 3. Interactive Modal Click
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2)  # Wait for modal overlay
                    
                    modals = driver.find_elements(By.XPATH, "//div[@role='dialog']")
                    if not modals:
                        print("   ⚠️ Warning: Modal did not open or could not be found.")
                        total_failed += 1
                        error_details.append({"button_text": btn_txt, "error": "Modal did not open"})
                        continue
                        
                    modal = modals[0]
                    modal_text = modal.text
                    modal_html = modal.get_attribute("outerHTML")
                    
                    # Try to close modal immediately after reading content to prevent UI block
                    close_buttons = driver.find_elements(By.CLASS_NAME, "ant-modal-close")
                    if close_buttons:
                        close_buttons[0].click()
                    else:
                        webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(1)  # wait close transition
                    
                    # Extract image URL from modal if present
                    campaign_image_url = self.DEFAULT_IMAGE_URL
                    try:
                        modal_soup = BeautifulSoup(modal_html, "html.parser")
                        img_tag = modal_soup.find("img", alt="bottomsheet-image")
                        if not img_tag:
                            img_tag = modal_soup.find("img")
                        if img_tag and img_tag.get("src"):
                            campaign_image_url = img_tag["src"]
                            print(f"   🖼️ Extracted campaign image: {campaign_image_url}")
                    except Exception as img_err:
                        print(f"   ⚠️ Image extraction error: {img_err}")
                    
                    # 4. Parse Modal Content
                    lines = [line.strip() for line in modal_text.split("\n") if line.strip()]
                    title = btn_txt.replace("\n", " ")
                    if lines:
                        title_candidate = lines[0]
                        if 10 < len(title_candidate) < 150:
                            title = title_candidate

                    # Run through central AI Parser
                    ai_data = parse_api_campaign(
                        title=title,
                        short_description=None,
                        content_html=modal_html,
                        bank_name=self.BANK_NAME,
                        scraper_sector=None,
                        tracking_url=tracking_url,
                        og_title=title
                    )
                    
                    if not ai_data or ai_data.get("_ai_failed"):
                        print(f"   ⚠️ AI parsing failed for campaign: {title}")
                        total_failed += 1
                        error_details.append({"url": tracking_url, "error": "AI parsing failed"})
                        continue
                        
                    # 5. DB Save and upsert
                    status = self._save_campaign(title, campaign_image_url, tracking_url, ai_data, modal_text, force=force)
                    if status == "saved":
                        total_saved += 1
                    elif status == "revived":
                        total_revived += 1
                    elif status == "skipped":
                        total_skipped += 1
                    else:
                        total_failed += 1
                        
                except Exception as e:
                    print(f"   ❌ Error processing card: {e}")
                    total_failed += 1
                    error_details.append({"button_text": btn_txt, "error": str(e)})
                    # Make sure modal is dismissed on error
                    try:
                        webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                        time.sleep(1)
                    except: pass
            
            # Log scraper run results
            status_msg = "SUCCESS" if total_failed == 0 else ("PARTIAL" if total_saved > 0 or total_revived > 0 else "FAILED")
            log_scraper_execution(
                db=self.db,
                scraper_name="trendyol_plus",
                status=status_msg,
                total_found=total_found,
                total_saved=total_saved,
                total_skipped=total_skipped,
                total_failed=total_failed,
                total_revived=total_revived,
                error_details={"errors": error_details} if error_details else None
            )
            
        except Exception as e:
            print(f"❌ Fatal error in scraper run: {e}")
            if self.db:
                log_scraper_execution(
                    db=self.db,
                    scraper_name="trendyol_plus",
                    status="FAILED",
                    total_found=0,
                    total_saved=0,
                    total_skipped=0,
                    total_failed=1,
                    total_revived=0,
                    error_details={"error": str(e)}
                )
        finally:
            self.close_driver()
            if self.db:
                self.db.close()
                
    def _save_campaign(self, original_title: str, image_url: str, tracking_url: str, ai_data: Dict[str, Any], raw_text: str, force: bool = False) -> str:
        # Check if exists
        campaign = self.db.query(Campaign).filter(
            Campaign.tracking_url == tracking_url,
            Campaign.card_id == self.card_id
        ).first()
        
        is_new = False
        if not campaign:
            is_new = True
            final_title = ai_data.get("title") or original_title
            slug = get_unique_slug(
                title=final_title,
                db_session=self.db,
                campaign_model=Campaign,
                tracking_url=tracking_url,
                card_name=self.CARD_NAME,
                bank_name=self.BANK_NAME
            )
            campaign = Campaign(
                card_id=self.card_id,
                slug=slug,
                tracking_url=tracking_url,
                is_active=True,
                created_at=datetime.utcnow()
            )
        elif not force and campaign.is_active:
            return "skipped"

        # Update details
        campaign.title = ai_data.get("title") or original_title
        campaign.description = ai_data.get("description") or campaign.title
        campaign.ai_marketing_text = ai_data.get("ai_marketing_text")
        campaign.reward_text = ai_data.get("reward_text")
        campaign.reward_value = ai_data.get("reward_value")
        campaign.reward_type = ai_data.get("reward_type")
        
        # Parse Dates
        if ai_data.get("start_date"):
            try: campaign.start_date = datetime.strptime(ai_data["start_date"], "%Y-%m-%d").date()
            except: pass
        if not campaign.start_date:
            campaign.start_date = datetime.utcnow().date()
            
        if ai_data.get("end_date"):
            try: campaign.end_date = datetime.strptime(ai_data["end_date"], "%Y-%m-%d").date()
            except: pass

        # Conditions
        conditions_list = ai_data.get("conditions", [])
        if isinstance(conditions_list, str):
            conditions_list = [c.strip() for c in conditions_list.split("\n") if c.strip()]
        campaign.conditions = "\n".join(conditions_list)
        
        campaign.participation = ai_data.get("participation")
        campaign.category = ai_data.get("participation") # map category
        
        cards = ai_data.get("cards")
        if isinstance(cards, list):
            campaign.eligible_cards = ", ".join(cards)
        else:
            campaign.eligible_cards = str(cards) if cards else self.CARD_NAME

        # Sector
        sector_slug = ai_data.get("sector", "diger")
        sector = self.sector_cache.get(sector_slug.lower()) or self.sector_cache.get("diğer")
        if sector:
            campaign.sector_id = sector.id

        # Image mapping
        campaign.image_url = image_url
        campaign.clean_text = raw_text
        campaign.updated_at = datetime.utcnow()

        try:
            # central quality checker + state manager upsert
            campaign, op_status = upsert_campaign(self.db, campaign)
            self.db.commit()

            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
            elif op_status == "saved":
                print(f"   ✅ Saved: {campaign.title[:50]}...")
            
            self.db.refresh(campaign)

            # Resolve associated brands
            brand_ids = get_or_create_brands_list(
                db_session=self.db,
                brand_names=ai_data.get("brands", []),
                brand_cache=self.brand_cache,
                sector_id=sector.id if sector else None
            )
            for bid in brand_ids:
                try:
                    link = self.db.query(CampaignBrand).filter(
                        CampaignBrand.campaign_id == campaign.id,
                        CampaignBrand.brand_id == bid
                    ).first()
                    if not link:
                        self.db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                        self.db.commit()
                except Exception as e:
                    self.db.rollback()
                    print(f"   ⚠️ CampaignBrand link failed: {e}")
            return op_status
        except Exception as e:
            self.db.rollback()
            print(f"   ❌ Save Error: {e}")
            return "error"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of campaigns")
    parser.add_argument("--force", action="store_true", help="Force update existing records")
    args = parser.parse_args()
    
    scraper = TrendyolPlusScraper()
    scraper.run(limit=args.limit, force=args.force)
