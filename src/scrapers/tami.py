import os
import sys
import json
import re
import time
import random
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.models import Campaign, Bank, Card, Sector, Brand, CampaignBrand
from src.database import get_db_session
from src.services.ai_parser import parse_api_campaign
from src.utils.slug_generator import get_unique_slug
from src.utils.scraper_utils import should_skip_campaign
from src.utils.logger_utils import log_scraper_execution

class TamiScraper:
    BASE_URL = "https://www.tami.com.tr"
    LIST_PAGE_URL = "https://www.tami.com.tr/kampanyalar/tami-kart"
    BANK_NAME = "Tami"
    BANK_SLUG = "tami"
    CARD_NAME = "Tami Kart"
    CARD_SLUG = "tami-kart"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        })
        self.build_id = self._fetch_build_id()
        self.bank_id = self._get_or_create_bank()
        self.card_id = self._get_or_create_card()

    def _fetch_build_id(self) -> str:
        """Extract Next.js buildId from the main page."""
        try:
            response = self.session.get(self.LIST_PAGE_URL, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            script = soup.find("script", id="__NEXT_DATA__")
            if script:
                data = json.loads(script.string)
                return data.get("buildId", "")
        except Exception as e:
            print(f"❌ Error fetching buildId: {e}")
        return ""

    def _get_or_create_bank(self) -> int:
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == self.BANK_SLUG).first()
            if not bank:
                bank = Bank(name=self.BANK_NAME, slug=self.BANK_SLUG, is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
            return bank.id

    def _get_or_create_card(self) -> int:
        with get_db_session() as db:
            card = db.query(Card).filter(Card.slug == self.CARD_SLUG).first()
            if not card:
                card = Card(
                    name=self.CARD_NAME, 
                    slug=self.CARD_SLUG, 
                    bank_id=self.bank_id, 
                    is_active=True,
                    card_type="debit" # Tami is generally a prepaid/debit oriented card
                )
                db.add(card)
                db.commit()
                db.refresh(card)
            return card.id

    def run(self, limit: Optional[int] = None, force: bool = False):
        print(f"🚀 Starting {self.BANK_NAME} Scraper...")
        
        # Respect TEST_MODE if set in environment
        if os.getenv("TEST_MODE") == "1" and not limit:
            print("🧪 TEST_MODE active: Limiting to 1 campaign.")
            limit = 1

        if not self.build_id:
            print("❌ Could not determine buildId. Aborting.")
            return

        api_url = f"{self.BASE_URL}/_next/data/{self.build_id}/kampanyalar/tami-kart.json"
        try:
            response = self.session.get(api_url, timeout=20)
            response.raise_for_status()
            data = response.json()
            campaigns_list = data.get("pageProps", {}).get("campaigns", [])
        except Exception as e:
            print(f"❌ Error fetching campaign list from API: {e}")
            return

        if limit:
            campaigns_list = campaigns_list[:limit]

        total_found = len(campaigns_list)
        total_saved = 0
        total_skipped = 0
        total_failed = 0
        error_details = []

        for i, item in enumerate(campaigns_list):
            campaign_obj = item.get("campaign", {})
            slug = campaign_obj.get("slug")
            if not slug:
                continue

            tracking_url = f"{self.BASE_URL}/kampanya/{slug}"
            print(f"[{i+1}/{total_found}] Processing: {tracking_url}")

            try:
                # 1. Early Check
                with get_db_session() as db:
                    if not force and should_skip_campaign(db, tracking_url, card_id=self.card_id):
                        print(f"   ⏭️  Skipped (Already exists or blocked)")
                        total_skipped += 1
                        continue

                # 2. Fetch Detail JSON
                detail_api_url = f"{self.BASE_URL}/_next/data/{self.build_id}/kampanya/{slug}.json"
                detail_resp = self.session.get(detail_api_url, timeout=20)
                detail_resp.raise_for_status()
                detail_data = detail_resp.json().get("pageProps", {}).get("campaignDetail", {})

                if not detail_data:
                    print(f"   ⚠️  No detail data found for {slug}")
                    total_failed += 1
                    continue

                # 3. Extract Data
                title = detail_data.get("title") or campaign_obj.get("title")
                details_html = detail_data.get("details") or ""
                
                # Clean HTML for AI to understand better
                soup_detail = BeautifulSoup(details_html, 'html.parser')
                clean_details = soup_detail.get_text(separator='\n', strip=True)
                
                image_url = detail_data.get("detailImage", {}).get("url") or campaign_obj.get("image", {}).get("url")
                if image_url and not image_url.startswith("http"):
                    image_url = urljoin(self.BASE_URL, image_url)

                # Collect all text content for AI
                content_parts = [f"Başlık: {title}", f"İçerik Detayları:\n{clean_details}"]
                for section in detail_data.get("sections", []):
                    sec_title = section.get("title", "")
                    sec_desc = section.get("description", "")
                    if sec_title or sec_desc:
                        content_parts.append(f"{sec_title}\n{sec_desc}")
                
                raw_content = "\n\n".join(content_parts)

                # 4. AI Parse
                # Note: We use force if we want to re-parse existing campaigns with new AI rules
                ai_data = parse_api_campaign(
                    title=title,
                    short_description=title,
                    content_html=raw_content,
                    bank_name=self.BANK_NAME,
                    tracking_url=tracking_url,
                    force=force
                )

                # 5. Save
                status = self._save_campaign(title, image_url, tracking_url, ai_data)
                if status == "saved":
                    total_saved += 1
                elif status == "skipped":
                    total_skipped += 1
                else:
                    total_failed += 1

            except Exception as e:
                print(f"   ❌ Error: {e}")
                total_failed += 1
                error_details.append({"url": tracking_url, "error": str(e)})

            time.sleep(random.uniform(0.5, 1.5))

        print(f"🏁 Scraping finished. Found: {total_found}, Saved: {total_saved}, Skipped: {total_skipped}, Failed: {total_failed}")

        # Final Log
        status_msg = "SUCCESS" if total_failed == 0 else ("PARTIAL" if total_saved > 0 else "FAILED")
        with get_db_session() as db:
            log_scraper_execution(
                db=db,
                scraper_name="tami",
                status=status_msg,
                total_found=total_found,
                total_saved=total_saved,
                total_skipped=total_skipped,
                total_failed=total_failed,
                error_details={"errors": error_details} if error_details else None
            )

    def _save_campaign(self, original_title: str, image_url: Optional[str], tracking_url: str, ai_data: Dict[str, Any]) -> str:
        with get_db_session() as db:
            # Title & Slug
            final_title = ai_data.get("short_title") or ai_data.get("title") or original_title
            slug = get_unique_slug(final_title, db, Campaign)

            # Sector
            sector_slug = ai_data.get("sector", "diger")
            sector = db.query(Sector).filter(Sector.slug == sector_slug).first()
            if not sector:
                sector = db.query(Sector).filter(Sector.slug == "diger").first()

            # Dates
            start_date = None
            if ai_data.get("start_date"):
                try: start_date = datetime.strptime(ai_data["start_date"], "%Y-%m-%d")
                except: pass
            
            end_date = None
            if ai_data.get("end_date"):
                try: end_date = datetime.strptime(ai_data["end_date"], "%Y-%m-%d")
                except: pass

            # Conditions
            conditions_lines = []
            participation = ai_data.get("participation")
            if participation and participation != "Detayları İnceleyin":
                conditions_lines.append(f"KATILIM: {participation}")
            
            conditions = ai_data.get("conditions")
            if isinstance(conditions, list):
                conditions_lines.extend([str(c) for c in conditions if c])
            
            conditions_text = "\n".join(conditions_lines)
            eligible_cards = ", ".join(ai_data.get("cards", [])) if ai_data.get("cards") else self.CARD_NAME

            campaign = Campaign(
                card_id=self.card_id,
                sector_id=sector.id if sector else None,
                slug=slug,
                title=final_title,
                description=ai_data.get("description") or final_title,
                reward_text=ai_data.get("reward_text"),
                reward_value=ai_data.get("reward_value"),
                reward_type=ai_data.get("reward_type"),
                conditions=conditions_text,
                eligible_cards=eligible_cards,
                image_url=image_url,
                start_date=start_date or datetime.utcnow(),
                end_date=end_date,
                is_active=True,
                tracking_url=tracking_url,
                clean_text=ai_data.get("_clean_text"),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            try:
                db.add(campaign)
                db.commit()
                db.refresh(campaign)

                # Brands
                if ai_data.get("brands"):
                    for b_name in ai_data["brands"]:
                        b_slug = re.sub(r'[^a-z0-9]+', '-', b_name.lower()).strip('-')
                        brand = db.query(Brand).filter((Brand.slug == b_slug) | (Brand.name.ilike(b_name))).first()
                        if not brand:
                            brand = Brand(name=b_name, slug=b_slug, is_active=True)
                            db.add(brand)
                            db.commit()
                            db.refresh(brand)
                        
                        cb = CampaignBrand(campaign_id=campaign.id, brand_id=brand.id)
                        db.add(cb)
                    db.commit()

                print(f"   ✅ Saved: {campaign.title}")
                return "saved"
            except Exception as e:
                db.rollback()
                print(f"   ❌ Save Error: {e}")
                return "error"

if __name__ == "__main__":
    scraper = TamiScraper()
    scraper.run()
