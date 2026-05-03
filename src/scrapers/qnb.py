import sys
import os
# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import re  # type: ignore # pyre-ignore[21]
import time  # type: ignore # pyre-ignore[21]
import requests  # type: ignore # pyre-ignore[21]
from typing import Optional, List, Dict, Any  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]

from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import parse_api_campaign  # type: ignore # pyre-ignore[21]
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
from src.services.brand_normalizer import cleanup_brands  # type: ignore # pyre-ignore[21]
from src.utils.slug_generator import get_unique_slug  # type: ignore # pyre-ignore[21]
from src.utils.cache_manager import clear_cache  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked  # type: ignore

class QNBScraper:
    """
    Scraper for QNB Finansbank campaigns using their public API.
    """
    
    BASE_URL = "https://www.qnbcard.com.tr"
    API_URL = "https://www.qnbcard.com.tr/api/Campaigns"
    BANK_NAME = "QNB"
    
    def __init__(self):
        self.bank_id = None
        self.card_id = None
        
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == "qnb").first()  # type: ignore # pyre-ignore[16]
            if not bank:
                print(f"   🏦 Creating Bank: {self.BANK_NAME}")
                bank = Bank(name=self.BANK_NAME, slug="qnb", logo_url="https://www.qnbcard.com.tr/Content/images/logo.png", is_active=True)
                db.add(bank)  # type: ignore # pyre-ignore[16]
                db.commit()  # type: ignore # pyre-ignore[16]
                db.refresh(bank)
            self.bank_id = bank.id  # type: ignore # pyre-ignore[16]
            
            card = db.query(Card).filter(Card.bank_id == bank.id, Card.slug == "qnbcard").first()  # type: ignore # pyre-ignore[16]
            if not card:
                print(f"   💳 Creating Card: QNBCard")
                card = Card(bank_id=bank.id, name="QNBCard", slug="qnbcard", card_type="credit", is_active=True)  # type: ignore # pyre-ignore[16]
                db.add(card)  # type: ignore # pyre-ignore[16]
                db.commit()  # type: ignore # pyre-ignore[16]
                db.refresh(card)
            self.card_id = card.id  # type: ignore # pyre-ignore[16]

    def _fetch_campaigns(self, limit=1000) -> List[Dict[str, Any]]:  # type: ignore # pyre-ignore[16,6]
        print(f"   🌐 Fetching campaigns from QNB API...")
        all_items = []
        page_index = 1
        take = 12
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "x-bone-language": "TR",
            "x-requested-with": "XMLHttpRequest"
        }
        
        try:
            while True:
                headers["page"] = str(page_index)
                params = {"isArchived": "false", "take": str(take)}
                
                response = requests.get(self.API_URL, params=params, headers=headers, timeout=20)
                response.raise_for_status()
                data = response.json()

                items = data.get("Items", [])
                if not items:
                    break
                    
                all_items.extend(items)
                total = data.get("TotalItems", 0)
                
                if len(all_items) >= total or (limit and len(all_items) >= limit):
                    break
                    
                page_index += 1  # type: ignore # pyre-ignore[58]
                time.sleep(0.5)
                
            return all_items[:limit] if limit else all_items  # type: ignore # pyre-ignore[16,7,6]
        except Exception as e:
            print(f"   ❌ API fetch failed: {e}")
            return all_items  # type: ignore # pyre-ignore[7]

    def _process_item(self, item: Dict[str, Any]) -> str:  # type: ignore # pyre-ignore[16,6]
        title = item.get("Title", "").strip()
        if not title:
            return "skipped"  # type: ignore # pyre-ignore[7]

        seo_name = (item.get("SeoProperty") or {}).get("Name")
        campaign_url = f"{self.BASE_URL}/kampanyalar/{seo_name}" if seo_name else f"{self.BASE_URL}/kampanyalar/{item.get('Id')}"

        with get_db_session() as db:
            if is_url_blocked(db, campaign_url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"  # type: ignore # pyre-ignore[7]

            existing = db.query(Campaign).filter(Campaign.tracking_url == campaign_url).first()  # type: ignore # pyre-ignore[16]
            if existing:
                print(f"   ⏭️ Skipped (Already exists): {title}")
                return "skipped"  # type: ignore # pyre-ignore[7]

        content_html = item.get("Content") or item.get("Description") or ""
        
        ai_data = parse_api_campaign(
            title=title,
            short_description=title,
            content_html=content_html,
            bank_name=self.BANK_NAME
        )
        
        if ai_data.get("_ai_failed"):
            return "error"  # type: ignore # pyre-ignore[7]

        return self._save_campaign(ai_data, campaign_url, item)  # type: ignore # pyre-ignore[7]

    def _save_campaign(self, ai_data: Dict[str, Any], url: str, item: Dict[str, Any]) -> str:  # type: ignore # pyre-ignore[16,6]
        try:
            with get_db_session() as db:
                if is_url_blocked(db, url):
                    print(f"   🚫 Skipped (Safety: Blocklisted): {ai_data.get('title') or url}")
                    return "skipped"  # type: ignore # pyre-ignore[7]

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

                sector = db.query(Sector).filter((Sector.slug == final_sector_slug) | (Sector.name.ilike(final_sector_slug))).first() if final_sector_slug else None  # type: ignore # pyre-ignore[16]
                if not sector:
                    sector = db.query(Sector).filter(Sector.slug == 'diger').first()  # type: ignore # pyre-ignore[16]
                sector_id = sector.id if sector else None  # type: ignore # pyre-ignore[16]

                image_url = None
                if item.get("Id") and item.get("HasImage"):
                    image_url = f"{self.BASE_URL}/medium/Campaign-DetailImage-{item.get('Id')}.vsf"

                slug = get_unique_slug(ai_data.get('short_title') or ai_data.get('title'), db, Campaign)
                
                if not self.card_id:
                    return "error"  # type: ignore # pyre-ignore[7]
                    
                campaign = Campaign(
                    card_id=self.card_id,
                    sector_id=sector_id,
                    title=ai_data.get("short_title") or ai_data.get("title"),
                    slug=slug,
                    description=ai_data.get("description"),
                    conditions="\n".join(ai_data.get("conditions", [])),
                    reward_text=ai_data.get("reward_text", "Fırsatı Kaçırmayın"),
                    reward_value=ai_data.get("reward_value"),
                    reward_type=ai_data.get("reward_type"),
                    start_date=ai_data.get("start_date"),
                    end_date=ai_data.get("end_date"),
                    image_url=image_url or "https://www.qnbcard.com.tr/Content/images/logo.png",
                    tracking_url=url,
                    is_active=True,
                    ai_marketing_text=ai_data.get("ai_marketing_text"),
                    clean_text=ai_data.get("_clean_text"),
                    participation=ai_data.get("participation"),
                    eligible_cards=", ".join(ai_data.get("cards", [])) if isinstance(ai_data.get("cards"), list) and ai_data.get("cards") else "QNBCard"
                )
                
                from src.utils.scraper_utils import upsert_campaign
                
                campaign, _op_status = upsert_campaign(db, campaign)
                db.commit()  # type: ignore # pyre-ignore[16]

                if ai_data.get('brands'):
                    clean_brands = cleanup_brands(ai_data.get('brands'))
                    # Brands via brand_matcher
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
            return locals().get("_op_status", "saved")  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"      ❌ DB Save Error: {e}")
            return "error"  # type: ignore # pyre-ignore[7]

    def run(self, limit: int = 1000):
        print(f"🚀 Starting QNB Scraper...")
        items = self._fetch_campaigns(limit=limit)
        
        success: int = 0
        skipped: int = 0
        failed: int = 0
        error_details: List[Dict[str, Any]] = []  # type: ignore # pyre-ignore[16,6]

        for item in items:
            try:
                res = self._process_item(item)
                if res == "saved":
                    success += 1  # type: ignore # pyre-ignore[58]
                elif res == "skipped":
                    skipped += 1  # type: ignore # pyre-ignore[58]
                else:
                    failed += 1  # type: ignore # pyre-ignore[58]
            except Exception as e:
                failed += 1  # type: ignore # pyre-ignore[58]
                error_details.append({"url": str(item.get("Id")), "error": str(e)})

        status = "SUCCESS" if failed == 0 else ("PARTIAL" if success > 0 else "FAILED")  # type: ignore # pyre-ignore[58]
        with get_db_session() as db:
            log_scraper_execution(
                db=db,
                scraper_name="qnb",
                status=status,
                total_found=len(items),
                total_saved=success,
                total_skipped=skipped,
                total_failed=failed,
                error_details={"errors": error_details} if error_details else None
            )
        
        clear_cache('campaigns:*')

if __name__ == "__main__":
    limit = 5 if os.environ.get('TEST_MODE') == '1' else 1000
    scraper = QNBScraper()
    scraper.run(limit=limit)
