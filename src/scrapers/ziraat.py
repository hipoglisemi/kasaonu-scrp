


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
from src.utils.scraper_utils import is_url_blocked, upsert_campaign  # type: ignore
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
from src.services.brand_matcher import get_or_create_brands_list  # type: ignore


class ZiraatScraper:
    BASE_URL = "https://www.bankkart.com.tr"
    LIST_URL = "https://www.bankkart.com.tr/kampanyalar"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        
        # Geoblock bypass: Find a working TR proxy if direct connection fails
        proxy_url = self._find_working_tr_proxy()
        if proxy_url:
            self.session.proxies.update({
                "http": proxy_url,
                "https": proxy_url
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
        self.db.commit()  # Release connection to the pool

    def _find_working_tr_proxy(self) -> Optional[str]:
        print("   🔍 Testing direct connection to Ziraat first...")
        try:
            resp = self.session.get("https://www.bankkart.com.tr", timeout=10)
            if resp.status_code == 200:
                print("   ✅ Direct connection works! No proxy needed.")
                return None
        except Exception as e:
            print(f"   ⚠️ Direct connection failed (might be geoblocked): {e}")

        print("   🌐 Fetching TR proxy list from proxyscrape...")
        proxy_list_url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=TR&ssl=all&anonymity=all"
        try:
            r = requests.get(proxy_list_url, timeout=10)
            proxies = [p.strip() for p in r.text.strip().split("\n") if p.strip()]
            print(f"   📋 Found {len(proxies)} TR proxies. Testing them...")
        except Exception as pe:
            print(f"   ❌ Failed to fetch proxy list: {pe}")
            return None

        for proxy in proxies[:15]:  # Test first 15 proxies
            proxy_url = f"http://{proxy}"
            proxies_dict = {"http": proxy_url, "https": proxy_url}
            try:
                print(f"      Testing proxy: {proxy} ...")
                test_resp = requests.get("https://www.bankkart.com.tr", headers=self.session.headers, proxies=proxies_dict, timeout=5)
                if test_resp.status_code == 200:
                    print(f"      ✅ Found working TR proxy: {proxy}")
                    return proxy_url
            except Exception:
                pass
        
        print("   ❌ No working TR proxy found from the list.")
        return None

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
            if existing and existing.is_active and existing.is_approved:
                print(f"   ⏭️ Skipped (Already exists and active): {existing.title[:40]}")
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

            # Extract og:title for better cleaning anchors
            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            # Extract FULL BODY for Autofix-standard global cleaning
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else str(soup)

            # 1. Try to get High-Res Image from Detail Page
            detail_img = None
            img_el = soup.select_one('#firstImg')
            if not img_el:
                img_el = soup.select_one('.subpage-detail figure img')
            
            if img_el and img_el.get('src'):
                detail_img = urljoin(self.BASE_URL, img_el['src'])
            
            final_image = detail_img if detail_img else campaign_data.get('image_url')
            
            # Restore sector hint from URL (Ziraat URLs contain category: .../kampanyalar/market-ve-gida/...)
            sector_hint = ""
            try:
                parts = url.split('/kampanyalar/')
                if len(parts) > 1:
                    category_slug = parts[1].split('/')[0]
                    sector_hint = f"İPUCU: Kampanya Kategorisi URL'de '{category_slug}' olarak geçiyor."
            except Exception:
                pass

            # Restore date hint (Ziraat list page has end_date, detail page often doesn't)
            date_hint = ""
            if campaign_data.get('list_end_date'):
                date_hint = f"İPUCU: Kampanya Bitiş Tarihi: {campaign_data['list_end_date']}"

            hints = "\n".join(filter(None, [date_hint, sector_hint]))

            # AI PARSING (Autofix-standard)
            from src.services.ai_parser import parse_api_campaign  # type: ignore
            ai_data = parse_api_campaign(
                title=title,
                short_description=hints or title,  # hints act as AI context
                content_html=raw_html,
                bank_name="Ziraat Bankası",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
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
            from src.utils.slug_generator import get_unique_slug
            slug = get_unique_slug(
                title=title,
                db_session=self.db,
                campaign_model=Campaign,
                tracking_url=url,
                card_name="Bankkart",
                bank_name="Ziraat Bankası"
            )

            # Conditions & Participation
            conds = ai_data.get("conditions", [])
            if isinstance(conds, str):
                conds = [c.strip() for c in conds.split("\n") if c.strip()]
            part_method = ai_data.get("participation")
            if part_method and "Detayları İnceleyin" not in part_method:
                pass  # participation field written separately to DB
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
            
            # Use centralized upsert_campaign for revival and quality control
            campaign, op_status = upsert_campaign(self.db, campaign)
            self.db.commit()
            
            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title}")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title} | End: {vu}")
            
            self.db.refresh(campaign)

            # Brands via brand_matcher
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
                    print(f"   ⚠️ CampaignBrand link failed: {e}")
            return op_status  # type: ignore # pyre-ignore[7]
            
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
        total_revived = 0
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
                elif res == "revived": total_revived += 1
                elif res == "skipped": skipped_count += 1  # type: ignore # pyre-ignore[58]
                else: 
                    failed_count += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": camp.get('url', 'unknown'), "error": f"Process returned {res}"})
            except Exception as e:
                failed_count += 1  # type: ignore # pyre-ignore[58]
                error_details.append({"url": camp.get('url', 'unknown'), "error": str(e)})
            
            count += 1  # type: ignore # pyre-ignore[58]
            time.sleep(2)
        print(f"✅ Özet: {len(campaigns)} bulundu, {success_count} eklendi, {total_revived} canlandı, {skipped_count} atlandı, {failed_count} hata aldı.")
        
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
                 total_revived=total_revived,
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
