import sys
import os
# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from src.database import get_db_session
from src.models import Campaign, Bank, Card, Sector, CampaignBrand
from src.services.ai_parser import parse_api_campaign
from src.utils.slug_generator import get_unique_slug
from src.utils.cache_manager import clear_cache
from src.utils.scraper_utils import is_url_blocked, upsert_campaign

class IstanbulkartScraper:
    """
    Scraper for Istanbulkart campaigns using the public Umbraco API.
    Does not require browser automation.
    """
    
    BASE_URL = 'https://www.istanbulkart.istanbul'
    API_URL = 'https://cms.istanbulkart.istanbul/umbraco/api/Campaign/GetIstanbulkartCampaigns'
    BANK_NAME = 'İstanbulkart'
    CARD_NAME = 'İstanbulkart'
    
    def __init__(self):
        self.bank = None
        self.card = None
        
        # Initialize bank and card from DB
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == "istanbulkart").first()
            if not bank:
                print(f"Creating bank: {self.BANK_NAME}")
                bank = Bank(name=self.BANK_NAME, slug="istanbulkart", logo_url="/logos/banks/istanbulkart.png", is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
            self.bank = bank
            
            card = db.query(Card).filter(Card.slug == "istanbulkart", Card.bank_id == self.bank.id).first()
            if not card:
                print(f"Creating card: {self.CARD_NAME}")
                card = Card(name=self.CARD_NAME, bank_id=self.bank.id, slug="istanbulkart", card_type="prepaid", logo_url="/logos/cards/istanbulkart.png", is_active=True)
                db.add(card)
                db.commit()
                db.refresh(card)
            self.card = card

    def _fetch_list(self) -> List[Dict[str, Any]]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Origin': 'https://www.istanbulkart.istanbul',
            'Referer': 'https://www.istanbulkart.istanbul/',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json'
        }
        
        try:
            print(f"   Fetching campaigns from API...")
            # languageId: 2 is required for Turkish campaigns
            response = requests.post(self.API_URL, json={'languageId': 2}, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            campaigns = data.get('Campaigns', [])
            # Sadece "Güncel Kampanyalar" sekmesindeki aktif kampanyaları al (IsPast = false)
            active_campaigns = [c for c in campaigns if not c.get('IsPast')]
            return active_campaigns
        except Exception as e:
            print(f"   ❌ Error fetching API: {e}")
            return []

    def _process_item(self, item: Dict[str, Any]):
        # Ignore completely past/expired campaigns early to save API calls
        if item.get('IsPast'):
            return "skipped"

        title = item.get('HeadLine') or "Başlıksız Kampanya"
        camp_id = item.get('Id')
        if not camp_id:
            return "skipped"

        full_url = f"{self.BASE_URL}/campaignsDetail?id={camp_id}"
        
        start_date = self._parse_iso_date(item.get('Start'))
        end_date = self._parse_iso_date(item.get('Finish'))
        
        with get_db_session() as db:
            if is_url_blocked(db, full_url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"
            
            from src.utils.scraper_utils import clean_url_for_matching
            clean_target = clean_url_for_matching(full_url)
            existing = None
            all_camps = db.query(Campaign).filter(
                Campaign.tracking_url.isnot(None),
                Campaign.card_id == (self.card.id if self.card else None)
            ).order_by(Campaign.is_active.desc()).all()
            for camp in all_camps:
                if clean_url_for_matching(camp.tracking_url) == clean_target:
                    existing = camp
                    break
            
            if existing and existing.is_active and existing.is_approved:
                existing_end = existing.end_date.date() if hasattr(existing.end_date, 'date') else existing.end_date
                incoming_end = end_date.date() if hasattr(end_date, 'date') else end_date
                if existing_end == incoming_end:
                    print(f"   ⏭️ Skipped (Already exists, active and approved): {title}")
                    return "skipped"

        print(f"   Processing: {title}")
        
        # High resolution detail image
        image_url = item.get('DetailPictureUrl') or item.get('CoverPictureUrl')
        
        description_html = item.get('Description') or ''
        conditions_html = item.get('Conditions') or ''
        
        combined_content = f"--- DETAIL PAGE ---\n{description_html}\n\n--- CONDITIONS ---\n{conditions_html}"

        ai_result = parse_api_campaign(
            title=title,
            short_description="",
            content_html=combined_content,
            bank_name=self.BANK_NAME,
            scraper_sector=None,
            tracking_url=full_url,
            og_title=title
        )
        
        display_title = ai_result.get('title') or ai_result.get('short_title') or title
        
        # Create a nice SEO slug from the AI optimized title
        seo_slug = get_unique_slug(display_title, get_db_session(), Campaign)
        
        return self._save_campaign(
            title=display_title,
            details_text="",
            image_url=image_url,
            tracking_url=full_url,
            start_date=start_date,
            end_date=end_date,
            ai_data=ai_result,
            seo_slug=seo_slug
        )

    def _save_campaign(self, title: str, details_text: str, image_url: Optional[str],
                       tracking_url: str, start_date, end_date, ai_data: Dict[str, Any], seo_slug: Optional[str] = None):
        try:
            with get_db_session() as db:
                if is_url_blocked(db, tracking_url):
                    print(f"   🚫 Skipped (Safety: Blocklisted): {title}")
                    return "skipped"

                sector_name = ai_data.get('sector', 'Diğer')
                sector = db.query(Sector).filter((Sector.slug == sector_name) | (Sector.name.ilike(sector_name))).first()
                if not sector:
                    sector = db.query(Sector).filter(Sector.slug == 'diger').first()
                sector_id = sector.id if sector else None

                slug_source = seo_slug if seo_slug and len(seo_slug) > 5 else title
                slug = get_unique_slug(slug_source, db, Campaign)

                campaign = Campaign(
                    slug=slug,
                    title=title,
                    card_id=self.card.id if self.card else None,
                    sector_id=sector_id,
                    reward_value=ai_data.get('reward_value'),
                    reward_type=ai_data.get('reward_type'),
                    reward_text=ai_data.get('reward_text', 'Detayları İnceleyin'),
                    clean_text=ai_data.get('_clean_text', ''),
                    description=ai_data.get('description') or details_text,
                    ai_marketing_text=ai_data.get('ai_marketing_text'),
                    conditions="\n".join(ai_data.get('conditions', [])),
                    start_date=start_date,
                    end_date=end_date,
                    image_url=image_url,
                    tracking_url=tracking_url,
                    is_active=True,
                    participation=ai_data.get('participation'),
                    eligible_cards=", ".join(ai_data.get('cards', [])) if ai_data.get('cards') else None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                campaign, op_status = upsert_campaign(db, campaign)
                db.commit()
                
                if op_status == "revived":
                    print(f"   ♻️  Revived Passive Campaign: {campaign.title}")
                elif op_status == "saved":
                    print(f"   ✅ Saved: {campaign.title}")
                
                db.refresh(campaign)

                # Brands via brand_matcher
                from src.services.brand_matcher import get_or_create_brands_list
                brand_names = ai_data.get("brands", [])
                brand_ids = get_or_create_brands_list(
                    db=db,
                    names=brand_names,
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
            print(f"   ❌ Error saving: {e}")
            return "error"

    def _parse_iso_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            # Handle format like 2026-06-02T00:00:00
            if 'T' in date_str:
                return datetime.fromisoformat(date_str)
            return datetime.strptime(date_str, "%Y-%m-%d")
        except:
            return None

    def run(self):
        print(f"🚀 Starting {self.BANK_NAME} {self.CARD_NAME} Scraper...")
        success_count = 0
        total_revived = 0
        skipped_count = 0
        failed_count = 0
        total_found = 0
        error_details = []
        
        items = self._fetch_list()
        
        if not items:
            print("❌ No campaigns found or API failed.")
            return

        print(f"   Found {len(items)} items in API.")
        total_found = len(items)
        
        for item in items:
            # Recheck expiry just to be safe
            end_date_str = item.get('Finish')
            if end_date_str:
                try:
                    end_date = self._parse_iso_date(end_date_str)
                    if end_date and end_date < datetime.now():
                        skipped_count += 1
                        continue
                except:
                    pass
            
            try:
                res = self._process_item(item)
                if res == "saved":
                    success_count += 1
                elif res == "revived":
                    total_revived += 1
                elif res == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                print(f"❌ Error processing item: {e}")
                failed_count += 1
                error_details.append({"id": item.get('Id', 'unknown'), "error": str(e)})

        print(f"\n✅ Özet: {total_found} bulundu, {success_count} eklendi, {total_revived} canlandı, {skipped_count} atlandı, {failed_count} hata aldı.")
        
        status = "SUCCESS"
        if failed_count > 0:
             status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"
             
        try:
            with get_db_session() as db:
                from src.utils.logger_utils import log_scraper_execution
                log_scraper_execution(
                     db=db,
                     scraper_name="istanbulkart",
                     status=status,
                     total_found=total_found,
                     total_saved=success_count,
                     total_skipped=skipped_count,
                     total_failed=failed_count,
                     total_revived=total_revived,
                     error_details={"errors": error_details} if error_details else None
                )
        except Exception as le:
             print(f"⚠️ Could not save scraper log: {le}")
        
        print("🧹 Clearing API cache...")
        clear_cache('campaigns:*')
        clear_cache('cards:*')

if __name__ == "__main__":
    scraper = IstanbulkartScraper()
    scraper.run()
