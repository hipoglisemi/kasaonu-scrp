import sys
import os

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.database import get_db_session
from src.models import Bank, Card, Sector, Campaign, CampaignBrand
from src.services.ai_parser import parse_api_campaign
from src.utils.logger_utils import log_scraper_execution
from src.services.brand_normalizer import cleanup_brands
from src.utils.slug_generator import get_unique_slug
from src.utils.cache_manager import clear_cache
from src.utils.scraper_utils import is_url_blocked, upsert_campaign

class FenerparaScraper:
    """
    Scraper for Fenerpara (QNB) campaigns using their public JSON API.
    """

    BASE_URL = "https://www.fenerpara.com"
    API_URL = "https://www.fenerpara.com/api/campaign/getall?isArchived=false"
    BANK_NAME = "QNB"
    CARD_NAME = "Fenerpara"
    CARD_SLUG = "fenerpara"

    def __init__(self):
        self.bank_id = None
        self.card_id = None

        with get_db_session() as db:
            bank = db.query(Bank).filter((Bank.slug == "qnb") | (Bank.name.ilike("%qnb%"))).first()
            if not bank:
                print(f"   🏦 Creating Bank: {self.BANK_NAME}")
                bank = Bank(name=self.BANK_NAME, slug="qnb", logo_url="https://www.qnbcard.com.tr/Content/images/logo.png", is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
            self.bank_id = bank.id

            card = db.query(Card).filter(Card.bank_id == bank.id, Card.slug == self.CARD_SLUG).first()
            if not card:
                print(f"   💳 Creating Card: {self.CARD_NAME}")
                card = Card(bank_id=bank.id, name=self.CARD_NAME, slug=self.CARD_SLUG, card_type="credit", is_active=True)
                db.add(card)
                db.commit()
                db.refresh(card)
            self.card_id = card.id

    def _fetch_campaigns(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        print(f"   🌐 Fetching campaigns from Fenerpara API...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "x-requested-with": "XMLHttpRequest"
        }

        try:
            response = requests.get(self.API_URL, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                print(f"   ⚠️ API returned non-list data: {type(data)}")
                return []

            print(f"   📦 Found {len(data)} campaigns from Fenerpara API.")
            return data[:limit] if limit else data
        except Exception as e:
            print(f"   ❌ API fetch failed: {e}")
            return []

    def _process_item(self, item: Dict[str, Any]) -> str:
        title = item.get("Title", "").strip()
        if not title or item.get("IsHideCampaign"):
            return "skipped"

        c_path = item.get("CampaignUrl") or item.get("SeoProperty", {}).get("Name") or item.get("Id")
        campaign_url = f"{self.BASE_URL}/kampanyalar/{c_path}"

        with get_db_session() as db:
            if is_url_blocked(db, campaign_url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"

            existing = db.query(Campaign).filter(Campaign.tracking_url == campaign_url).first()
            if existing and existing.is_active and existing.is_approved:
                new_image_url = None
                if item.get("Id") and item.get("IsHaveMediums"):
                    new_image_url = f"{self.BASE_URL}/medium/Campaign-DetailImage-{item.get('Id')}.vsf"

                if new_image_url and existing.image_url != new_image_url:
                    print(f"   🔄 Updating Image URL for existing campaign: {title}")
                    existing.image_url = new_image_url
                    db.commit()
                else:
                    print(f"   ⏭️ Skipped (Already exists and active): {title}")
                return "skipped"

        content_html = item.get("Content") or item.get("ShortDescription") or ""

        ai_data = parse_api_campaign(
            title=title,
            short_description=item.get("ShortDescription") or title,
            content_html=content_html,
            bank_name=self.BANK_NAME,
            tracking_url=campaign_url
        )

        if ai_data.get("_ai_failed"):
            return "error"

        return self._save_campaign(ai_data, campaign_url, item)

    def _save_campaign(self, ai_data: Dict[str, Any], url: str, item: Dict[str, Any]) -> str:
        try:
            with get_db_session() as db:
                if is_url_blocked(db, url):
                    print(f"   🚫 Skipped (Safety: Blocklisted): {ai_data.get('title') or url}")
                    return "skipped"

                final_sector_slug = ai_data.get('sector')

                if ai_data.get('brands'):
                    from src.models import PointBlankRule
                    pbe_rules = db.query(PointBlankRule).filter(
                        PointBlankRule.brand_name.in_(ai_data.get('brands')),
                        PointBlankRule.is_verified == True
                    ).all()
                    for rule in pbe_rules:
                        if rule.sector_slug and rule.sector_slug != 'BLACKLIST':
                            final_sector_slug = rule.sector_slug
                            print(f"      [PBE Override] Forced sector to '{final_sector_slug}' due to brand '{rule.brand_name}'")
                            break

                sector = db.query(Sector).filter((Sector.slug == final_sector_slug) | (Sector.name.ilike(final_sector_slug))).first() if final_sector_slug else None
                if not sector:
                    sector = db.query(Sector).filter(Sector.slug == 'diger').first()
                sector_id = sector.id if sector else None

                image_url = None
                if item.get("Id") and item.get("IsHaveMediums"):
                    image_url = f"{self.BASE_URL}/medium/Campaign-DetailImage-{item.get('Id')}.vsf"

                slug = get_unique_slug(ai_data.get('short_title') or ai_data.get('title'), db, Campaign)

                start_date = None
                end_date = None
                if item.get("StartDate"):
                    try:
                        start_date = datetime.fromisoformat(item["StartDate"]).date()
                    except Exception:
                        pass
                if not start_date and ai_data.get("start_date"):
                    try:
                        start_date = datetime.strptime(ai_data["start_date"], "%Y-%m-%d").date()
                    except Exception:
                        pass

                if item.get("EndDate"):
                    try:
                        end_date = datetime.fromisoformat(item["EndDate"]).date()
                    except Exception:
                        pass
                if not end_date and ai_data.get("end_date"):
                    try:
                        end_date = datetime.strptime(ai_data["end_date"], "%Y-%m-%d").date()
                    except Exception:
                        pass

                campaign = Campaign(
                    card_id=self.card_id,
                    sector_id=sector_id,
                    title=ai_data.get("short_title") or ai_data.get("title"),
                    slug=slug,
                    description=ai_data.get("description"),
                    conditions="\n".join(ai_data.get("conditions", [])) if isinstance(ai_data.get("conditions"), list) else ai_data.get("conditions"),
                    reward_text=ai_data.get("reward_text", "Fırsatı Kaçırmayın"),
                    reward_value=ai_data.get("reward_value"),
                    reward_type=ai_data.get("reward_type"),
                    start_date=start_date,
                    end_date=end_date,
                    image_url=image_url or f"{self.BASE_URL}/_assets/img/dark-logo.svg",
                    tracking_url=url,
                    is_active=True,
                    ai_marketing_text=ai_data.get("ai_marketing_text"),
                    clean_text=ai_data.get("_clean_text"),
                    participation=ai_data.get("participation"),
                    eligible_cards=", ".join(ai_data.get("cards", [])) if isinstance(ai_data.get("cards"), list) and ai_data.get("cards") else self.CARD_NAME
                )

                campaign, op_status = upsert_campaign(db, campaign)
                db.commit()

                if op_status == "revived":
                    print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
                elif op_status == "saved":
                    print(f"   ✅ Saved: {campaign.title[:50]}...")

                db.refresh(campaign)

                if ai_data.get('brands'):
                    clean_brands = cleanup_brands(ai_data.get('brands'))
                    from src.services.brand_matcher import get_or_create_brands_list
                    brand_ids = get_or_create_brands_list(
                        db_session=db,
                        brand_names=ai_data.get("brands", []),
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
            return op_status
        except Exception as e:
            print(f"      ❌ DB Save Error: {e}")
            return "error"

    def run(self, limit: Optional[int] = None):
        print(f"🚀 Starting Fenerpara Scraper...")
        items = self._fetch_campaigns(limit=limit)

        success: int = 0
        revived: int = 0
        skipped: int = 0
        failed: int = 0
        error_details: List[Dict[str, Any]] = []

        for item in items:
            try:
                res = self._process_item(item)
                if res == "saved":
                    success += 1
                elif res == "revived":
                    revived += 1
                elif res == "skipped":
                    skipped += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                error_details.append({"url": str(item.get("Id")), "error": str(e)})

        status = "SUCCESS" if failed == 0 else ("PARTIAL" if success > 0 else "FAILED")
        with get_db_session() as db:
            log_scraper_execution(
                db=db,
                scraper_name="fenerpara",
                status=status,
                total_found=len(items),
                total_saved=success,
                total_skipped=skipped,
                total_failed=failed,
                total_revived=revived,
                error_details={"errors": error_details} if error_details else None
            )

        clear_cache('campaigns:*')

if __name__ == "__main__":
    limit = 5 if os.environ.get('TEST_MODE') == '1' else None
    scraper = FenerparaScraper()
    scraper.run(limit=limit)
