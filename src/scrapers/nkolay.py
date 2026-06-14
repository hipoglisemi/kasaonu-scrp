import os
import sys
import time
import random
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urljoin

# Ensure src is in path so CLI execution works
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.chrome.service import Service
from selenium_stealth import stealth
from selenium.webdriver.common.by import By

try:
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_WDM = True
except ImportError:
    HAS_WDM = False

from src.database import get_db_session
from src.models import Campaign, Bank, Card, Sector, Brand, CampaignBrand
from src.services.ai_parser import parse_api_campaign
from src.utils.slug_generator import get_unique_slug
from src.utils.scraper_utils import should_skip_campaign, upsert_campaign, is_url_blocked
from src.utils.cache_manager import clear_cache


class NkolayScraper:
    """
    Scraper for Nkolay (Aktif Bank) campaigns.
    Uses a single Selenium driver for the full run (list + details).
    """

    BASE_URL = 'https://www.nkolay.com'
    LIST_URL = 'https://www.nkolay.com/kampanyalar'
    BANK_NAME = 'Nkolay'
    CARD_NAME = 'Nkolay Kart'

    def __init__(self):
        self.driver: Optional[WebDriver] = None
        self.db: Optional[Session] = None
        self.bank: Optional[Bank] = None
        self.card: Optional[Card] = None
        self.sector_cache: Dict[str, Sector] = {}

    # ── DRIVER ────────────────────────────────────────────────────────────────

    def setup_driver(self):
        """Initialize a single Selenium driver for the entire scrape."""
        if self.driver:
            return

        print("   🔌 Initializing Browser Driver (Chrome + Stealth)...")
        options = webdriver.ChromeOptions()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

        # Headless in CI/Docker
        if os.getenv("DOCKER_MODE") == "true" or os.getenv("HEADLESS") == "1" or os.getenv("TEST_MODE") == "1":
            options.add_argument('--headless=new')

        try:
            if HAS_WDM:
                self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            else:
                self.driver = webdriver.Chrome(options=options)

            stealth(
                self.driver,
                languages=["tr-TR", "tr"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
            print("   ✅ Browser launched successfully.")
        except Exception as e:
            print(f"   ❌ Failed to launch browser: {e}")
            raise

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    # ── CACHE / DB HELPERS ────────────────────────────────────────────────────

    def _load_cache(self):
        db = self.db
        if not db:
            return

        # Bank
        bank = db.query(Bank).filter(Bank.slug == "nkolay").first()
        if not bank:
            bank = Bank(name=self.BANK_NAME, slug="nkolay", is_active=True, logo_url="/logos/cards/nkolay.png", aliases=["nkolay", "aktif bank", "aktifbank"])
            db.add(bank)
            db.commit()
        self.bank = bank

        # Card
        card = db.query(Card).filter(Card.slug == "nkolay-kart").first()
        if not card:
            card = Card(name=self.CARD_NAME, bank_id=bank.id, slug="nkolay-kart", card_type="credit", is_active=True, logo_url="/logos/cards/nkolay.png")
            db.add(card)
            db.commit()
        self.card = card

        # Sectors
        for s in db.query(Sector).all():
            self.sector_cache[s.slug] = s
            self.sector_cache[s.name.lower()] = s

    # ── SCRAPING ──────────────────────────────────────────────────────────────

    def _fetch_campaign_list(self) -> List[Dict[str, Any]]:
        """Scroll the campaign list page, click 'Daha fazla göster' and collect card-level information."""
        print(f"📥 Fetching campaign list from {self.LIST_URL}")
        campaigns = []
        driver = self.driver
        if not driver:
            return campaigns

        driver.get(self.LIST_URL)
        time.sleep(5)

        # Dismiss cookie banner
        try:
            cookie_buttons = driver.find_elements(By.XPATH, "//button[contains(text(),'Kabul') or contains(text(),'kabul') or contains(text(),'KABUL') or contains(text(),'Accept') or contains(text(),'accept')]")
            for btn in cookie_buttons:
                if btn.is_displayed():
                    btn.click()
                    time.sleep(1)
                    break
        except Exception as e:
            print(f"   No cookie banner dismissed: {e}")

        # Click 'Daha fazla göster' button repeatedly
        click_count = 0
        while True:
            try:
                show_more_btns = driver.find_elements(By.XPATH, "//button[contains(text(),'Daha fazla') or contains(text(),'daha fazla') or contains(text(),'DAHA FAZLA') or contains(text(),'Göster') or contains(text(),'göster')]")
                clicked = False
                for btn in show_more_btns:
                    if btn.is_displayed() and btn.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                        time.sleep(1.5)
                        btn.click()
                        click_count += 1
                        print(f"   [{click_count}] Clicked 'Daha fazla göster' button")
                        time.sleep(3.5)
                        clicked = True
                        break
                if not clicked:
                    break
            except Exception as e:
                print(f"   No more 'Daha fazla göster' button or error: {e}")
                break

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        cards = soup.select('a[class*="productCardLink"]')
        print(f"   DEBUG: Found {len(cards)} potential card elements")

        for card in cards:
            href = card.get('href')
            if not href:
                continue

            # Title
            p_elm = card.select_one('p')
            title = p_elm.get_text(strip=True) if p_elm else ""
            if not title:
                title = card.get_text(strip=True)
            if not title:
                continue

            # Image
            img_elm = card.select_one('img')
            image_url = img_elm.get('src') if img_elm else None
            if image_url and not image_url.startswith('http'):
                image_url = urljoin(self.BASE_URL, image_url)

            campaigns.append({
                'title': title,
                'url': urljoin(self.BASE_URL, href),
                'list_image': image_url,
                'sector_hint': '',
            })

        # Deduplicate by URL
        seen = set()
        unique = []
        for c in campaigns:
            if c['url'] not in seen:
                seen.add(c['url'])
                unique.append(c)

        print(f"✅ Found {len(unique)} unique campaign cards")
        return unique

    def _fetch_detail(self, url: str) -> str:
        """Load a detail page with scrolling and extract clean HTML content."""
        driver = self.driver
        if not driver:
            return ""

        driver.get(url)
        time.sleep(3.5)

        # Scroll through the page to trigger lazy content
        for frac in [0.33, 0.66, 1.0]:
            driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {frac});")
            time.sleep(1)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Clean noise directly in soup before passing to AI parser
        for noise_sel in ['.owl-carousel', 'select', 'footer', 'header', 'nav', 'iframe', 'script', 'style']:
            for el in soup.select(noise_sel):
                el.decompose()

        # Target the main campaign content
        for sel in ['main', 'article', 'div[class*="detail"]', 'div[class*="content"]']:
            el = soup.select_one(sel)
            if el:
                return str(el)

        return str(soup.find('body') or soup)

    # ── PROCESSING ────────────────────────────────────────────────────────────

    def _process_campaign(self, item: Dict[str, Any], force: bool = False) -> str:
        url = item['url']
        db = self.db
        if not db:
            return "error"

        # Blocklist check
        if is_url_blocked(db, url):
            print(f"      ⏭️  Skipped (blocked URL): {url}")
            return "skipped"

        # Skip check
        existing = db.query(Campaign).filter(Campaign.tracking_url == url).first()
        if not force and existing and existing.is_active and existing.is_approved:
            print(f"      ⏭️  Skipped (already exists and active): {url}")
            return "skipped"

        print(f"   🔎 Processing: {item['title']}")

        # Detail page
        raw_content = self._fetch_detail(url)
        if not raw_content:
            print(f"      ⚠️ Could not extract detail content for {url}")
            raw_content = item['title']

        # AI parse
        ai_data = parse_api_campaign(
            title=item['title'],
            short_description=item['title'],
            content_html=raw_content,
            bank_name=self.BANK_NAME,
            scraper_sector=item.get('sector_hint'),
            tracking_url=url,
            force=force,
        )

        if not ai_data:
            print("      ❌ AI parsing failed.")
            return "error"

        return self._save_campaign(ai_data, url, item.get('list_image'))

    def _save_campaign(self, data: Dict[str, Any], url: str, image_url: Optional[str]) -> str:
        db = self.db
        if not db:
            return "error"

        try:
            title = data.get('short_title') or data.get('title') or "Nkolay Kampanya"
            slug = get_unique_slug(title, db, Campaign)

            # Dates
            start_date = None
            end_date = None
            if data.get('start_date'):
                try:
                    start_date = datetime.strptime(data['start_date'], "%Y-%m-%d")
                except Exception:
                    pass
            if data.get('end_date'):
                try:
                    end_date = datetime.strptime(data['end_date'], "%Y-%m-%d")
                except Exception:
                    pass

            # Sector
            sector_slug = data.get('sector', 'diger')
            sector = self.sector_cache.get(str(sector_slug).lower()) or self.sector_cache.get('diger')

            # Conditions
            conditions_raw = data.get('conditions', [])
            if isinstance(conditions_raw, list):
                conditions_text = '\n'.join(conditions_raw)
            else:
                conditions_text = str(conditions_raw)

            campaign = Campaign(
                slug=slug,
                title=title,
                card_id=self.card.id if self.card else None,
                sector_id=sector.id if sector else None,
                reward_value=data.get('reward_value'),
                reward_type=data.get('reward_type'),
                reward_text=data.get('reward_text') or 'Detayları İnceleyin',
                description=str(data.get('description') or '')[:500],
                ai_marketing_text=data.get("ai_marketing_text"),
                conditions=conditions_text,
                participation=data.get('participation') or '',
                start_date=start_date,
                end_date=end_date,
                image_url=image_url,
                tracking_url=url,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                eligible_cards=", ".join(data.get("cards", [])) if isinstance(data.get("cards"), list) and data.get("cards") else self.CARD_NAME
            )

            # Use centralized upsert_campaign for revival and quality control
            campaign, op_status = upsert_campaign(db, campaign)
            db.commit()

            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title[:50]}...")

            db.refresh(campaign)

            # Brands via brand_matcher
            if data.get('brands'):
                from src.services.brand_matcher import get_or_create_brands_list
                brand_ids = get_or_create_brands_list(db, data['brands'], {}, campaign.sector_id)
                for bid in brand_ids:
                    link_check = db.query(CampaignBrand).filter_by(campaign_id=campaign.id, brand_id=bid).first()
                    if not link_check:
                        db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                db.commit()

            return op_status

        except IntegrityError:
            db.rollback()
            print(f"      ⚠️ Duplicate, skipped.")
            return "skipped"
        except Exception as e:
            db.rollback()
            print(f"      ❌ Save error: {e}")
            return "error"

    # ── ENTRY POINT ───────────────────────────────────────────────────────────

    def run(self, limit: Optional[int] = None, force: bool = False):
        print(f"🚀 Starting Nkolay Scraper...")
        try:
            self.db = get_db_session()
            self._load_cache()
            self.setup_driver()  # single driver for full run

            items = self._fetch_campaign_list()
            if limit:
                items = items[:limit]
                print(f"   Using limit: {limit}")

            saved = revived = skipped = errors = 0
            error_details = []
            for i, item in enumerate(items, 1):
                print(f"   [{i}/{len(items)}] {item['url']}")
                try:
                    res = self._process_campaign(item, force=force)
                    if res == "saved":
                        saved += 1
                    elif res == "revived":
                        revived += 1
                    elif res == "skipped":
                        skipped += 1
                    else:
                        errors += 1
                        error_details.append({"url": item['url'], "error": f"Process returned {res}"})
                except Exception as e:
                    print(f"      ❌ Error: {e}")
                    errors += 1
                time.sleep(random.uniform(1.2, 2.5))

            print(f"\n✅ Summary: {saved} saved, {revived} revived, {skipped} skipped, {errors} errors.")

            from src.utils.logger_utils import log_scraper_execution
            log_scraper_execution(
                db=self.db,
                scraper_name="nkolay",
                status="SUCCESS" if errors == 0 else "PARTIAL",
                total_found=len(items),
                total_saved=saved,
                total_skipped=skipped,
                total_failed=errors,
                total_revived=revived,
                error_details={"errors": error_details} if error_details else None
            )

            if saved > 0 or revived > 0:
                clear_cache('campaigns:*')

        except Exception as e:
            print(f"❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.close_driver()
            if self.db:
                self.db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Limit number of campaigns')
    parser.add_argument('--force', action='store_true', help='Force re-parse even if exists')
    args = parser.parse_args()

    scraper = NkolayScraper()
    scraper.run(limit=args.limit, force=args.force)
