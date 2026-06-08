import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time  # type: ignore # pyre-ignore[21]
import requests  # type: ignore # pyre-ignore[21]
import traceback  # type: ignore # pyre-ignore[21]
from typing import Dict, Optional  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]

from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Bank, Card, Sector, Campaign, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked, upsert_campaign  # type: ignore
from src.services.brand_matcher import get_or_create_brands_list  # type: ignore

class ZiraatKatilimScraper:
    BASE_URL = "https://www.ziraatkatilim.com.tr"
    LIST_URL = "https://www.ziraatkatilim.com.tr/kart-kampanyalari"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        self.db = get_db_session()
        
        self.sector_cache: Dict[str, Sector] = {}  # type: ignore # pyre-ignore[16,6]
        self._load_cache()
        
        self.bank = self.db.query(Bank).filter(Bank.slug == 'ziraat-katilim').first()  # type: ignore # pyre-ignore[16]
        if not self.bank:
            self.bank = Bank(name='Ziraat Katılım', slug='ziraat-katilim')
            self.db.add(self.bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
            
        self.card = self.db.query(Card).filter(Card.slug == 'katilim-bankkart').first()  # type: ignore # pyre-ignore[16]
        if not self.card:
             self.card = Card(bank_id=self.bank.id, name='Katılım Bankkart', slug='katilim-bankkart', is_active=True)  # type: ignore # pyre-ignore[16]
             self.db.add(self.card)  # type: ignore # pyre-ignore[16]
             self.db.commit()  # type: ignore # pyre-ignore[16]
        
        self.card_id = self.card.id  # type: ignore # pyre-ignore[16]

    def _fetch_campaign_list(self):
        print(f"📄 Fetching Ziraat Katılım campaigns from HTML...")
        campaigns = []
        try:
            resp = self.session.get(self.LIST_URL, timeout=30)
            soup = BeautifulSoup(resp.text, 'html.parser')
            seen = set()
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('/kart-kampanyalari/') and '?' not in href:
                    full_url = urljoin(self.BASE_URL, href)
                    if full_url not in seen:
                        seen.add(full_url)
                        campaigns.append({"url": full_url})
            print(f"   ✅ Total found: {len(campaigns)} items.")
        except Exception as e:
            print(f"   ⚠️ Error fetching list: {e}")
        return campaigns

    def _process_campaign(self, campaign_data):
        url = campaign_data['url']
        
        try:
            existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore # pyre-ignore[16]
            if existing and existing.is_active and existing.is_approved:
                print(f"   ⏭️ Skipped (Already exists and active): {existing.title[:40]}")
                return "skipped"  # type: ignore # pyre-ignore[7]
        except Exception as e:
            pass

        print(f"🔍 Processing (AI Enabled): {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            title_el = soup.select_one('h1')
            title = title_el.get_text(strip=True) if title_el else "Kampanya"

            if is_url_blocked(self.db, url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"  # type: ignore # pyre-ignore[7]

            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else str(soup)

            detail_img = None
            cover_img_el = soup.select_one('.cover-image img')
            if cover_img_el and cover_img_el.get('src'):
                detail_img = urljoin(self.BASE_URL, cover_img_el['src'])
            else:
                for img in soup.select('img'):
                    src = img.get('src', '')
                    if 'kampanya' in src.lower() or 'banner' in src.lower():
                        detail_img = urljoin(self.BASE_URL, src)
                        break
            
            final_image = detail_img

            from src.services.ai_parser import parse_api_campaign  # type: ignore
            ai_data = parse_api_campaign(
                title=title,
                short_description=title,
                content_html=raw_html,
                bank_name="Ziraat Katılım",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            )
            
            if not ai_data:
                print("   ❌ AI Parsing failed.")
                return "error"  # type: ignore # pyre-ignore[7]

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
                card_name="Katılım Bankkart",
                bank_name="Ziraat Katılım"
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
                sector_id=sector.id if sector else None,  # type: ignore # pyre-ignore[16]
                slug=slug,
                title=title,
                description=desc,
                ai_marketing_text=ai_data.get("ai_marketing_text"),
                reward_text=ai_data.get("reward_text"),
                reward_value=ai_data.get("reward_value"),
                conditions=final_conditions,
                eligible_cards=", ".join(cards_raw),
                participation=part_method,
                image_url=final_image,
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
            return op_status  # type: ignore # pyre-ignore[7]
            
        except Exception as e:
            print(f"   ❌ Error processing {url}: {e}")
            if self.db: self.db.rollback()  # type: ignore # pyre-ignore[16]
            traceback.print_exc()
            return "error"  # type: ignore # pyre-ignore[7]

    def run(self):
        print("🚀 Starting Ziraat Katılım Scraper...")
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
                if res == "saved": success_count += 1  # type: ignore # pyre-ignore[58]
                elif res == "revived": total_revived += 1
                elif res == "skipped": skipped_count += 1  # type: ignore # pyre-ignore[58]
                else: 
                    failed_count += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": camp.get('url', 'unknown'), "error": f"Process returned {res}"})
            except Exception as e:
                failed_count += 1  # type: ignore # pyre-ignore[58]
                error_details.append({"url": camp.get('url', 'unknown'), "error": str(e)})
            
            count += 1  # type: ignore # pyre-ignore[58]
            time.sleep(1)
            
        print(f"✅ Özet: {len(campaigns)} bulundu, {success_count} eklendi, {total_revived} canlandı, {skipped_count} atlandı, {failed_count} hata aldı.")
        
        status = "SUCCESS"
        if failed_count > 0:  # type: ignore # pyre-ignore[58]
             status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
             
        try:
            from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
            log_scraper_execution(
                 db=self.db,
                 scraper_name="ziraat_katilim",
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
        for s in self.db.query(Sector).all():  # type: ignore # pyre-ignore[16]
            self.sector_cache[s.slug] = s
            self.sector_cache[s.name.lower()] = s

    def _get_sector(self, slug: str) -> Optional[Sector]:  # type: ignore # pyre-ignore[16,6]
        if not slug:
            return self.sector_cache.get("diger")  # type: ignore # pyre-ignore[7]
        return self.sector_cache.get(slug.lower()) or self.sector_cache.get("diger")  # type: ignore # pyre-ignore[7]

if __name__ == "__main__":
    try:
        scraper = ZiraatKatilimScraper()
        scraper.run()
    finally:
        if hasattr(scraper, 'db') and scraper.db:
            scraper.db.close()  # type: ignore # pyre-ignore[16]
