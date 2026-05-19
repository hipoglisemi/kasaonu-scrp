


"""
Masterpass Plus Scraper
Powered by Playwright
"""

import os
import sys
import time  # type: ignore # pyre-ignore[21]
import re  # type: ignore # pyre-ignore[21]
import uuid  # type: ignore # pyre-ignore[21]
import traceback  # type: ignore # pyre-ignore[21]
import json  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from typing import Optional, Dict, Any, List  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]

# Fix sys.path to ensure src is discoverable
current_dir = os.path.dirname(os.path.abspath(__file__))
# Check if we are in src/scrapers or root
if "src" in current_dir:
    project_root = os.path.dirname(os.path.dirname(current_dir))
else:
    project_root = current_dir

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv  # type: ignore # pyre-ignore[21]
load_dotenv(os.path.join(project_root, '.env'))

from sqlalchemy import create_engine, text, func  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import sessionmaker  # type: ignore # pyre-ignore[21]

# Import unified models and database session
from src.database import engine, get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked, upsert_campaign  # type: ignore
from src.services.ai_parser_golden import parse_api_campaign  # type: ignore

# AIParser is lazy-imported in __init__ to avoid google.generativeai hang
AIParser = None

class MasterpassScraper:
    """Masterpass Plus scraper - Playwright based"""

    BASE_URL = "https://www.masterpassturkiye.com"
    CAMPAIGNS_URL = "https://www.masterpassturkiye.com/masterpassplus"
    BANK_NAME = "Mastercard"
    BANK_SLUG = "mastercard"

    def __init__(self):
        self.engine = engine
        self.db = get_db_session()
        self.card_id = None
        
        # Lazy import of AIParser
        try:
            from src.services.ai_parser import AIParser as _AIParser  # type: ignore # pyre-ignore[21]
        except ImportError as e:
            print(f"[DEBUG] AIParser import FAILED: {e}")
            raise
        self.parser = _AIParser()

        self.page = None
        self.browser = None
        self.playwright = None
        self._init_card()

    def _init_card(self):
        bank = self.db.query(Bank).filter(Bank.slug == self.BANK_SLUG).first()  # type: ignore # pyre-ignore[16]
        if not bank:
            print(f"⚠️  Masterpass not found in DB, creating...")
            bank = Bank(name=self.BANK_NAME, slug=self.BANK_SLUG)
            self.db.add(bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
        print(f"✅ Bank: {bank.name} (ID: {bank.id})")

        card = self.db.query(Card).filter(Card.slug == 'mastercard').first()  # type: ignore # pyre-ignore[16]
        if not card:
            print(f"⚠️  Card 'mastercard' not found, creating...")
            card = Card(bank_id=bank.id, name='Mastercard', slug='mastercard', is_active=True)  # type: ignore # pyre-ignore[16]
            self.db.add(card)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
        self.card_id = card.id  # type: ignore # pyre-ignore[16]
        print(f"✅ Card: {card.name} (ID: {self.card_id})")

    def _start_browser(self):
        from playwright.sync_api import sync_playwright  # type: ignore # pyre-ignore[21]
        self.playwright = sync_playwright().start()
        
        is_ci = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"
        connected = False

        if not is_ci:
            try:
                print("   🔌 Attempting to connect to local Chrome debug instance at http://localhost:9222...")
                self.browser = self.playwright.chromium.connect_over_cdp("http://localhost:9222")  # type: ignore
                connected = True
                print("   ✅ Connected to local existing Chrome instance")
                
                if len(self.browser.contexts) > 0:  # type: ignore # pyre-ignore[58]
                    context = self.browser.contexts[0]
                else:
                    context = self.browser.new_context()
                    
                self.page = context.new_page()  # type: ignore
                self.page.set_default_timeout(120000)
                return
            except Exception as e:
                pass
                
        if not connected:
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu", "--window-size=1920,1080",
                      "--disable-blink-features=AutomationControlled"]
            )
            context = self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="tr-TR",
                timezone_id="Europe/Istanbul"
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.page = context.new_page()
            self.page.set_default_timeout(120000)

    def _stop_browser(self):
        try:
            if self.page: self.page.close()  # type: ignore # pyre-ignore[16]
            if self.browser: self.browser.close()  # type: ignore # pyre-ignore[16]
            if self.playwright: self.playwright.stop()
        except Exception:
            pass

    def _fetch_campaign_urls(self, limit: Optional[int] = None) -> List[str]:  # type: ignore # pyre-ignore[16,6]
        print(f"📥 Fetching campaign list from {self.CAMPAIGNS_URL} ...")
        self.page.goto(self.CAMPAIGNS_URL, wait_until="networkidle", timeout=120000)  # type: ignore
        time.sleep(3)

        soup = BeautifulSoup(self.page.content(), "html.parser")
        
        a_tags = soup.find_all('a', href=True)
        all_links = []
        
        for a in a_tags:
            href = a['href']
            if '/masterpassplus/' in href and href != '/masterpassplus' and href != '/masterpassplus/':
                if not href.startswith('http'):
                    full_url = urljoin(self.BASE_URL, href)
                else:
                    full_url = href
                all_links.append(full_url)

        unique_urls = list(dict.fromkeys(all_links))
        if limit:
            unique_urls = unique_urls[:limit]  # type: ignore # pyre-ignore[16,6]
            
        print(f"✅ Found {len(unique_urls)} campaigns")
        return unique_urls  # type: ignore # pyre-ignore[7]

    def _extract_campaign_data(self, url: str) -> Optional[Dict[str, Any]]:  # type: ignore # pyre-ignore[16,6]
        try:
            success = False
            for attempt in range(2):
                try:
                    self.page.goto(url, wait_until="networkidle", timeout=60000)
                    time.sleep(2)
                    success = True
                    break
                except Exception as e:
                    print(f"      ⚠️ Detail load attempt {attempt+1}/2 failed: {e}. Retrying...")
                    time.sleep(3)
            
            if not success:
                print(f"      ❌ Could not load detail page: {url}")
                return None  # type: ignore # pyre-ignore[7]
                
            soup = BeautifulSoup(self.page.content(), "html.parser")
            
            # Title
            title_el = soup.find('h1')
            title = self._clean(title_el.text) if title_el else "Başlık Yok"

            # Image
            image_url = None
            imgs = soup.find_all('img')
            for img in imgs:
                src = img.get('src')
                if src and ('kampanya' in src.lower() or 'offer' in src.lower() or 'campaign' in src.lower() or 'detail' in src.lower()):
                    if not src.startswith('data:'):
                        image_url = urljoin(self.BASE_URL, src)
                        break
            
            # Content Extraction
            conditions = []
            for div in soup.find_all('div'):
                text = div.get_text(separator='\\n').strip()
                if ('Koşul' in text or len(text) > 300) and 'Anasayfa' not in text[:50] and len(text) < 10000:  # type: ignore # pyre-ignore[16,6]
                    lines = [self._clean(t) for t in text.split('\\n') if len(self._clean(t)) > 10]
                    conditions.extend(lines)
                    break # Usually there's only one main long div
            
            if not conditions:
                print("   ⚠️ Could not easily find conditions block, checking p tags")
                for p in soup.find_all('p'):
                    if len(p.text) > 20: conditions.append(self._clean(p.text))

            full_text = f"Title: {title}\\n\\n" + "\\n".join(conditions)

            return {  # type: ignore # pyre-ignore[7]
                "title": title, 
                "image_url": image_url,
                "full_text": full_text,
                "conditions": conditions, 
                "source_url": url,
            }
        except Exception as e:
            print(f"   ⚠️ Error extracting {url}: {e}")
            return None  # type: ignore # pyre-ignore[7]

    def _clean(self, text: str) -> str:
        if not text:
            return ""  # type: ignore # pyre-ignore[7]
        return re.sub(r"\s+", " ", text.replace("\n", " ").replace("\r", "")).strip()  # type: ignore # pyre-ignore[7]

    def _to_title_case(self, text: str) -> str:
        if not text: return ""
        replacements = {"I": "ı", "İ": "i"}
        lower_text = text
        for k, v in replacements.items(): lower_text = lower_text.replace(k, v)
        lower_text = lower_text.lower()
        words = lower_text.split()
        capitalized = []
        for word in words:
            if not word: continue
            if word[0] == 'i': capitalized.append('İ' + word[1:])  # type: ignore # pyre-ignore[16,6]
            elif word[0] == 'ı': capitalized.append('I' + word[1:])  # type: ignore # pyre-ignore[16,6]
            else: capitalized.append(word.capitalize())
        return " ".join(capitalized)  # type: ignore # pyre-ignore[7]

    def _get_or_create_slug(self, title: str) -> str:
        base = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
        slug = base
        counter = 1
        while self.db.query(Campaign).filter(Campaign.slug == slug).first():  # type: ignore # pyre-ignore[16]
            slug = f"{base}-{counter}"
            counter += 1  # type: ignore # pyre-ignore[58]
        return slug  # type: ignore # pyre-ignore[7]

    def _filter_conditions(self, conditions: List[str]) -> List[str]:  # type: ignore # pyre-ignore[16,6]
        blacklist = [
            "değişiklik yapma hakkı", 
            "saklı tutar", 
            "sorumlu tutulamaz", 
            "sorumluluk kabul edilmez",
            "durdurma hakkına sahiptir",
            "kullanım koşulları"
        ]
        clean = []
        for c in conditions:
            c_lower = c.lower()
            if any(b in c_lower for b in blacklist):
                continue
            clean.append(c)
        return clean  # type: ignore # pyre-ignore[7]

    def _process_campaign(self, url: str, force: bool = False) -> str:
        # --- 1. DB Check FIRST (Early Exit) ---
        if not force:
            existing = self.db.query(Campaign).filter(  # type: ignore # pyre-ignore[16]
                Campaign.tracking_url == url,
                Campaign.card_id == self.card_id
            ).first()
            if existing:
                print(f"      ⏭️  Skipped (Already exists): {existing.title}")
                return "skipped"  # type: ignore # pyre-ignore[7]

        print(f"   🔍 Processing: {url}")
        
        data = self._extract_campaign_data(url)
        if not data:
            print("      ⏭️  Skipped (Parse Error)")
            return "skipped"  # type: ignore # pyre-ignore[7]

        title = data.get("title") or "Başlıksız"
        if is_url_blocked(self.db, url):
            print(f"      🚫 Skipped (Blocklisted): {title}")
            return "skipped"  # type: ignore # pyre-ignore[7]

        try:
            # Get raw HTML directly from Playwright page (already loaded by _extract_campaign_data)
            raw_html = self.page.content()

            ai_data = parse_api_campaign(
                title=title,
                short_description=None,
                content_html=raw_html,
                bank_name="Masterpass",
                scraper_sector=None,
                tracking_url=url,
                og_title=title  # og_title fallback = title
            ) or {}
        except Exception as e:
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            print(f"      ⚠️ AI parse error: {e}")
            ai_data = {}
            
        print(f"      🧠 AI Data: {json.dumps(ai_data, ensure_ascii=False)}")

        try:
            raw_title = ai_data.get("title") or data.get("title") or ""
            formatted_title = self._to_title_case(raw_title)
            from src.utils.slug_generator import get_unique_slug
            slug = get_unique_slug(
                title=formatted_title,
                db_session=self.db,
                campaign_model=Campaign,
                tracking_url=url,
                card_name="Masterpass",
                bank_name="Masterpass"
            )
            
            ai_cat = ai_data.get("sector", "Diğer")
            sector = self.db.query(Sector).filter(Sector.slug == ai_cat).first()  # type: ignore # pyre-ignore[16]
            if not sector:
                sector = self.db.query(Sector).filter(Sector.slug == 'diger').first()  # type: ignore # pyre-ignore[16]

            start_date, end_date = None, None
            for key in ["start_date", "end_date"]:  # type: ignore # pyre-ignore[16,6]
                val = ai_data.get(key)
                if val:
                    try:
                        dt = datetime.strptime(val, "%Y-%m-%d")
                        if key == "start_date":
                            start_date = dt
                        else:
                            end_date = dt
                    except Exception:
                        pass

            conds = ai_data.get("conditions", [])
            if isinstance(conds, str):
                conds = [c.strip() for c in conds.split("\n") if c.strip()]
            part = ai_data.get("participation")
            if part:
                
                pass  # participation field written separately to DB
            conds = self._filter_conditions(conds)
            
            # Prevent empty text formatting array issues by using newlines instead of string literals
            final_conditions = "\n".join(conds) if conds else "\n".join(data["conditions"])

            cards_raw = ai_data.get("cards", [])
            if isinstance(cards_raw, str):
                cards_raw = [c.strip() for c in cards_raw.split(",") if c.strip()]
            eligible_cards_str = ", ".join(cards_raw) or "Mastercard"

            existing = self.db.query(Campaign).filter(  # type: ignore # pyre-ignore[16]
                Campaign.tracking_url == url,
                Campaign.card_id == self.card_id
            ).first()

            campaign = Campaign(
                card_id=self.card_id,
                sector_id=sector.id if sector else None,
                title=formatted_title,
                slug=slug,
                description=ai_data.get("description") or formatted_title,
                reward_text=ai_data.get("reward_text"),
                reward_value=ai_data.get("reward_value"),
                reward_type=ai_data.get("reward_type"),
                conditions=final_conditions,
                participation=part,
                eligible_cards=eligible_cards_str,
                clean_text=ai_data.get("_clean_text"),
                image_url=data.get("image_url"),
                start_date=start_date,
                end_date=end_date,
                is_active=True,
                tracking_url=url,
                created_at=func.now(),
                updated_at=func.now(),
            )
            
            # Use centralized upsert_campaign for revival and quality control
            campaign, op_status = upsert_campaign(self.db, campaign)
            self.db.commit()

            if op_status == "revived":
                print(f"      ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
                return "revived"
            elif op_status == "saved":
                 print(f"      ✅ Saved: {campaign.title[:50]}...")
                 return "saved"
            elif op_status == "updated":
                 print(f"      ✅ Updated: {campaign.title[:50]}...")
                 return "saved"
            print(f"      ✅ Saved")


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



            return "saved"  # type: ignore # pyre-ignore[7]
        except Exception as e:
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            print(f"      ❌ Save failed: {e}")
            return "error"  # type: ignore # pyre-ignore[7]

    def run(self, limit: Optional[int] = None, urls: Optional[List[str]] = None, force: bool = False):  # type: ignore # pyre-ignore[16,6]
        """Main entry point."""
        specific_urls = urls
        try:
            print("🚀 Starting Masterpass Scraper (Playwright)...")
            self._start_browser()
            
            if self.db:
                self.db.commit()  # type: ignore # pyre-ignore[16]
                # We do NOT close the DB here otherwise we can't save later
                
            urls = self._fetch_campaign_urls(limit=limit)
            
            # Filter if specific URLs provided
            if specific_urls:
                 urls = [u for u in urls if u in specific_urls]

            print(f"   🎯 Processing {len(urls)} campaigns...")
            
            success, revived, skipped, failed = 0, 0, 0, 0
            for i, url in enumerate(urls, 1):
                print(f"\n[{i}/{len(urls)}] {url}")
                try:
                    res = self._process_campaign(url, force=force)
                    if res == "saved":
                        success += 1  # type: ignore # pyre-ignore[58]
                    elif res == "revived":
                        revived += 1
                    elif res == "skipped":
                        skipped += 1  # type: ignore # pyre-ignore[58]
                    else:
                        failed += 1  # type: ignore # pyre-ignore[58]
                except Exception as e:
                    print(f"      ❌ Failed to process: {e}")
                    if self.db:
                        self.db.rollback()  # type: ignore # pyre-ignore[16]
                    failed += 1  # type: ignore # pyre-ignore[58]
                time.sleep(1)
            print(f"\n🏁 Finished. {len(urls)} found, {success} saved, {revived} revived, {skipped} skipped, {failed} errors")
            
            # Log successful or partial execution
            if self.db:
                log_scraper_execution(
                    db=self.db,
                    scraper_name="masterpass",
                    status="SUCCESS" if failed == 0 else ("PARTIAL" if success > 0 else "FAILED"),  # type: ignore # pyre-ignore[58]
                    total_found=len(urls),
                    total_saved=success,
                    total_skipped=skipped,
                    total_failed=failed,
                    total_revived=revived
                )
                
        except Exception as e:
            print(f"❌ Scraper error: {e}")
            if self.db:
                error_details = {"traceback": traceback.format_exc(), "error": str(e)}
                log_scraper_execution(
                    db=self.db,
                    scraper_name="masterpass",
                    status="FAILED",
                    error_details=error_details
                )
            raise
        finally:
            self._stop_browser()
            if self.db:
                self.db.close()  # type: ignore # pyre-ignore[16]


if __name__ == "__main__":
    import argparse  # type: ignore # pyre-ignore[21]
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit campaigns")
    parser.add_argument("--force", action="store_true", help="Force update")
    parser.add_argument("--urls", nargs='*', help="Specific URLs to scrape")
    args = parser.parse_args()
    
    scraper = MasterpassScraper()
    scraper.run(limit=args.limit, urls=args.urls, force=args.force)
