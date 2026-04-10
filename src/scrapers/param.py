


"""
ParamKart Scraper
Powered by Playwright (Handles Lazy Loading via Scrolling)
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
from src.utils.scraper_utils import is_url_blocked  # type: ignore

# AIParser is lazy-imported in __init__ to avoid google.generativeai hang
AIParser = None


SECTOR_MAP = {
    "Market & Gıda": "Market", "Giyim & Aksesuar": "Giyim",
    "Restoran & Kafe": "Restoran & Kafe", "Seyahat": "Seyahat",
    "Turizm & Konaklama": "Seyahat", "Elektronik": "Elektronik",
    "Mobilya & Dekorasyon": "Mobilya & Dekorasyon",
    "Kozmetik & Sağlık": "Kozmetik & Sağlık", "E-Ticaret": "E-Ticaret",
    "Otomotiv": "Otomotiv", "Sigorta": "Sigorta", "Eğitim": "Eğitim",
    "Kültür, Sanat & Spor": "Kültür, Sanat & Spor", "Eğlence": "Kültür, Sanat & Spor",
    "Diğer": "Diğer",
}

class ParamScraper:
    """Param scraper - Playwright based (Handles infinite scroll on list and details)"""

    BASE_URL = "https://param.com.tr"
    CAMPAIGNS_URL = "https://param.com.tr/tum-avantajlar"
    BANK_NAME = "Param"
    BANK_SLUG = "param"

    def __init__(self):
        self.engine = engine
        self.db = get_db_session()
        self.card_id = None
        
        # Lazy import of AIParser
        try:
            from src.services.ai_parser import AIParser as _AIParser  # type: ignore # pyre-ignore[21]
        except ImportError:
            from services.ai_parser import AIParser as _AIParser  # type: ignore # pyre-ignore[21]
        self.parser = _AIParser()

        self.page = None
        self.browser = None
        self.playwright = None
        self._init_card()

    def _init_card(self):
        bank = self.db.query(Bank).filter(Bank.slug == self.BANK_SLUG).first()  # type: ignore # pyre-ignore[16]
        if not bank:
            print(f"⚠️  Param not found in DB, creating...")
            # We don't have a guaranteed stable logo for param right now, but we can set a basic one if needed
            bank = Bank(name=self.BANK_NAME, slug=self.BANK_SLUG)
            self.db.add(bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
        print(f"✅ Bank: {bank.name} (ID: {bank.id})")

        card = self.db.query(Card).filter(Card.slug == 'paramkart').first()  # type: ignore # pyre-ignore[16]
        if not card:
            print(f"⚠️  Card 'paramkart' not found, creating...")
            card = Card(bank_id=bank.id, name='ParamKart', slug='paramkart', is_active=True)  # type: ignore # pyre-ignore[16]
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
                self.browser = self.playwright.chromium.connect_over_cdp("http://localhost:9222")
                connected = True
                print("   ✅ Connected to local existing Chrome instance")
                
                if len(self.browser.contexts) > 0:  # type: ignore # pyre-ignore[58]
                    context = self.browser.contexts[0]
                else:
                    context = self.browser.new_context()
                    
                self.page = context.new_page()
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
            if self.browser:
                self.browser.close()  # type: ignore # pyre-ignore[16]
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass

    def _fetch_campaign_urls(self, limit: Optional[int] = None) -> List[str]:  # type: ignore # pyre-ignore[16,6]
        print(f"📥 Fetching campaign list from {self.CAMPAIGNS_URL} ...")
        self.page.goto(self.CAMPAIGNS_URL, wait_until="domcontentloaded", timeout=120000)
        time.sleep(5)

        print("   ⏬ Scrolling down to load all campaigns...")
        last_height = self.page.evaluate("document.body.scrollHeight")
        scroll_count = 0
        while scroll_count < 30:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2.5)
            new_height = self.page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scroll_count += 1  # type: ignore # pyre-ignore[58]
            if limit:
                # Early break if limit reached
                soup = BeautifulSoup(self.page.content(), "html.parser")
                count = len(set([a['href'] for a in soup.select('a[href^="/avantajlar/"]') if a['href'] != '/avantajlar/']))
                if count >= (limit or 0):
                    break

        print(f"   ⏬ Scrolled {scroll_count} times.")
        
        soup = BeautifulSoup(self.page.content(), "html.parser")
        all_links = []
        
        for a in soup.select('a[href^="/avantajlar/"]'):  # type: ignore # pyre-ignore[16,6]
            href = a['href']
            if href != '/avantajlar/' and "tum-avantajlar" not in href:
                full_url = urljoin(self.BASE_URL, href)
                all_links.append(str(full_url))  # type: ignore

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
                    self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    success = True
                    break
                except Exception as e:
                    print(f"      ⚠️ Detail load attempt {attempt+1}/2 failed: {e}. Retrying...")
                    time.sleep(3)
            
            if not success:
                print(f"      ❌ Could not load detail page: {url}")
                return None  # type: ignore # pyre-ignore[7]
                
            # Click accept cookies banner if it exists and blocks view
            try:
                btn = self.page.query_selector('button[id*="cookie-accept"], button[class*="cookie"]')
                if btn and btn.is_visible():
                    btn.click()
            except:
                pass

            # Scroll to bottom of detail page as user requested to trigger lazy loading of content
            print("      ⏬ Scrolling detail page...")
            self.page.evaluate("""async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0;
                    let distance = 300;
                    let timer = setInterval(() => {
                        let scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance; // JS syntax fix
                        if(totalHeight >= scrollHeight){
                            clearInterval(timer);
                            resolve();
                        }
                    }, 100);
                });
            }""")
            time.sleep(1.5)

            soup = BeautifulSoup(self.page.content(), "html.parser")
            
            # Title
            title_el = soup.find('h1')
            title = self._clean(title_el.text) if title_el else "Başlık Yok"

            # Image
            image_url = None
            img_el = soup.select_one("img.img-fluid, .avantaj-resim img, img.hero-image")
            if img_el:
                # Param uses various data attributes for lazy loading
                src = (
                    img_el.get("data-original") or 
                    img_el.get("data-src") or 
                    img_el.get("data-lazy-src") or
                    img_el.get("src")
                )
                if src and not src.startswith("data:") and "logo" not in src.lower():
                    image_url = urljoin(self.BASE_URL, src)
            
            # Date extract from full text later if needed, but sometimes it is in specific fields
            
            # Content Extraction
            conditions = []
            
            # Param often uses lists for "Temel Bilgi" and "Genel Bilgi"
            for ul in soup.find_all('ul'):
                for li in ul.find_all('li'):
                    text = self._clean(li.text)
                    if text and len(text) > 10 and not text.startswith("Bizi Takip Edin"):
                        conditions.append(text)
            
            # If nothing found in lists, look for paragraphs under specific sections
            if not conditions:
                for p in soup.find_all('p'):
                    text = self._clean(p.text)
                    if text and len(text) > 20 and "Bizi Takip Edin" not in text:
                        conditions.append(text)
                        
            # Assemble full text for AI
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
            "yazım hataları", 
            "sorumlu tutulamaz", 
            "sorumluluk kabul edilmez",
            "durdurma hakkına sahiptir"
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
                Campaign.tracking_url == url, Campaign.card_id == self.card_id
            ).first()
            
            if existing:
                print(f"   ⏭️  Skipped (Already exists): {existing.title}")
                return "skipped"  # type: ignore # pyre-ignore[7]

        print(f"🔍 Processing: {url}")
        data = self._extract_campaign_data(url)
        if not data:
            print("   ⏭️  Skipped (Parse Error)")
            return "skipped"  # type: ignore # pyre-ignore[7]

        title = data.get("title") or "Başlıksız"
        if is_url_blocked(self.db, url):
            print(f"   🚫 Skipped (Blocklisted): {title}")
            return "skipped"  # type: ignore # pyre-ignore[7]

        try:
            ai_data = self.parser.parse_campaign_data(
                raw_text=data["full_text"], 
                bank_name=self.BANK_NAME, 
                title=data["title"],
                tracking_url=url,
                force=force
            ) or {}
        except Exception as e:
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            print(f"   ⚠️ AI parse error: {e}")
            ai_data = {}
            
        print(f"   🧠 AI Data: {json.dumps(ai_data, ensure_ascii=False)}")

        try:
            raw_title = ai_data.get("title") or data.get("title") or ""
            formatted_title = self._to_title_case(raw_title)
            slug = self._get_or_create_slug(formatted_title)
            
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
            final_conditions = "\n".join(conds) if conds else "\n".join(data["conditions"])

            cards_raw = ai_data.get("cards", [])
            if isinstance(cards_raw, str):
                cards_raw = [c.strip() for c in cards_raw.split(",") if c.strip()]
            eligible_cards_str = ", ".join(cards_raw) or "ParamKart"

            existing = self.db.query(Campaign).filter(  # type: ignore # pyre-ignore[16]
                Campaign.tracking_url == url, Campaign.card_id == self.card_id
            ).first()

            if existing:
                print(f"   🔄 Updating existing campaign: {existing.title}")
                existing.sector_id = sector.id if sector else None  # type: ignore # pyre-ignore[16]
                existing.title = formatted_title
                existing.description = ai_data.get("description") or formatted_title
                existing.reward_text = ai_data.get("reward_text")
                existing.reward_value = ai_data.get("reward_value")
                existing.reward_type = ai_data.get("reward_type")
                existing.conditions = final_conditions
                existing.eligible_cards = eligible_cards_str
                if data["image_url"]:  # type: ignore # pyre-ignore[16,6]
                    existing.image_url = data["image_url"]
                existing.start_date = start_date or existing.start_date
                existing.end_date = end_date or existing.end_date
                existing.updated_at = func.now()
                self.db.commit()  # type: ignore # pyre-ignore[16]
                print(f"   ✅ Updated: {existing.title[:50]}")  # type: ignore # pyre-ignore[16,6]
                campaign = existing
            else:
                campaign = Campaign(  # type: ignore
                    card_id=self.card_id,  # type: ignore
                    sector_id=sector.id if sector else None,  # type: ignore # pyre-ignore[16]
                    slug=slug,  # type: ignore
                    title=formatted_title,  # type: ignore
                    description=ai_data.get("description") or formatted_title,  # type: ignore
                    reward_text=ai_data.get("reward_text"),  # type: ignore
                    reward_value=ai_data.get("reward_value"),  # type: ignore
                    reward_type=ai_data.get("reward_type"),  # type: ignore
                    conditions=final_conditions,  # type: ignore
                    eligible_cards=eligible_cards_str,  # type: ignore
                    image_url=data.get("image_url"),  # type: ignore
                    start_date=start_date,  # type: ignore
                    end_date=end_date,  # type: ignore
                    is_active=True,  # type: ignore
                    tracking_url=url,  # type: ignore
                    created_at=func.now(),  # type: ignore
                    updated_at=func.now(),  # type: ignore
                )
                self.db.add(campaign)  # type: ignore # pyre-ignore[16]
                self.db.commit()  # type: ignore # pyre-ignore[16]
                print(f"   ✅ Saved: {campaign.title[:50]}")  # type: ignore # pyre-ignore[16,6]


            # Brands via brand_matcher


            from src.services.brand_matcher import get_or_create_brands_list


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



            return "saved"  # type: ignore # pyre-ignore[7]
        except Exception as e:
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            print(f"   ❌ Save failed: {e}")
            traceback.print_exc()
            return "error"  # type: ignore # pyre-ignore[7]

    def run(self, limit: Optional[int] = None, urls: Optional[List[str]] = None, force: bool = False):  # type: ignore # pyre-ignore[16,6]
        """Main entry point."""
        try:
            print("🚀 Starting Param Scraper (Playwright)...")
            self._start_browser()
            
            if self.db:
                self.db.commit()  # type: ignore # pyre-ignore[16]
                
            found_urls = self._fetch_campaign_urls(limit=limit)
            
            # Filter if specific URLs provided
            if urls:
                final_urls = [u for u in found_urls if u in urls]
            else:
                final_urls = found_urls

            print(f"   🎯 Processing {len(final_urls)} campaigns...")
            
            success, skipped, failed = 0, 0, 0
            for i, url in enumerate(final_urls, 1):
                print(f"\n[{i}/{len(final_urls)}]")
                try:
                    res = self._process_campaign(url, force=force)
                    if res == "saved":
                        success += 1  # type: ignore # pyre-ignore[58]
                    elif res == "skipped":
                        skipped += 1  # type: ignore # pyre-ignore[58]
                    else:
                        failed += 1  # type: ignore # pyre-ignore[58]
                except Exception as e:
                    print(f"❌ Error: {e}")
                    if self.db:
                        self.db.rollback()  # type: ignore # pyre-ignore[16]
                    failed += 1  # type: ignore # pyre-ignore[58]
                time.sleep(1)
            print(f"\n🏁 Finished. {len(final_urls)} found, {success} saved, {skipped} skipped, {failed} errors")
            
            # Log execution
            if self.db:
                log_scraper_execution(
                    db=self.db,
                    scraper_name="param",
                    status="SUCCESS" if failed == 0 else ("PARTIAL" if success > 0 else "FAILED"),  # type: ignore # pyre-ignore[58]
                    total_found=len(final_urls),
                    total_saved=success,
                    total_skipped=skipped,
                    total_failed=failed
                )
        except Exception as e:
            print(f"❌ Scraper error: {e}")
            if self.db:
                error_details = {"traceback": traceback.format_exc(), "error": str(e)}
                log_scraper_execution(
                    db=self.db,
                    scraper_name="param",
                    status="FAILED",
                    error_details=error_details
                )
            raise
        finally:
            self._stop_browser()
            self.db.close()  # type: ignore # pyre-ignore[16]


if __name__ == "__main__":
    import argparse  # type: ignore # pyre-ignore[21]
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit campaigns")
    parser.add_argument("--force", action="store_true", help="Force update")
    parser.add_argument("--urls", nargs='*', help="Specific URLs to scrape")
    args = parser.parse_args()
    
    scraper = ParamScraper()
    scraper.run(limit=args.limit, urls=args.urls, force=args.force)
