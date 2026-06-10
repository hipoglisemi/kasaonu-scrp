import sys
import os
import re
import time
import traceback
from typing import Dict, Optional, List, Any
from urllib.parse import urljoin
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import requests
from bs4 import BeautifulSoup
from src.database import get_db_session
from src.models import Bank, Card, Sector, Campaign, CampaignBrand
from src.utils.scraper_utils import is_url_blocked, upsert_campaign
from src.services.brand_matcher import get_or_create_brands_list

class AnadolubankScraper:
    BASE_URL = "https://www.anadolubank.com.tr"
    LIST_URL = "https://www.anadolubank.com.tr/kampanyalar"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        self.db = get_db_session()
        
        self.sector_cache: Dict[str, Sector] = {}
        self._load_cache()
        
        self.bank = self.db.query(Bank).filter(Bank.slug == 'anadolubank').first()
        if not self.bank:
            self.bank = Bank(name='Anadolubank', slug='anadolubank', logo_url='/logos/banks/anadolubank.png', is_active=True)
            self.db.add(self.bank)
            self.db.commit()
            
        self.card = self.db.query(Card).filter(Card.slug == 'anadolubank-kredi-karti').first()
        if not self.card:
             self.card = Card(
                 bank_id=self.bank.id, 
                 name='Kredi Kartı', 
                 slug='anadolubank-kredi-karti', 
                 logo_url='/logos/cards/anadolubank.png',
                 is_active=True
             )
             self.db.add(self.card)
             self.db.commit()
        
        self.card_id = self.card.id

    def _fetch_campaign_list(self) -> List[Dict[str, Any]]:
        print(f"📄 Fetching Anadolubank campaigns from {self.LIST_URL}...")
        campaigns = []
        seen = set()
        
        try:
            resp = self.session.get(self.LIST_URL, timeout=30)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Find all links to detail pages
            links = soup.select('a')
            for a in links:
                href = a.get('href')
                if href and ('/kampanyalar/' in href.lower() or '/kampanya/' in href.lower()) and href != '/kampanyalar':
                    full_url = urljoin(self.BASE_URL, href)
                    if full_url not in seen:
                        seen.add(full_url)
                        campaigns.append({"url": full_url})
                        
        except Exception as e:
            print(f"   ⚠️ Error fetching list from {self.LIST_URL}: {e}")
                
        print(f"   ✅ Total unique campaigns found: {len(campaigns)}")
        return campaigns

    def _process_campaign(self, campaign_data):
        url = campaign_data['url']
        
        try:
            existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()
            if existing and existing.is_active and existing.is_approved:
                print(f"   ⏭️ Skipped (Already exists and active): {existing.title[:40]}")
                return "skipped"
        except Exception as e:
            pass

        print(f"🔍 Processing (AI Enabled): {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            title_el = soup.select_one('h1') or soup.select_one('h2')
            title = title_el.get_text(strip=True) if title_el else "Kampanya"

            if is_url_blocked(self.db, url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"

            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            body_el = soup.select_one('.campaign_detail') or soup.find("body")
            raw_html = str(body_el) if body_el else str(soup)

            detail_img = None
            
            # Look for an image inside the page
            for img in soup.select('img'):
                src = img.get('src', '')
                if 'assets.anadolubank.com.tr/duyuru-panel/' in src or '_detail' in src:
                    detail_img = urljoin(self.BASE_URL, src)
                    break

            # Fallback to OG image
            if not detail_img:
                og_img = soup.find("meta", property="og:image")
                if og_img and og_img.get("content") and "favicon" not in og_img.get("content").lower() and "logo" not in og_img.get("content").lower():
                    detail_img = og_img.get("content")

            from src.services.ai_parser_golden import parse_api_campaign
            ai_data = parse_api_campaign(
                title=title,
                short_description=title,
                content_html=raw_html,
                bank_name="Anadolubank",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            )
            
            if not ai_data or ai_data.get("_ai_failed"):
                print("   ❌ AI Parsing failed.")
                return "error"

            title = ai_data.get("title", "Kampanya")
            desc = ai_data.get("description", "")
            
            sector_slug = ai_data.get("sector")
            sector = self._get_sector(sector_slug)
            
            from src.utils.slug_generator import get_unique_slug
            slug = get_unique_slug(
                title=title,
                db_session=self.db,
                campaign_model=Campaign,
                tracking_url=url,
                card_name="Kredi Kartı",
                bank_name="Anadolubank"
            )

            conds = ai_data.get("conditions", [])
            if isinstance(conds, str):
                conds = [c.strip() for c in conds.split("\n") if c.strip()]
            part_method = ai_data.get("participation")
            final_conditions = "\n".join(conds)

            cards_raw = ai_data.get("cards", [])
            if isinstance(cards_raw, str):
                cards_raw = [c.strip() for c in cards_raw.split(",") if c.strip()]

            vf = None
            vu = None
            if ai_data.get("start_date"):
                try: vf = datetime.strptime(ai_data.get("start_date"), "%Y-%m-%d")
                except: pass
            if ai_data.get("end_date"):
                try: vu = datetime.strptime(ai_data.get("end_date"), "%Y-%m-%d")
                except: pass

            campaign = Campaign(
                card_id=self.card_id,
                sector_id=sector.id if sector else None,
                slug=slug,
                title=title,
                description=desc,
                ai_marketing_text=ai_data.get("ai_marketing_text"),
                reward_text=ai_data.get("reward_text"),
                reward_value=ai_data.get("reward_value"),
                reward_type=ai_data.get("reward_type"),
                conditions=final_conditions,
                eligible_cards=", ".join(cards_raw),
                participation=part_method,
                image_url=detail_img,
                start_date=vf,
                end_date=vu,
                clean_text=ai_data.get("_clean_text"),
                is_active=True,
                tracking_url=url,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            campaign, op_status = upsert_campaign(self.db, campaign)
            self.db.commit()
            
            if op_status == "revived":
                print(f"   ♻️  Revived: {campaign.title}")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title}")
            
            self.db.refresh(campaign)

            brand_ids = get_or_create_brands_list(
                db=self.db,
                names=ai_data.get("brands", []),
                brand_cache=getattr(self, 'brand_cache', {}),
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
            return op_status
            
        except Exception as e:
            print(f"   ❌ Error processing {url}: {e}")
            if self.db: self.db.rollback()
            traceback.print_exc()
            return "error"

    def run(self):
        print("🚀 Starting Anadolubank Scraper...")
        campaigns = self._fetch_campaign_list()
        
        max_campaigns = os.environ.get("MAX_CAMPAIGNS_PER_RUN")
        limit = int(max_campaigns) if max_campaigns else 999
        
        count = 0
        success_count = 0
        total_revived = 0
        skipped_count = 0
        failed_count = 0
        error_details = []

        for camp in campaigns:
            if count >= limit:
                print(f"🛑 Reached MAX limit ({limit})")
                break
            
            try:
                res = self._process_campaign(camp)
                if res == "saved": success_count += 1
                elif res == "revived": total_revived += 1
                elif res == "skipped": skipped_count += 1
                else: 
                    failed_count += 1
                    error_details.append({"url": camp.get('url', 'unknown'), "error": f"Process returned {res}"})
            except Exception as e:
                failed_count += 1
                error_details.append({"url": camp.get('url', 'unknown'), "error": str(e)})
            
            count += 1
            time.sleep(1)
            
        print(f"✅ Özet: {len(campaigns)} bulundu, {success_count} eklendi, {total_revived} canlandı, {skipped_count} atlandı, {failed_count} hata aldı.")
        
        status = "SUCCESS"
        if failed_count > 0:
             status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"
             
        try:
            from src.utils.logger_utils import log_scraper_execution
            log_scraper_execution(
                 db=self.db,
                 scraper_name="anadolubank",
                 status=status,
                 total_found=len(campaigns),
                 total_saved=success_count,
                 total_skipped=skipped_count,
                 total_failed=failed_count,
                 total_revived=total_revived,
                 error_details={"errors": error_details} if error_details else None
            )
        except Exception as le:
             print(f"⚠️ Could not save scraper log: {le}")
             
        print("🏁 Finished.")

    def _load_cache(self):
        for s in self.db.query(Sector).all():
            self.sector_cache[s.slug] = s
            self.sector_cache[s.name.lower()] = s

    def _get_sector(self, slug: str) -> Optional[Sector]:
        if not slug:
            return self.sector_cache.get("diger")
        return self.sector_cache.get(slug.lower()) or self.sector_cache.get("diger")

if __name__ == "__main__":
    try:
        scraper = AnadolubankScraper()
        scraper.run()
    finally:
        if hasattr(scraper, 'db') and scraper.db:
            scraper.db.close()
