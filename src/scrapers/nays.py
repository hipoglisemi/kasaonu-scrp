import os
import sys
import json
import re
import time
import requests
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load Env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_root, '.env'))
except Exception:
    pass

from src.models import Campaign, Bank, Card, Sector, Brand, CampaignBrand
from src.database import get_db_session
from src.services.ai_parser import AIParser
from src.utils.slug_generator import get_unique_slug
from src.utils.scraper_utils import should_skip_campaign, is_url_blocked
from src.utils.logger_utils import log_scraper_execution

class NaysScraper:
    BASE_URL = "https://www.naysapp.com.tr"
    LIST_PAGE_URL = "https://www.naysapp.com.tr/firsatlar"
    BANK_NAME = "Nays"
    BANK_SLUG = "nays"
    CARD_NAME = "Nays Kart"
    CARD_SLUG = "nays-kart"
    DEFAULT_IMAGE_URL = "https://www.naysapp.com.tr/assets/images/nays-logo.png"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        self.parser = AIParser()
        self.bank_id = self._get_or_create_bank()
        self.card_id = self._get_or_create_card()

    def _get_or_create_bank(self) -> int:
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == self.BANK_SLUG).first()
            if not bank:
                # Try to find by name if slug fails
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

    def run(self, limit: Optional[int] = None, force: bool = False):
        print(f"🚀 Starting {self.BANK_NAME} Scraper...")
        
        try:
            response = self.session.get(self.LIST_PAGE_URL, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            print(f"❌ Error fetching list page: {e}")
            return

        # Fetch campaign links and images
        campaign_data = {}
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "/firsatlar/" in href and href.strip("/") != "firsatlar":
                full_url = urljoin(self.BASE_URL, href)
                
                # Check for image in the figure tag within the anchor
                img_url = None
                figure = a_tag.find("figure")
                if figure:
                    img_tag = figure.find("img")
                    if img_tag:
                        img_src = img_tag.get("src")
                        if img_src:
                            img_url = urljoin(self.BASE_URL, img_src)
                
                # Avoid anchor links and social links
                if "#" not in full_url and "facebook" not in full_url and "twitter" not in full_url:
                    # Prioritize the one with an image if we find the same URL multiple times
                    if full_url not in campaign_data or (img_url and not campaign_data[full_url]):
                        campaign_data[full_url] = img_url

        campaign_list = [{"url": url, "image_url": img} for url, img in campaign_data.items()]
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
                detail_resp = self.session.get(url, timeout=30)
                detail_resp.raise_for_status()
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

                # 3. Extract Data
                # Title typically in h1
                title_el = detail_soup.find("h1")
                title = title_el.get_text(strip=True) if title_el else ""
                
                # Image Ranking:
                # 1. JSON-LD Structured Data (Most Reliable Banner Source)
                # 2. List Page Banner
                # 3. Detail Page specific Campaign Image (Pattern: /medium/Campaign/Image/)
                # 4. Detail Page Article Image
                # 5. OG Image (Likely logo)
                image_url = list_image_url
                
                # Try to extract from JSON-LD
                try:
                    ld_json_scripts = detail_soup.find_all("script", type="application/ld+json")
                    for script in ld_json_scripts:
                        try:
                            data = json.loads(script.string)
                            # Structured data might be a list or a single object
                            if isinstance(data, list):
                                for item in data:
                                    if "image" in item:
                                        image_url = urljoin(self.BASE_URL, item["image"])
                                        break
                            elif isinstance(data, dict):
                                if "image" in data:
                                    image_url = urljoin(self.BASE_URL, data["image"])
                            if image_url and "/medium/Campaign/" in image_url:
                                break
                        except: continue
                except Exception as e:
                    print(f"   ⚠️ JSON-LD error: {e}")

                if not image_url or "logo.png" in image_url:
                    # Search for campaign-specific image on detail page
                    campaign_img = detail_soup.find("img", src=re.compile(r"/medium/Campaign/Image/"))
                    if campaign_img:
                        image_url = urljoin(self.BASE_URL, campaign_img.get("src"))
                
                if not image_url or "logo.png" in image_url:
                    img_el = detail_soup.select_one(".page-detail-banner img") or detail_soup.select_one("article img")
                    if img_el:
                        src = img_el.get("src")
                        if src:
                            image_url = urljoin(self.BASE_URL, src)
                
                if not image_url or "logo.png" in image_url:
                    og_image = detail_soup.find("meta", property="og:image")
                    if og_image:
                        image_url = urljoin(self.BASE_URL, og_image["content"])
                
                if not image_url or "logo.png" in image_url:
                    image_url = self.DEFAULT_IMAGE_URL

                # Body content for AI
                content_part = detail_soup.select_one(".page-detail-content") or detail_soup.select_one("article")
                if not content_part:
                    content_part = detail_soup.body
                
                raw_text = content_part.get_text(separator="\n", strip=True) if content_part else ""

                # 4. AI Parse
                ai_data = self.parser.parse_campaign_data(
                    raw_text=raw_text,
                    bank_name=self.BANK_NAME
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
                else:
                    total_failed += 1

            except Exception as e:
                print(f"   ❌ Error: {e}")
                traceback.print_exc()
                total_failed += 1
                error_details.append({"url": url, "error": str(e)})

            time.sleep(1.5)

        # Log execution
        status_msg = "SUCCESS" if total_failed == 0 else ("PARTIAL" if total_saved > 0 else "FAILED")
        with get_db_session() as db:
            log_scraper_execution(
                db=db,
                scraper_name="nays",
                status=status_msg,
                total_found=total_found,
                total_saved=total_saved,
                total_skipped=total_skipped,
                total_failed=total_failed,
                error_details={"errors": error_details} if error_details else None
            )

    def _save_campaign(self, original_title: str, image_url: str, tracking_url: str, ai_data: Dict[str, Any], raw_text: str, force: bool = False) -> str:
        with get_db_session() as db:
            # Check if exists
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

            # Update fields
            campaign.title = ai_data.get("title") or original_title
            campaign.description = ai_data.get("description") or campaign.title
            campaign.reward_text = ai_data.get("reward_text")
            campaign.reward_value = ai_data.get("reward_value")
            campaign.reward_type = ai_data.get("reward_type")
            
            # Dates
            if ai_data.get("start_date"):
                try: campaign.start_date = datetime.strptime(ai_data["start_date"], "%Y-%m-%d")
                except: pass
            if not campaign.start_date:
                campaign.start_date = datetime.utcnow()
                
            if ai_data.get("end_date"):
                try: campaign.end_date = datetime.strptime(ai_data["end_date"], "%Y-%m-%d")
                except: pass

            # Conditions & Cards
            participation = ai_data.get("participation")
            conditions_list = ai_data.get("conditions", [])
            if isinstance(conditions_list, str):
                conditions_list = [c.strip() for c in conditions_list.split("\n") if c.strip()]
            
            if participation and participation != "Detayları İnceleyin":
            
            campaign.conditions = "\n".join(conditions_list)
            
            cards = ai_data.get("cards")
            if isinstance(cards, list):
                campaign.eligible_cards = ", ".join(cards)
            else:
                campaign.eligible_cards = str(cards) if cards else self.CARD_NAME

            # Sector
            sector_slug = ai_data.get("sector", "diger")
            sector = db.query(Sector).filter(Sector.slug == sector_slug).first()
            if sector:
                campaign.sector_id = sector.id

            # Image - Prefer new one if old one is default/logo
            if image_url and (not campaign.image_url or "logo.png" in campaign.image_url or force):
                campaign.image_url = image_url
            
            campaign.clean_text = raw_text
            campaign.updated_at = datetime.utcnow()

            try:
                db.commit()
                db.refresh(campaign)

                # Brands via brand_matcher
                from src.services.brand_matcher import get_or_create_brands_list
                brand_ids = get_or_create_brands_list(
                    db_session=db,
                    brand_names=data.get("brands", []),
                    brand_cache=getattr(self, 'brand_cache', {}),
                    sector_id=sector.id if sector else None
                )
                for bid in brand_ids:
                    try:
                        link = db.query(CampaignBrand).filter(
                            CampaignBrand.campaign_id == campaign.id,
                            CampaignBrand.brand_id == bid
                        ).first()
                        if not link:
                            db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                            db.commit()
                    except Exception as e:
                        db.rollback()
                        print(f"   ⚠️ CampaignBrand link failed: {e}")
                return "saved"
            except Exception as e:
                db.rollback()
                print(f"   ❌ Save Error: {e}")
                return "error"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of campaigns")
    parser.add_argument("--force", action="store_true", help="Force update")
    args = parser.parse_args()
    
    scraper = NaysScraper()
    scraper.run(limit=args.limit, force=args.force)
