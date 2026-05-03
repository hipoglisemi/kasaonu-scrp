import os
import sys
import time
import re
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Fix sys.path for absolute imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

from sqlalchemy import func
from src.database import engine, get_db_session
from src.models import Bank, Card, Sector, Campaign, CampaignBrand
from src.services.brand_matcher import get_or_create_brands_list
from src.services.ai_parser_golden import parse_api_campaign  # type: ignore
from src.utils.scraper_utils import is_url_blocked

class HSBCScraper:
    """HSBC Premier Scraper - Playwright based"""

    BASE_URL = "https://www.hsbc.com.tr"
    LIST_URL = "https://www.hsbc.com.tr/kartlar-ve-krediler/kampanyalar/guncel-kampanyalar"
    BANK_NAME = "HSBC"

    def __init__(self):
        self.engine = engine
        self.db = get_db_session()
        
        # Lazy import of AIParser
        try:
            from src.services.ai_parser import AIParser
            print("[DEBUG] AIParser lazy-imported")
            self.parser = AIParser()
        except ImportError as e:
            print(f"❌ AIParser import failed: {e}")
            raise

        self.playwright = None
        self.browser = None
        self.page = None
        self.card_id = None
        self.brand_cache = {}
        self._init_ids()

    def _init_ids(self):
        bank = self.db.query(Bank).filter(Bank.slug == 'hsbc').first()
        if not bank:
            print("⚠️ HSBC bank not found, creating...")
            bank = Bank(name='HSBC', slug='hsbc')
            self.db.add(bank)
            self.db.commit()
        
        card = self.db.query(Card).filter(Card.slug == 'premier', Card.bank_id == bank.id).first()
        if not card:
            print("⚠️ HSBC Premier card not found, creating...")
            card = Card(bank_id=bank.id, name='Premier', slug='premier', is_active=True)
            self.db.add(card)
            self.db.commit()
        
        self.card_id = card.id
        print(f"✅ Bank: {bank.name} (ID: {bank.id}), Card: {card.name} (ID: {self.card_id})")

    def _start_browser(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        
        try:
            print("   🔌 Attempting to connect to local Chrome debug instance at http://localhost:9222...")
            self.browser = self.playwright.chromium.connect_over_cdp("http://localhost:9222")
            print("   ✅ Connected to local existing Chrome instance")
            
            if len(self.browser.contexts) > 0:
                context = self.browser.contexts[0]
            else:
                context = self.browser.new_context()
                
            self.page = context.new_page()
            self.page.set_default_timeout(60000)
            return
        except Exception as e:
            print(f"   ⚠️ Could not connect to debug Chrome, launching headless... ({e})")

        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        self.page = context.new_page()
        self.page.set_default_timeout(60000)
        print("✅ Playwright browser started (Headless fallback).")

    def _stop_browser(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        print("✅ Browser stopped.")

    def _fetch_campaign_items(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        all_items = []
        page_num = 1
        
        print(f"📥 Fetching campaign list from {self.LIST_URL}...")
        
        while True:
            url = f"{self.LIST_URL}?page={page_num}"
            print(f"   📄 Page {page_num}...")
            
            try:
                self.page.goto(url, wait_until="networkidle")
                soup = BeautifulSoup(self.page.content(), "html.parser")
                
                # Campaign items are in containers. 
                # Let's try multiple common selectors based on HSBC site structure
                items = soup.select(".campaign-list-item") or soup.select(".row.campaign-item") or soup.select(".campaign-item")
                
                if not items:
                    # Fallback to links and look for images nearby
                    links = soup.select("a.more")
                    if not links:
                        print("   ℹ️ No more campaigns found.")
                        break
                    for a in links:
                        href = a.get("href")
                        if not href: continue
                        full_url = urljoin(self.BASE_URL, href)
                        
                        # Find nearest image (usually in a sibling or parent container)
                        parent = a.find_parent()
                        img_el = None
                        target = parent
                        for _ in range(3): # Look up to 3 levels up
                            if not target: break
                            img_el = target.select_one("img")
                            if img_el: break
                            target = target.parent
                            
                        img_url = urljoin(self.BASE_URL, img_el["src"]) if img_el and img_el.get("src") else None
                        all_items.append({"url": full_url, "image_url": img_url})
                else:
                    for item in items:
                        link_el = item.select_one("a.more")
                        if not link_el: continue
                        
                        href = link_el.get("href")
                        if not href: continue
                        full_url = urljoin(self.BASE_URL, href)
                        
                        img_el = item.select_one("img")
                        img_url = urljoin(self.BASE_URL, img_el["src"]) if img_el and img_el.get("src") else None
                        
                        all_items.append({"url": full_url, "image_url": img_url})
                
                if limit and len(all_items) >= limit:
                    print(f"   ✅ Limit reached ({limit})")
                    return all_items[:limit]
                    
                page_num += 1
                if page_num > 15: break
            except Exception as e:
                print(f"   ⚠️ Error fetching page {page_num}: {e}")
                break
                
        print(f"✅ Found {len(all_items)} campaign items.")
        return all_items

    def _extract_campaign_data(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            print(f"🔍 Extracting detail: {url}")
            self.page.goto(url, wait_until="domcontentloaded")
            time.sleep(2)
            
            soup = BeautifulSoup(self.page.content(), "html.parser")
            
            title_el = soup.select_one("h1")
            title = title_el.get_text(strip=True) if title_el else "Başlık Yok"
            
            content_area = soup.select_one(".content-area") or soup.select_one("article") or soup.select_one(".content") or soup.select_one("main")
            full_text = content_area.get_text(separator="\n", strip=True) if content_area else ""
            
            # Detail page often has generic banner, so we rely on list_image_url
            image_url = None
            img_el = soup.select_one(".banner img") or soup.select_one("article img") or soup.select_one(".content img")
            if img_el and img_el.get("src"):
                image_url = urljoin(self.BASE_URL, img_el["src"])
            
            return {
                "title": title,
                "raw_html": self.page.content(),  # Return raw HTML for parse_api_campaign
                "image_url": image_url,
                "source_url": url
            }
        except Exception as e:
            print(f"   ⚠️ Extraction failed for {url}: {e}")
            return None

    def _to_title_case(self, text: Any) -> str:
        if not text: return ""
        text_str = str(text or "")
        replacements = {"I": "ı", "İ": "i"}
        lower_text = text_str
        for k, v in replacements.items(): lower_text = lower_text.replace(k, v)
        lower_text = lower_text.lower()
        words = lower_text.split()
        capitalized = []
        for word in words:
            if not word: continue
            if word[0] == 'i': capitalized.append('İ' + word[1:])
            elif word[0] == 'ı': capitalized.append('I' + word[1:])
            else: capitalized.append(word.capitalize())
        return " ".join(capitalized)

    def _get_or_create_slug(self, title: str) -> str:
        base = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        slug = base
        counter = 1
        while self.db.query(Campaign).filter(Campaign.slug == slug).first():
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    def _process_campaign(self, campaign_item: Dict[str, str], force: bool = False):
        url = campaign_item["url"]
        list_image_url = campaign_item.get("image_url")

        # 1. Existing check
        existing = self.db.query(Campaign).filter(
            Campaign.tracking_url == url, 
            Campaign.card_id == self.card_id
        ).first()
        
        if existing and not force:
            print(f"   ⏭️ Skipped (Exists): {existing.title[:40]}")
            return "skipped"
            
        # 2. Blocklist
        if is_url_blocked(self.db, url) and not force:
            print(f"   🚫 Skipped (Blocked): {url}")
            return "skipped"

        # 3. Extract
        data = self._extract_campaign_data(url)
        if not data:
            return "failed"
            
        # 4. AI Parse
        ai_data = {}
        try:
            ai_data = parse_api_campaign(
                title=data["title"],
                short_description=None,
                content_html=data.get("raw_html", ""),
                bank_name=self.BANK_NAME,
                scraper_sector=None,
                tracking_url=url,
                og_title=None
            ) or {}
        except Exception as e:
            print(f"   ⚠️ AI Parse error: {e}")

        if not ai_data or ai_data.get("_ai_failed"):
            print("   ⚠️ AI Parsing failed.")
            return "failed"

        # 5. Save
        try:
            # Combine images: Prefer list image if detail image is generic or missing
            final_image = list_image_url or data.get("image_url")
            
            formatted_title = self._to_title_case(ai_data.get("title") or data["title"])
            slug = self._get_or_create_slug(formatted_title)
            
            sector_slug = ai_data.get("sector", "diger")
            sector = self.db.query(Sector).filter(Sector.slug == sector_slug).first()
            if not sector: sector = self.db.query(Sector).filter(Sector.slug == 'diger').first()

            start_dt = None
            end_dt = None
            if ai_data.get("start_date"):
                try: start_dt = datetime.strptime(ai_data["start_date"], "%Y-%m-%d")
                except: pass
            if ai_data.get("end_date"):
                try: end_dt = datetime.strptime(ai_data["end_date"], "%Y-%m-%d")
                except: pass

            conds = "\n".join(ai_data.get("conditions", []))
            part = ai_data.get("participation")
            if part and part != "Detayları İnceleyin":
                conds = f"KATILIM: {part}\n\n{conds}"

            campaign_id = None
            if existing:
                existing.title = formatted_title
                existing.description = ai_data.get("description")
                existing.ai_marketing_text = ai_data.get("ai_marketing_text") or existing.description
                existing.reward_text = ai_data.get("reward_text")
                existing.reward_value = ai_data.get("reward_value")
                existing.reward_type = ai_data.get("reward_type")
                existing.conditions = conds
                existing.eligible_cards = ", ".join(ai_data.get("cards", []))
                existing.image_url = final_image or existing.image_url
                existing.start_date = start_dt
                existing.end_date = end_dt
                existing.sector_id = sector.id if sector else None
                existing.updated_at = func.now()
                campaign_id = existing.id
                print(f"   ✅ Updated: {existing.title[:50]}")
            else:
                camp = Campaign(
                    card_id=self.card_id,
                    sector_id=sector.id if sector else None,
                    slug=slug,
                    title=formatted_title,
                    description=ai_data.get("description"),
                    ai_marketing_text=ai_data.get("ai_marketing_text") or ai_data.get("description"),
                    reward_text=ai_data.get("reward_text"),
                    reward_value=ai_data.get("reward_value"),
                    reward_type=ai_data.get("reward_type"),
                    conditions=conds,
                    eligible_cards=", ".join(ai_data.get("cards", [])) or None,
                    image_url=final_image,
                    start_date=start_dt,
                    end_date=end_dt,
                    is_active=True,
                    tracking_url=url,
                    created_at=func.now(),
                    updated_at=func.now()
                )
                self.db.add(camp)
                self.db.flush()
                campaign_id = camp.id
                print(f"   ✅ Saved: {camp.title[:50]}")
            
            self.db.commit()
            
            # Brands matching
            brands = ai_data.get("brands", [])
            if brands:
                brand_ids = get_or_create_brands_list(
                    db=self.db,
                    names=brands,
                    brand_cache=self.brand_cache,
                    sector_id=sector.id if sector else None
                )
                for bid in brand_ids:
                    link = self.db.query(CampaignBrand).filter(
                        CampaignBrand.campaign_id == campaign_id,
                        CampaignBrand.brand_id == bid
                    ).first()
                    if not link:
                        self.db.add(CampaignBrand(campaign_id=campaign_id, brand_id=bid))
                self.db.commit()

            return "saved"
        except Exception as e:
            self.db.rollback()
            print(f"   ❌ DB error: {e}")
            traceback.print_exc()
            return "failed"

    def run(self, limit: Optional[int] = None, force: bool = False):
        try:
            print(f"🚀 Starting HSBC Scraper...")
            self._start_browser()
            items = self._fetch_campaign_items(limit=limit)
            
            success = 0
            skipped = 0
            failed = 0
            
            for i, item in enumerate(items, 1):
                print(f"\n[{i}/{len(items)}]")
                res = self._process_campaign(item, force=force)
                if res == "saved": success += 1
                elif res == "skipped": skipped += 1
                else: failed += 1
                time.sleep(1)
                
            print(f"\n🏁 Finished. Total: {len(items)}, Saved: {success}, Skipped: {skipped}, Failed: {failed}")
        except Exception as e:
            print(f"❌ Scraper crashed: {e}")
            traceback.print_exc()
        finally:
            self._stop_browser()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    
    scraper = HSBCScraper()
    scraper.run(limit=args.limit, force=args.force)
