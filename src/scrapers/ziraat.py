


import sys
import os

# Dynamic path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time  # type: ignore # pyre-ignore[21]
import re  # type: ignore # pyre-ignore[21]
import requests  # type: ignore # pyre-ignore[21]
import json  # type: ignore # pyre-ignore[21]
import traceback  # type: ignore # pyre-ignore[21]
from typing import List, Dict, Any, Optional  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import Session  # type: ignore # pyre-ignore[21]

from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked  # type: ignore
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]


class ZiraatScraper:
    BASE_URL = "https://www.bankkart.com.tr"
    LIST_URL = "https://www.bankkart.com.tr/kampanyalar"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        self.db = get_db_session()
        self.parser = AIParser()
        
        # Cache containers
        self.sector_cache: Dict[str, Sector] = {}  # type: ignore # pyre-ignore[16,6]
        self._load_cache()
        
        # Ensure Bank & Card
        self.bank = self.db.query(Bank).filter(Bank.slug == 'ziraat-bankasi').first()  # type: ignore # pyre-ignore[16]

        if not self.bank:
            self.bank = Bank(name='Ziraat Bankası', slug='ziraat-bankasi')
            self.db.add(self.bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
            
        self.card = self.db.query(Card).filter(Card.slug == 'bankkart').first()  # type: ignore # pyre-ignore[16]
        if not self.card:
             self.card = Card(bank_id=self.bank.id, name='Bankkart', slug='bankkart', is_active=True)  # type: ignore # pyre-ignore[16]
             self.db.add(self.card)  # type: ignore # pyre-ignore[16]
             self.db.commit()  # type: ignore # pyre-ignore[16]
        
        self.card_id = self.card.id  # type: ignore # pyre-ignore[16]

    def _fetch_campaign_list(self):
        print(f"📄 Fetching all campaigns via API...")
        campaigns = []
        seen_urls = set()

        # Ziraat API: indexNo=1..N, each page returns 8 items as {"Items": [...]}
        # When exhausted, API returns [] (empty JSON array, NOT a dict)
        page = 1
        consecutive_empty = 0

        while True:
            ajax_url = f"https://www.bankkart.com.tr/api/Campaigns/GetMoreShow?indexNo={page}&type=Bireysel"
            print(f"   -> Fetching API page {page}: {ajax_url}")

            try:
                resp = self.session.get(ajax_url, timeout=30)
                if resp.status_code != 200:
                    print(f"   ⚠️ API returned status {resp.status_code}, stopping.")
                    break

                try:
                    data = resp.json()
                except Exception:
                    print(f"   ⚠️ Failed to parse JSON at page {page}, stopping.")
                    break

                # API returns [] when exhausted (not a dict!)
                if isinstance(data, list):
                    print(f"   ℹ️ Empty list response at page {page} — all campaigns fetched.")
                    break

                if not isinstance(data, dict):
                    print(f"   ⚠️ Unexpected API response type: {type(data)}, stopping.")
                    break

                new_items = data.get('Items', [])

                if not new_items:
                    consecutive_empty += 1  # type: ignore # pyre-ignore[58]
                    print(f"   ℹ️ No items at page {page} (empty #{consecutive_empty}).")
                    if consecutive_empty >= 2:
                        break
                    page += 1  # type: ignore # pyre-ignore[58]
                    time.sleep(0.5)
                    continue

                consecutive_empty = 0

                for item in new_items:
                    seo_name = item.get('SeoName')
                    cat = item.get('Category', {})
                    cat_seo = cat.get('SeoName', 'diger-kampanyalar') if isinstance(cat, dict) else 'diger-kampanyalar'

                    if not seo_name:
                        continue

                    full_url = f"https://www.bankkart.com.tr/kampanyalar/{cat_seo}/{seo_name}"

                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)  # type: ignore # pyre-ignore[16]

                    img_url = urljoin(self.BASE_URL, item.get('ImageUrl')) if item.get('ImageUrl') else None

                    end_date_iso = item.get('EndDate')
                    end_date_str = None
                    if end_date_iso:
                        try:
                            dt = datetime.fromisoformat(end_date_iso)
                            end_date_str = dt.strftime("%d.%m.%Y")
                        except Exception:
                            pass

                    campaigns.append({
                        "url": full_url,
                        "image_url": img_url,
                        "list_end_date": end_date_str
                    })

                print(f"   -> Found {len(new_items)} items on page {page} (total so far: {len(campaigns)}).")
                page += 1  # type: ignore # pyre-ignore[58]
                time.sleep(0.8)

                # Safety limit: 200 pages × 8 items = 1600 campaigns max
                if page > 200:
                    print("   ⚠️ Safety limit (200 pages) reached.")
                    break

            except Exception as e:
                print(f"   ⚠️ Error on page {page}: {e}")
                break

        print(f"   ✅ Total found: {len(campaigns)} items.")
        return campaigns  # type: ignore # pyre-ignore[7]


    def _process_campaign(self, campaign_data):
        url = campaign_data['url']
        
        # Database Pre-check (Skip Logic)
        try:
            existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore # pyre-ignore[16]
            if existing:
                print(f"   ⏭️ Skipped (Already exists): {existing.title[:40]}")
                return "skipped"  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"   ⚠️ DB Pre-check error: {e}")

        print(f"🔍 Processing (AI Enabled): {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            title_el = soup.select_one('h1, .campaign-title, .title h2')
            title = title_el.get_text(strip=True) if title_el else "Kampanya Detayı"

            # Blocklist check
            from src.utils.scraper_utils import is_url_blocked  # type: ignore
            if is_url_blocked(self.db, url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"  # type: ignore # pyre-ignore[7]

            # --- ENHANCED CONTENT EXTRACTION ---
            # Ziraat puts conditions in Tabs (#tab-1, #tab-2 etc)
            # We need to explicitly fetch them
            
            main_content = soup.select_one('.subpage-detail')
            content_text = main_content.get_text(separator=' ', strip=True) if main_content else ""

            # Append Tab Contents (Conditions, Cards)
            tabs = soup.select('.tabs-content .tab-content')
            for tab in tabs:
                content_text += "\n" + tab.get_text(separator='\n', strip=True)  # type: ignore # pyre-ignore[58]

            # Fallback: specific IDs used by Ziraat
            if "Katılım Koşulları" not in content_text:
                 specific_tabs = soup.select('#tab-1, #tab-2, #tab-3, #tab-4')
                 for st in specific_tabs:
                     content_text += "\n" + st.get_text(separator='\n', strip=True)  # type: ignore # pyre-ignore[58]
            
            # -----------------------------------

            # 1. Try to get High-Res Image from Detail Page
            detail_img = None
            # Try #firstImg (Legacy scraper used this)
            img_el = soup.select_one('#firstImg')
            if not img_el:
                img_el = soup.select_one('.subpage-detail figure img')
            
            if img_el and img_el.get('src'):
                detail_img = urljoin(self.BASE_URL, img_el['src'])
            
            final_image = detail_img if detail_img else campaign_data.get('image_url')

            # 2. Inject Date Hint to AI
            date_hint = ""
            if campaign_data.get('list_end_date'):
                date_hint = f"\nİPUCU: Kampanya Bitiş Tarihi: {campaign_data['list_end_date']} (Bunu referans al, yılı buradan doğrulayabilirsin)"  # type: ignore # pyre-ignore[16,6]

            # 3. Inject Sector Hint from URL
            # URL: .../kampanyalar/market-ve-gida/...
            sector_hint = ""
            try:
                parts = url.split('/kampanyalar/')
                if len(parts) > 1:
                    category_slug = parts[1].split('/')[0]
                    sector_hint = f"\nİPUCU: Kampanya Kategorisi Linkte '{category_slug}' olarak geçiyor. Buna uygun Sektör seç."
            except: pass

            # AI PARSING
            ai_data = self.parser.parse_campaign_data(
                raw_text=content_text + date_hint + sector_hint, # Use ENHANCED content + HINTS
                bank_name="ziraat"
            )
            
            if not ai_data:
                print("   ❌ AI Parsing failed.")
                return "error"  # type: ignore # pyre-ignore[7]

            title = ai_data.get("title", "Kampanya")
            desc = ai_data.get("description", "")
            
            # Map Sector via AI Slug
            ai_sector_slug = ai_data.get("sector")
            sector = self._get_sector(ai_sector_slug)
            
            # Slug
            base_slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
            slug = base_slug
            counter = 1
            while self.db.query(Campaign).filter(Campaign.slug == slug).first():  # type: ignore # pyre-ignore[16]
                slug = f"{base_slug}-{counter}"
                counter += 1  # type: ignore # pyre-ignore[58]

            # Conditions & Participation
            conds = ai_data.get("conditions", [])
            if isinstance(conds, str):
                conds = [c.strip() for c in conds.split("\n") if c.strip()]
            part_method = ai_data.get("participation")
            if part_method and "Detayları İnceleyin" not in part_method:
                conds.insert(0, f"KATILIM: {part_method}")
            final_conditions = "\n".join(conds)

            cards_raw = ai_data.get("cards", [])
            if isinstance(cards_raw, str):
                cards_raw = [c.strip() for c in cards_raw.split(",") if c.strip()]

            # Dates
            vf = None
            vu = None
            # Tey safe parsing from AI
            if ai_data.get("start_date"):
                try: vf = datetime.strptime(ai_data.get("start_date"), "%Y-%m-%d")
                except: pass
            if ai_data.get("end_date"):
                try: vu = datetime.strptime(ai_data.get("end_date"), "%Y-%m-%d")
                except: pass
            
            # Fallback for End Date from list page if AI missed it
            if not vu and campaign_data['list_end_date']:  # type: ignore # pyre-ignore[16,6]
                try:
                    # "Son Gün 28.2.2026"
                    clean_date = campaign_data['list_end_date'].replace("Son Gün", "").strip()
                    vu = datetime.strptime(clean_date, "%d.%m.%Y")
                except: pass

            # DB Upsert
            existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore # pyre-ignore[16]
            if existing:
                print(f"   ⏭️ Skipped (Already exists, preserving manual edits): {title[:50]}...")  # type: ignore # pyre-ignore[16,6]
                return "skipped"  # type: ignore # pyre-ignore[7]

            campaign = Campaign(
                card_id=self.card_id,
                sector_id=sector.id if sector else None,  # type: ignore # pyre-ignore[16]
                slug=slug,
                title=title,
                description=desc,
                reward_text=ai_data.get("reward_text"),
                reward_value=ai_data.get("reward_value"),
                conditions=final_conditions,
                eligible_cards=", ".join(cards_raw),
                image_url=final_image,
                start_date=vf,
                end_date=vu,
                is_active=True,
                tracking_url=url,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(campaign)  # type: ignore # pyre-ignore[16]
            
            self.db.commit()  # type: ignore # pyre-ignore[16]

            # BRANDS
            from src.services.brand_matcher import get_or_create_brands_list
            brand_ids = get_or_create_brands_list(
                self.db,
                ai_data.get("brands", []),
                getattr(self, 'brand_cache', {}),
                sector.id if sector else None
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
            print(f"   ✅ Saved: {title} | End: {vu}")
            return "saved"  # type: ignore # pyre-ignore[7]
            
        except Exception as e:
            print(f"   ❌ Error processing {url}: {e}")
            if self.db: self.db.rollback()  # type: ignore # pyre-ignore[16]
            traceback.print_exc()
            return "error"  # type: ignore # pyre-ignore[7]

    def run(self):
        print("🚀 Starting Ziraat Bank Scraper...")
        campaigns = self._fetch_campaign_list()
        
        # Check environment limit
        max_campaigns = os.environ.get("MAX_CAMPAIGNS_PER_RUN")
        limit = int(max_campaigns) if max_campaigns else 999
        
        count = 0
        success_count = 0
        skipped_count = 0
        failed_count = 0
        error_details = []

        for camp in campaigns:
            if count >= limit:
                print(f"🛑 Reached MAX_CAMPAIGNS_PER_RUN limit ({limit})")
                break
            
            try:
                res = self._process_campaign(camp)
                if res == "saved": success_count += 1  # type: ignore # pyre-ignore[58]
                elif res == "skipped": skipped_count += 1  # type: ignore # pyre-ignore[58]
                else: 
                    failed_count += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": camp.get('url', 'unknown'), "error": "Unknown DB failure"})
            except Exception as e:
                failed_count += 1  # type: ignore # pyre-ignore[58]
                error_details.append({"url": camp.get('url', 'unknown'), "error": str(e)})
            
            count += 1  # type: ignore # pyre-ignore[58]
            time.sleep(2)
        print(f"✅ Özet: {len(campaigns)} bulundu, {success_count} eklendi, {skipped_count} atlandı, {failed_count} hata aldı.")
        
        status = "SUCCESS"
        if failed_count > 0:  # type: ignore # pyre-ignore[58]
             status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
             
        try:
            from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
            log_scraper_execution(
                 db=self.db,
                 scraper_name="ziraat",
                 status=status,
                 total_found=len(campaigns),
                 total_saved=success_count,
                 total_skipped=skipped_count,
                 total_failed=failed_count,
                 error_details={"errors": error_details} if error_details else None
            )
        except Exception as le:
             print(f"⚠️ Could not save scraper log: {le}")
             
        print("🏁 Finished.")


    def _load_cache(self):
        """Load sectors into cache for fast lookup"""
        for s in self.db.query(Sector).all():  # type: ignore # pyre-ignore[16]
            self.sector_cache[s.slug] = s
            self.sector_cache[s.name.lower()] = s

    def _get_sector(self, slug: str) -> Optional[Sector]:  # type: ignore # pyre-ignore[16,6]
        if not slug:
            return self.sector_cache.get("diger")  # type: ignore # pyre-ignore[7]
        return self.sector_cache.get(slug.lower()) or self.sector_cache.get("diger")  # type: ignore # pyre-ignore[7]

if __name__ == "__main__":
    try:
        scraper = ZiraatScraper()
        scraper.run()
    finally:
        if hasattr(scraper, 'db') and scraper.db:
            scraper.db.close()  # type: ignore # pyre-ignore[16]
