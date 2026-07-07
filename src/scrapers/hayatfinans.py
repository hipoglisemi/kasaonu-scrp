import sys
import os
import re
import time
import requests
import json
import traceback
from typing import Dict, Optional, List, Any
from urllib.parse import urljoin
from datetime import datetime
from bs4 import BeautifulSoup

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Bank, Card, Sector, Campaign, CampaignBrand
from src.utils.scraper_utils import is_url_blocked, upsert_campaign
from src.services.brand_matcher import get_or_create_brands_list

class HayatFinansScraper:
    BASE_URL = "https://hayatfinans.com.tr"
    LIST_URL = "https://hayatfinans.com.tr/kampanyalar"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        self.db = get_db_session()
        
        self.sector_cache: Dict[str, Sector] = {}
        self.brand_cache: Dict[str, Any] = {}
        self._load_cache()
        
        # Get or create Hayat Finans bank
        self.bank = self.db.query(Bank).filter(Bank.slug == 'hayat-finans').first()
        if not self.bank:
            self.bank = Bank(
                name='Hayat Finans', 
                slug='hayat-finans', 
                logo_url='/logos/banks/hayatfinans.webp', 
                is_active=True
            )
            self.db.add(self.bank)
            self.db.commit()
             
        # Get or create Hayat Finans card
        self.card = self.db.query(Card).filter(Card.slug == 'hayat-finans').first()
        if not self.card:
             self.card = Card(
                 bank_id=self.bank.id, 
                 name='Hayat Finans', 
                 slug='hayat-finans', 
                 logo_url='/logos/cards/hayatfinans.webp',
                 is_active=True
             )
             self.db.add(self.card)
             self.db.commit()

    def _parse_next_data(self, html_content: str) -> Optional[Dict[str, Any]]:
        """Parse the next data script tag on the page."""
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup.find_all('script'):
            text = script.string
            if text and 'props' in text and 'pageProps' in text:
                try:
                    return json.loads(text.strip())
                except Exception as e:
                    print("   ⚠️ JSON parse error on script tag:", e)
        return None

    def _fetch_campaign_list(self) -> List[Dict[str, Any]]:
        print(f"📄 Fetching Hayat Finans campaigns from {self.LIST_URL}...")
        campaigns = []
        
        try:
            resp = self.session.get(self.LIST_URL, timeout=30)
            data = self._parse_next_data(resp.text)
            if not data:
                print("   ❌ Failed to extract NEXT data from page.")
                return []
                
            props = data.get('props', {}).get('pageProps', {}).get('data', {})
            components = props.get('components', [])
            
            child_list = []
            for comp in components:
                if isinstance(comp, dict) and 'child' in comp:
                    child = comp.get('child', [])
                    if len(child) > 0 and isinstance(child[0], dict) and 'href' in child[0]:
                        child_list = child
                        break
            
            print(f"   Found {len(child_list)} campaign elements in page components.")
            for item in child_list:
                href = item.get('href')
                if href:
                    # Make relative URLs absolute
                    if not href.startswith('http'):
                        href = urljoin(self.BASE_URL, href)
                    
                    img_data = item.get('img')
                    img_url = None
                    if isinstance(img_data, dict):
                        img_url = img_data.get('url')
                    elif isinstance(img_data, str):
                        img_url = img_data
                        
                    campaigns.append({
                        "url": href,
                        "title": item.get('title'),
                        "image": img_url
                    })
                    
        except Exception as e:
            print(f"   ⚠️ Error fetching campaign list: {e}")
            traceback.print_exc()
            
        print(f"   ✅ Total campaigns parsed: {len(campaigns)}")
        return campaigns

    def _process_campaign(self, campaign_data: Dict[str, Any]) -> str:
        url = campaign_data['url']
        card_id = self.card.id
        card_name = self.card.name

        try:
            existing = self.db.query(Campaign).filter(
                Campaign.tracking_url == url,
                Campaign.card_id == card_id
            ).first()
            if existing and existing.is_active and existing.is_approved:
                print(f"   ⏭️ Skipped (Already exists and active): {existing.title[:40]}")
                return "skipped"
        except Exception:
            pass

        print(f"🔍 Processing ({card_name}): {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')

            title_el = soup.select_one('h1')
            title = title_el.get_text(strip=True) if title_el else campaign_data.get('title', 'Kampanya')

            if is_url_blocked(self.db, url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"

            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            # Content is stored inside main layout wrapper
            content_el = soup.find('main')
            raw_html = str(content_el) if content_el else str(soup.find("body"))

            detail_img = campaign_data.get('image')
            if not detail_img:
                og_img = soup.find("meta", property="og:image")
                if og_img and og_img.get("content") and "favicon" not in og_img.get("content").lower() and "logo" not in og_img.get("content").lower():
                    detail_img = og_img.get("content")

            from src.services.ai_parser_golden import parse_api_campaign
            ai_data = parse_api_campaign(
                title=title,
                short_description=title,
                content_html=raw_html,
                bank_name="Hayat Finans",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            )
            
            if not ai_data or ai_data.get("_ai_failed"):
                print("   ❌ AI Parsing failed.")
                return "error"

            title = ai_data.get("title", title)
            desc = ai_data.get("description", "")
            
            sector_slug = ai_data.get("sector")
            sector = self._get_sector(sector_slug)
            
            from src.utils.slug_generator import get_unique_slug
            slug = get_unique_slug(
                title=title,
                db_session=self.db,
                campaign_model=Campaign,
                tracking_url=url,
                card_name=card_name,
                bank_name="Hayat Finans"
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
                card_id=card_id,
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
                except Exception:
                    self.db.rollback()
            return op_status
            
        except Exception as e:
            print(f"   ❌ Error processing {url}: {e}")
            self.db.rollback()
            traceback.print_exc()
            return "error"

    def run(self):
        print("🚀 Starting Hayat Finans Scraper...")
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
                 scraper_name="hayatfinans",
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
        scraper = HayatFinansScraper()
        scraper.run()
    finally:
        if hasattr(scraper, 'db') and scraper.db:
            scraper.db.close()
