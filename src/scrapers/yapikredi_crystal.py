import sys
import os
# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests  # type: ignore # pyre-ignore[21]
import time  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from playwright.sync_api import sync_playwright
from typing import Dict, Any, List, Optional  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import Session  # type: ignore # pyre-ignore[21]

from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Campaign, Bank, Card, Sector, Brand, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import parse_api_campaign  # type: ignore # pyre-ignore[21]
from src.utils.slug_generator import get_unique_slug  # type: ignore # pyre-ignore[21]
from src.utils.cache_manager import clear_cache  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked  # type: ignore
from src.services.brand_normalizer import cleanup_brands  # type: ignore # pyre-ignore[21]

class YapikrediCrystalScraper:
    """
    Scraper for Yapı Kredi Crystal campaigns using the public API.
    Does not require browser automation (Playwright/Selenium).
    """
    
    BASE_URL = 'https://www.crystalcard.com.tr'
    LIST_API_URL = 'https://www.crystalcard.com.tr/api/campaigns?campaignSectorId=a5e7279b-0c32-4b5f-a8cd-97089a1092c2&campaignSectorKey=tum-kampanyalar'
    BANK_NAME = 'Yapı Kredi'
    CARD_NAME = 'Crystal' # The specific card program
    
    def __init__(self):
        self.bank = None
        self.card = None
        
        # Initialize bank and card from DB
        with get_db_session() as db:
            bank = db.query(Bank).filter(Bank.slug == "yapi-kredi").first()  # type: ignore # pyre-ignore[16]
            if not bank:
                print(f"Creating bank: {self.BANK_NAME}")
                bank = Bank(name=self.BANK_NAME, slug="yapi-kredi", logo_url="/logos/cards/yapikredi.png", is_active=True)
                db.add(bank)  # type: ignore # pyre-ignore[16]
                db.commit()  # type: ignore # pyre-ignore[16]
                db.refresh(bank)
            self.bank = bank
            
            card = db.query(Card).filter(Card.slug == "crystal", Card.bank_id == self.bank.id).first()  # type: ignore # pyre-ignore[16]
            if not card:
                print(f"Creating card: {self.CARD_NAME}")
                card = Card(name=self.CARD_NAME, bank_id=self.bank.id, slug="crystal", card_type="credit", logo_url="/logos/cards/yapikredicrystal.png", is_active=True)  # type: ignore # pyre-ignore[16]
                db.add(card)  # type: ignore # pyre-ignore[16]
                db.commit()  # type: ignore # pyre-ignore[16]
                db.refresh(card)
            self.card = card

    def _fetch_list(self, page: int) -> List[Dict[str, Any]]:  # type: ignore # pyre-ignore[16,6]
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': f'{self.BASE_URL}/kampanyalar',
            'Accept': 'application/json, text/plain, */*',
            'page': str(page)
        }
        
        try:
            print(f"   Fetching page {page}...")
            response = requests.get(self.LIST_API_URL, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            return data.get('Items', [])  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"   Error fetching list page {page}: {e}")
            return []  # type: ignore # pyre-ignore[7]

    def _process_item(self, item: Dict[str, Any]):  # type: ignore # pyre-ignore[16,6]
        title = item.get('Title') or item.get('PageTitle') or "Başlıksız Kampanya"
        url_suffix = item.get('Url')
        if not url_suffix:
            return "skipped"  # type: ignore # pyre-ignore[7]

        if url_suffix.startswith('http'):
            full_url = url_suffix
        else:
            full_url = f"{self.BASE_URL}{url_suffix}"
        
        with get_db_session() as db:
            if is_url_blocked(db, full_url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"  # type: ignore # pyre-ignore[7]

            existing = db.query(Campaign).filter(Campaign.tracking_url == full_url).first()  # type: ignore # pyre-ignore[16]
            if existing and existing.clean_text and len(existing.clean_text) >= 600:
                print(f"   ⏭️ Skipped (Already exists and fully scraped): {title}")
                return "skipped"  # type: ignore # pyre-ignore[7]

        print(f"   Processing: {title}")
        
        api_image_url = item.get('ImageUrl')
        if api_image_url and not api_image_url.startswith('http'):
            api_image_url = f"{self.BASE_URL}{api_image_url}"
        
        short_description = item.get('ShortDescription') or ''
        start_date_str = item.get('StartDate')
        end_date_str = item.get('EndDate')
        
        start_date = self._parse_iso_date(start_date_str)
        end_date = self._parse_iso_date(end_date_str)
        
        # NEW: Fetch detail page for full content using a browser for dynamic content
        print(f"      🌐 Fetching detail page (Browser Mode) for full content: {full_url}")
        browser_html = ""
        og_title = None
        try:
            with sync_playwright() as p:
                browser = p.firefox.launch(headless=True)
                context = browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                page = context.new_page()
                # Go to URL and wait for domcontentloaded
                page.goto(full_url, wait_until="domcontentloaded", timeout=20000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)
                
                # Extract og:title
                og_title = page.locator('meta[property="og:title"]').get_attribute('content')
                
                browser_html = page.content()
                browser.close()
            
            if browser_html:
                content_html = browser_html
        except Exception as e:
            print(f"      ⚠️ Browser fetch failed, falling back to API content: {e}")
            content_html = item.get('Content') or ''

        # COMBINE: API data is usually cleaner than the dynamic detail page.
        # We combine API description with the detail content to give AI best of both worlds.
        api_desc = item.get('Description') or ''
        combined_content = f"--- API DATA ---\n{api_desc}\n\n--- DETAIL PAGE ---\n{content_html}"

        scraper_sector = item.get('Category') or item.get('Type') or item.get('SectorName') or None
        
        ai_result = parse_api_campaign(
            title=title,
            short_description=short_description,
            content_html=combined_content,
            bank_name=self.BANK_NAME,
            scraper_sector=scraper_sector,
            tracking_url=full_url,
            og_title=og_title
        )
        
        display_title = ai_result.get('short_title') or title
        
        return self._save_campaign(  # type: ignore # pyre-ignore[7]
            title=display_title,
            details_text=short_description,
            image_url=api_image_url,
            tracking_url=full_url,
            start_date=start_date,
            end_date=end_date,
            ai_data=ai_result,
            seo_slug=item.get('Url', '').strip('/').split('/')[-1] if item.get('Url') else None
        )

    def _save_campaign(self, title: str, details_text: str, image_url: Optional[str],  # type: ignore # pyre-ignore[16,6]
                       tracking_url: str, start_date, end_date, ai_data: Dict[str, Any], seo_slug: Optional[str] = None):  # type: ignore # pyre-ignore[16,6]
        try:
            with get_db_session() as db:
                # Early safety check
                if is_url_blocked(db, tracking_url):
                    print(f"   🚫 Skipped (Safety: Blocklisted): {title}")
                    return "skipped"  # type: ignore # pyre-ignore[7]

                # Map sector
                sector_name = ai_data.get('sector', 'Diğer')
                sector = db.query(Sector).filter((Sector.slug == sector_name) | (Sector.name.ilike(sector_name))).first()  # type: ignore # pyre-ignore[16]
                if not sector:
                    sector = db.query(Sector).filter(Sector.slug == 'diger').first()  # type: ignore # pyre-ignore[16]
                sector_id = sector.id if sector else None  # type: ignore # pyre-ignore[16]

                # Use seo_slug if valid, otherwise fallback to title
                slug_source = seo_slug if seo_slug and len(seo_slug) > 5 else title
                slug = get_unique_slug(slug_source, db, Campaign)

                campaign = Campaign(  # type: ignore
                    slug=slug,  # type: ignore
                    title=title,  # type: ignore
                    card_id=self.card.id if self.card else None,  # type: ignore
                    sector_id=sector_id,  # type: ignore
                    reward_value=ai_data.get('reward_value'),  # type: ignore
                    reward_type=ai_data.get('reward_type'),  # type: ignore
                    reward_text=ai_data.get('reward_text', 'Detayları İnceleyin'),  # type: ignore
                    clean_text=ai_data.get('_clean_text', ''),  # type: ignore
                    description=ai_data.get('description') or details_text,  # type: ignore
                    ai_marketing_text=ai_data.get('ai_marketing_text'),  # type: ignore
                    conditions="\n".join(ai_data.get('conditions', [])),  # type: ignore
                    start_date=start_date,  # type: ignore
                    end_date=end_date,  # type: ignore
                    image_url=image_url,  # type: ignore
                    tracking_url=tracking_url,  # type: ignore
                    is_active=True,  # type: ignore
                    participation=ai_data.get('participation'),  # type: ignore
                    eligible_cards=", ".join(ai_data.get('cards', [])) if ai_data.get('cards') else None,  # type: ignore
                    created_at=datetime.utcnow(),  # type: ignore
                    updated_at=datetime.utcnow()  # type: ignore
                )
                
                # Use centralized upsert_campaign for revival and quality control
                from src.utils.scraper_utils import upsert_campaign
                campaign, op_status = upsert_campaign(db, campaign)
                db.commit()

                if op_status == "revived":
                    print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
                elif op_status == "saved":
                     print(f"   ✅ Saved: {campaign.title[:50]}...")
                
                db.refresh(campaign)


                # Brands via brand_matcher
                from src.services.brand_matcher import get_or_create_brands_list  # type: ignore
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
            print(f"   ❌ Error saving: {e}")
            return "error"  # type: ignore # pyre-ignore[7]

    def _parse_iso_date(self, date_str: Optional[str]) -> Optional[datetime]:  # type: ignore # pyre-ignore[16,6]
        if not date_str:
            return None  # type: ignore # pyre-ignore[7]
        try:
            return datetime.fromisoformat(date_str)  # type: ignore # pyre-ignore[7]
        except:
            return None  # type: ignore # pyre-ignore[7]

    def run(self):
        print(f"🚀 Starting {self.BANK_NAME} {self.CARD_NAME} Scraper...")
        page = 1
        success_count = 0
        total_revived = 0
        skipped_count = 0
        failed_count = 0
        total_found = 0
        error_details = []
        
        while True:
            items = self._fetch_list(page)
            if not items:
                break
                
            print(f"   Found {len(items)} items on page {page}")
            total_found += len(items)  # type: ignore # pyre-ignore[58]
            
            active_count = 0
            for item in items:
                # Filter expired
                end_date_str = item.get('EndDate')
                if end_date_str:
                    try:
                        end_date = datetime.fromisoformat(end_date_str)
                        if end_date < datetime.now():
                            continue
                    except:
                        pass
                
                active_count += 1  # type: ignore # pyre-ignore[58]
                try:
                    res = self._process_item(item)
                    if res == "saved":
                        success_count += 1  # type: ignore # pyre-ignore[58]
                    elif res == "revived":
                        total_revived += 1
                    elif res == "skipped":
                        skipped_count += 1  # type: ignore # pyre-ignore[58]
                    else:
                        failed_count += 1  # type: ignore # pyre-ignore[58]
                except Exception as e:
                    print(f"❌ Error processing item: {e}")
                    failed_count += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": item.get('Url', 'unknown'), "error": str(e)})
            
            if active_count == 0 and len(items) > 0:  # type: ignore # pyre-ignore[58]
                break
                
            page += 1  # type: ignore # pyre-ignore[58]
            time.sleep(1)

        print(f"\n✅ Özet: {total_found} bulundu, {success_count} eklendi, {total_revived} canlandı, {skipped_count} atlandı, {failed_count} hata aldı.")
        
        status = "SUCCESS"
        if failed_count > 0:  # type: ignore # pyre-ignore[58]
             status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
             
        try:
            with get_db_session() as db:
                from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
                log_scraper_execution(
                     db=db,
                     scraper_name=f"yapikredi-{self.CARD_NAME.lower()}",
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
    scraper = YapikrediCrystalScraper()
    scraper.run()
