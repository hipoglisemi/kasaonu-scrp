


"""
İşbankası Maximum Genç Scraper
Powered by Playwright (GitHub Actions compatible, Cloudflare-resistant)
"""

import os
import sys
import time  # type: ignore # pyre-ignore[21]
import re  # type: ignore # pyre-ignore[21]
import uuid  # type: ignore # pyre-ignore[21]
import traceback  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from typing import Optional, Dict, Any, List  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked  # type: ignore
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]

# Path setup
project_root = "/Users/hipoglisemi/Desktop/kartavantaj-scraper"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from dotenv import load_dotenv  # type: ignore # pyre-ignore[21]
    load_dotenv(os.path.join(project_root, '.env'))
except Exception:
    pass
try:
    with open(os.path.join(project_root, '.env'), 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                k, v = line.strip().split('=', 1)
                if k not in os.environ:
                    os.environ[k] = v.strip('"\'')
except Exception:
    pass

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Date, Numeric, ForeignKey  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import sessionmaker, relationship, declarative_base  # type: ignore # pyre-ignore[21]
from sqlalchemy.dialects.postgresql import UUID  # type: ignore # pyre-ignore[21]

# AIParser is lazy-imported in __init__ to avoid google.generativeai hang
AIParser = None

DATABASE_URL = os.environ.get("DATABASE_URL")
from src.models import Bank, Card, Sector, Brand, CampaignBrand, Campaign  # type: ignore # pyre-ignore[21]


SECTOR_MAP = {
    "Market & Gıda": "Market", "Giyim & Aksesuar": "Giyim",
    "Restoran & Kafe": "Restoran & Kafe", "Seyahat": "Seyahat",
    "Turizm & Konaklama": "Seyahat", "Elektronik": "Elektronik",
    "Mobilya & Dekorasyon": "Mobilya & Dekorasyon",
    "Kozmetik & Sağlık": "Kozmetik & Sağlık", "E-Ticaret": "E-Ticaret",
    "Otomotiv": "Otomotiv", "Sigorta": "Sigorta", "Eğitim": "Eğitim",
    "Diğer": "Diğer",
}


class IsbankMaximumGencScraper:
    """İşbankası Maximum Genç scraper - Playwright based"""

    BASE_URL = "https://www.maximumgenc.com.tr"
    CAMPAIGNS_URL = "https://www.maximumgenc.com.tr/kampanyalar"
    BANK_NAME = "İşbankası"
    CARD_SLUG = "maximum-genc"
    DEFAULT_IMAGE_URL = None  # Logo fallback kaldırıldı — placeholder görünmesine yol açıyordu

    def __init__(self):
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL is not set")
        self.engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()
        
        # Lazy import of AIParser to avoid google.generativeai hanging at module import time
        try:
            from src.services.ai_parser import AIParser as _AIParser  # type: ignore # pyre-ignore[21]
            print("[DEBUG] AIParser lazy-imported via src.services")
        except ImportError:
            try:
                from services.ai_parser import AIParser as _AIParser  # type: ignore # pyre-ignore[21]
                print("[DEBUG] AIParser lazy-imported via services")
            except ImportError as e:
                print(f"[DEBUG] AIParser import FAILED: {e}")  # type: ignore # pyre-ignore[16,6]
                raise
        self.parser = _AIParser()
        print("[DEBUG] AIParser initialized")

        self.page = None
        self.browser = None
        self.playwright = None
        self.card_id = None
        self._init_card()

    def _init_card(self):
        bank = self.db.query(Bank).filter(  # type: ignore # pyre-ignore[16]
            Bank.slug.in_([
                'i-sbankasi',   # gerçek DB slug
                'isbank', 'isbankasi', 'is-bankasi', 'turkiye-is-bankasi',
            ])
        ).first()
        if not bank:
            bank = self.db.query(Bank).filter(  # type: ignore # pyre-ignore[16]
                Bank.name.ilike('%İş Bank%') | Bank.name.ilike('%İşbank%')
            ).first()
        if not bank:
            print(f"⚠️  İşbankası not found in DB, creating...")
            bank = Bank(name='İş Bankası', slug='isbank')
            self.db.add(bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
        print(f"✅ Bank: {bank.name} (ID: {bank.id}, slug: {bank.slug})")

        card = self.db.query(Card).filter(  # type: ignore # pyre-ignore[16]
            Card.slug.in_([
                'maximum-genc', 'maximum-genc-card', 'isbank-maximum-genc',
                'isbankasi-maximum-genc', 'maximumgenc',
            ])
        ).first()
        if not card:
            card = self.db.query(Card).filter(  # type: ignore # pyre-ignore[16]
                Card.name.ilike('%Maximum Gen%'),
                Card.bank_id == bank.id  # type: ignore # pyre-ignore[16]
            ).first()
        if not card:
            print(f"⚠️  Card 'maximum-genc' not found, creating...")
            card = Card(bank_id=bank.id, name='Maximum Genç Card', slug='maximum-genc', is_active=True)  # type: ignore # pyre-ignore[16]
            self.db.add(card)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
            
        # Ensure card is not None before accessing id
        if card:
            self.card_id = card.id  # type: ignore # pyre-ignore[16]
            print(f"✅ Card: {card.name} (ID: {self.card_id}, slug: {card.slug})")
        else:
            self.card_id = None
            print(f"❌ Card could not be initialized")



    def _start_browser(self):
        from playwright.sync_api import sync_playwright  # type: ignore # pyre-ignore[21]
        self.playwright = sync_playwright().start()
        
        is_ci = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"
        connected = False

        if not is_ci:
            try:
                print("   🔌 Attempting to connect to local Chrome debug instance at http://localhost:9222...")
                if self.playwright:
                    self.browser = self.playwright.chromium.connect_over_cdp("http://localhost:9222")
                connected = True
                print("   ✅ Connected to local existing Chrome instance")
                
                # Use existing context if available
                if self.browser and len(self.browser.contexts) > 0:  # type: ignore # pyre-ignore[58]
                    context = self.browser.contexts[0]
                elif self.browser:
                    context = self.browser.new_context()
                else:
                    context = None
                    
                if context:
                    self.page = context.new_page()
                
                if self.page:
                    self.page.set_default_timeout(120000)
                return
            except Exception as e:
                print(f"   ⚠️  Could not connect to debug Chrome, launching headless... ({e})")
                
        if not connected and self.playwright:
            self.browser = self.playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu", "--window-size=1920,1080",
                      "--disable-blink-features=AutomationControlled",
                      "--disable-extensions", "--disable-web-security"]
            )
            if self.browser:
                context = self.browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    locale="tr-TR",
                    timezone_id="Europe/Istanbul",
                    extra_http_headers={"Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"}
                )
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                self.page = context.new_page()
            
            if self.page:
                self.page.set_default_timeout(120000)
                print("✅ Playwright browser started.")

    def _stop_browser(self):
        try:
            if hasattr(self, 'browser') and self.browser:
                self.browser.close()  # type: ignore # pyre-ignore[16]
            if hasattr(self, 'playwright') and self.playwright:
                self.playwright.stop()
        except Exception:
            pass

    def _fetch_campaign_urls(self, limit: Optional[int] = None) -> tuple[List[str], List[str]]:  # type: ignore # pyre-ignore[16,6]
        print(f"📥 Fetching campaign list from {self.CAMPAIGNS_URL}...")
        if not self.page:
            print("❌ Page is not initialized")
            return [], []  # type: ignore # pyre-ignore[7]
        self.page.goto(self.CAMPAIGNS_URL, wait_until="domcontentloaded", timeout=120000)
        time.sleep(5)

        scroll_count = 0
        while scroll_count < 100:
            if limit:
                soup = BeautifulSoup(self.page.content(), "html.parser")
                items = soup.find_all("div", class_="item")
                count = 0
                for item in items:
                    a_tag = item.find("a", href=True)
                    if a_tag:
                        href = a_tag["href"].lower()
                        if "tum-kampanya" not in href and "/kampanyalar/" not in href and href.startswith("/"):
                            count += 1  # type: ignore # pyre-ignore[58]
                            
                if limit is not None and count >= limit:
                    break

            if self.page:
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

            btn = self.page.query_selector(".show-more-opportunity") if self.page else None
            if btn and btn.is_visible():
                btn.scroll_into_view_if_needed()
                time.sleep(1)
                try:
                    btn.click()
                except Exception:
                    if self.page:
                        self.page.evaluate("element => element.click()", btn)
                time.sleep(3)
                scroll_count += 1  # type: ignore # pyre-ignore[58]
                print(f"   ⏬ Loaded more campaigns (round {scroll_count})...")
            else:
                break

        soup = BeautifulSoup(self.page.content(), "html.parser")
        
        all_links = []
        expired_links = []
        
        items = soup.find_all("div", class_="item")
        for item in items:
            a_tag = item.find("a", href=True)
            if not a_tag:
                continue
                
            href = a_tag["href"].lower()
            if "tum-kampanya" not in href and "/kampanyalar/" not in href and href.startswith("/"):
                full_url = urljoin(self.BASE_URL, a_tag["href"])
                
                # Sona ermiş kampanya tespiti
                parent_text = item.get_text(separator='\n', strip=True).lower()
                
                if "sona ermiştir" in parent_text or "bitmiştir" in parent_text or "sona erdi" in parent_text or "süresi doldu" in parent_text:
                    expired_links.append(full_url)
                else:
                    all_links.append(full_url)

        unique_urls = list(dict.fromkeys(all_links))
        unique_expired = list(dict.fromkeys(expired_links))
        if isinstance(unique_urls, list) and limit is not None:
            unique_urls = unique_urls[:limit]  # type: ignore # pyre-ignore[16,6]
            
        print(f"✅ Found {len(unique_urls)} active campaigns, and {len(unique_expired)} expired campaigns")
        return unique_urls, unique_expired  # type: ignore # pyre-ignore[7]

    def _extract_campaign_data(self, url: str) -> Optional[Dict[str, Any]]:  # type: ignore # pyre-ignore[16,6]
        try:
            success = False
            for attempt in range(3):
                try:
                    self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    success = True
                    break
                except Exception as e:
                    print(f"      ⚠️ Detail load attempt {attempt+1}/3 failed: {e}. Retrying...")
                    time.sleep(3 + attempt * 2)
            
            if not success:
                print(f"      ❌ Could not load detail page after 3 attempts: {url}")
                return None  # type: ignore # pyre-ignore[7]
                
            self.page.evaluate("window.scrollTo(0, 500)")
            time.sleep(2)

            soup = BeautifulSoup(self.page.content(), "html.parser")
            title_el = soup.select_one("h1.color-purple, h1")
            title = self._clean(title_el.text) if title_el else "Başlık Yok"

            if "gecmis" in url or "geçmiş" in title.lower():
                return None  # type: ignore # pyre-ignore[7]

            # Blocklist check
            from src.database import get_db_session  # type: ignore
            with get_db_session() as db:
                 if is_url_blocked(db, url):
                      print(f"   🚫 Skipped (Blocklisted): {url}")
                      return None

            # Image — multiple fallback strategies
            image_url = None
            # 1. Dedicated campaign image containers
            img_el = (
                soup.select_one(".detail-img img")
                or soup.select_one(".campaign-banner img")
                or soup.select_one(".campaign-detail img")
                or soup.select_one(".opportunity-image img")
                or soup.select_one("section.banner img")
                or soup.select_one("section img")
            )
            if img_el:
                src = img_el.get("data-original") or img_el.get("data-src") or img_el.get("src")
                if src and not src.startswith("data:") and "logo" not in src.lower():
                    image_url = urljoin(self.BASE_URL, src)
            # 2. Background-image in style attribute
            if not image_url:
                for sel in ["section.banner", "div.banner", ".campaign-banner", "section.opportunity", ".detail-img"]:
                    banner = soup.select_one(sel)
                    if banner and "style" in banner.attrs:
                        match = re.search(r"url\(['\"]?(.*?)['\"]?\)", banner["style"])
                        if match and "logo" not in match.group(1).lower():
                            image_url = urljoin(self.BASE_URL, match.group(1))
                            break
            # 3. Any img on page that looks like a campaign image (not a logo/icon)
            if not image_url:
                for img in soup.find_all("img"):
                    src = img.get("data-src") or img.get("src") or ""
                    if src and not src.startswith("data:") and "logo" not in src.lower() and "icon" not in src.lower():
                        candidate = urljoin(self.BASE_URL, src)
                        # Prefer campaign/opportunity images
                        if any(k in src.lower() for k in ["kampanya", "campaign", "opportunity", "firsatlar", "firsat", "uploa"]):
                            image_url = candidate
                            break
            # No fallback to logo — leave None if no real image found

            # Date
            date_text = ""
            date_el = soup.select_one("div.mobile-date, .date, .campaign-date")
            if date_el:
                spans = date_el.find_all("span")
                if len(spans) >= 2:
                    date_text = f"{self._clean(spans[0].text)} - {self._clean(spans[1].text)}"
                else:
                    date_text = self._clean(date_el.text)
            
            if not date_text:
                full_text = soup.get_text()
                m = re.search(r"(\d{1,2}\s+\w+\s+\d{4})\s*-\s*(\d{1,2}\s+\w+\s+\d{4})", full_text)
                if m:
                    date_text = m.group(0)

            # Content
            content_div = soup.select_one("div.content-part, .detail-text, .campaign-content, section .container")
            conditions = []
            full_text = ""
            if content_div:
                raw = content_div.get_text("\n", strip=True)
                conditions = [self._clean(l) for l in raw.split("\n") if len(self._clean(l)) > 20]
                full_text = " ".join(conditions)
            else:
                full_text = self._clean(soup.get_text())[:1000]  # type: ignore # pyre-ignore[16,6]

            conditions = [c for c in conditions if not c.startswith("Copyright")]

            return {  # type: ignore # pyre-ignore[7]
                "title": title, "image_url": image_url,
                "date_text": date_text, "full_text": full_text,
                "conditions": conditions, "source_url": url,
            }
        except Exception as e:
            print(f"   ⚠️ Error extracting {url}: {e}")
            return None  # type: ignore # pyre-ignore[7]

    def _parse_date(self, date_text: str, is_end: bool = False) -> Optional[str]:  # type: ignore # pyre-ignore[16,6]
        if not date_text:
            return None  # type: ignore # pyre-ignore[7]
        text = date_text.replace("İ", "i").lower()
        months = {
            "ocak": "01", "şubat": "02", "mart": "03", "nisan": "04",
            "mayıs": "05", "haziran": "06", "temmuz": "07", "ağustos": "08",
            "eylül": "09", "ekim": "10", "kasım": "11", "aralık": "12",
        }
        try:
            m = re.search(r"(\d{1,2})\s*([a-zğüşıöç]+)?\s*-\s*(\d{1,2})\s*([a-zğüşıöç]+)\s*(\d{4})", text)
            if m:
                day1, month1, day2, month2, year = m.groups()
                if not month1:
                    month1 = month2
                if is_end:
                    return f"{year}-{months.get(month2, '12')}-{str(day2).zfill(2)}"  # type: ignore # pyre-ignore[7]
                return f"{year}-{months.get(month1, '01')}-{str(day1).zfill(2)}"  # type: ignore # pyre-ignore[7]
        except Exception:
            pass
        return None  # type: ignore # pyre-ignore[7]

    def _clean(self, text: str) -> str:
        if not text:
            return ""  # type: ignore # pyre-ignore[7]
        return re.sub(r"\s+", " ", text.replace("\n", " ").replace("\r", "")).strip()  # type: ignore # pyre-ignore[7]

    def _to_title_case(self, text: Any) -> str:
        if not text: return ""
        text_str = str(text)
        replacements = {"I": "ı", "İ": "i"}
        lower_text = text_str
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

    def _process_campaign(self, url: str) -> str:
        existing = self.db.query(Campaign).filter(  # type: ignore # pyre-ignore[16]
            Campaign.tracking_url == url, Campaign.card_id == self.card_id
        ).first()
        if existing:
            print(f"   ⏭️  Skipped (Already exists): {existing.title[:40]}")
            return "skipped"  # type: ignore # pyre-ignore[7]

        # Blocklist check
        if is_url_blocked(self.db, url):
            print(f"   🚫 Skipped (Blocklisted): {url}")
            return "skipped"  # type: ignore # pyre-ignore[7]

        print(f"🔍 Processing: {url}")
        data = self._extract_campaign_data(url)
        if not data:
            print("   ⏭️  Skipped")
            return "skipped"  # type: ignore # pyre-ignore[7]

        try:
            ai_data = self.parser.parse_campaign_data(
                raw_text=data["full_text"], bank_name=self.BANK_NAME
            ) or {}
        except Exception as e:
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            print(f"   ⚠️ AI parse error: {e}")
            ai_data = {}

        try:
            raw_title = ai_data.get("title") or data.get("title") or ""
            formatted_title = self._to_title_case(raw_title)
            slug = self._get_or_create_slug(formatted_title)
            ai_cat = ai_data.get("sector", "Diğer")
            sector = self.db.query(Sector).filter(Sector.slug == ai_cat).first()  # type: ignore # pyre-ignore[16]
            if not sector:
                sector = self.db.query(Sector).filter(Sector.slug == 'diger').first()  # type: ignore # pyre-ignore[16]

            start_date, end_date = None, None
            for ai_key, is_end in [("start_date", False), ("end_date", True)]:  # type: ignore # pyre-ignore[16,6]
                val = ai_data.get(ai_key)
                dt = None
                if val:
                    try:
                        dt = datetime.strptime(val, "%Y-%m-%d")
                    except Exception:
                        pass
                if not dt:
                    parsed = self._parse_date(data["date_text"], is_end=is_end)
                    if parsed:
                        try:
                            dt = datetime.strptime(parsed, "%Y-%m-%d")
                        except Exception:
                            pass
                if ai_key == "start_date":
                    start_date = dt
                else:
                    end_date = dt

            conds = ai_data.get("conditions", [])
            if isinstance(conds, str):
                conds = [c.strip() for c in conds.split("\n") if c.strip()]
            part = ai_data.get("participation")
            if part and "Detayları İnceleyin" not in part:

            cards_raw = ai_data.get("cards", [])
            if isinstance(cards_raw, str):
                cards_raw = [c.strip() for c in cards_raw.split(",") if c.strip()]

            campaign = Campaign(
                card_id=self.card_id, sector_id=sector.id if sector else None,  # type: ignore # pyre-ignore[16]
                slug=slug, title=formatted_title,
                description=ai_data.get("description") or data["title"][:200],  # type: ignore # pyre-ignore[16,6]
                reward_text=ai_data.get("reward_text"),
                reward_value=ai_data.get("reward_value"),
                reward_type=ai_data.get("reward_type"),
                conditions="\n".join(conds),
                eligible_cards=", ".join(cards_raw) or None,
                image_url=data["image_url"],
                start_date=start_date, end_date=end_date,
                is_active=True, tracking_url=url,
                created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
            )
            self.db.add(campaign)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]


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



            print(f"   ✅ Saved: {campaign.title[:50]}")  # type: ignore # pyre-ignore[16,6]
            return "saved"  # type: ignore # pyre-ignore[7]
        except Exception as e:
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            print(f"   ❌ Save failed: {e}")
            traceback.print_exc()
            return "error"  # type: ignore # pyre-ignore[7]

    def run(self, limit: Optional[int] = None, urls: Optional[List[str]] = None, force: bool = False):  # type: ignore # pyre-ignore[16,6]
        try:
            print("🚀 Starting İşbankası Maximum Genç Scraper (Playwright)...")
            self._start_browser()
            
            # Close DB session to prevent idle connection timeout during long Playwright scroll
            if self.db:
                self.db.commit()  # type: ignore # pyre-ignore[16]
                self.db.close()  # type: ignore # pyre-ignore[16]
                
            if urls:
                print(f"🎯 Running specific URLs: {len(urls)}")
                active_urls = urls
                expired_urls = []
            else:
                active_urls, expired_urls = self._fetch_campaign_urls(limit=limit)
            
            # Evaluate expired campaigns logic
            if expired_urls:
                print(f"🛑 Found {len(expired_urls)} expired campaigns on list page. Checking DB for early end...")
                for e_url in expired_urls:
                    try:
                        existing = self.db.query(Campaign).filter(  # type: ignore # pyre-ignore[16]
                            Campaign.tracking_url == e_url,
                            Campaign.card_id == self.card_id,
                            Campaign.is_active == True
                        ).first()
                        if existing:
                            print(f"   🛑 Deleting expired campaign from DB: {existing.title}")
                            self.db.delete(existing)
                            self.db.commit()  # type: ignore # pyre-ignore[16]
                    except Exception as e:
                        if self.db:
                            self.db.rollback()  # type: ignore # pyre-ignore[16]
                        print(f"   ⚠️ Could not update expired campaign {e_url}: {e}")
                        
            urls = active_urls
            success, skipped, failed = 0, 0, 0
            error_details = []
            for i, url in enumerate(urls, 1):
                print(f"\n[{i}/{len(urls)}]")
                try:
                    res = self._process_campaign(url)
                    if res == "saved":
                        success += 1  # type: ignore # pyre-ignore[58]
                    elif res == "skipped":
                        skipped += 1  # type: ignore # pyre-ignore[58]
                    else:
                        failed += 1  # type: ignore # pyre-ignore[58]
                        error_details.append({"url": url, "error": "Unknown DB failure"})
                except Exception as e:
                    print(f"❌ Error: {e}")
                    failed += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": url, "error": str(e)})
                time.sleep(1.5)
            print(f"\n🏁 Finished. {len(urls)} found, {success} saved, {skipped} skipped, {failed} errors")
            
            status = "SUCCESS"
            if failed > 0:  # type: ignore # pyre-ignore[58]
                 status = "PARTIAL" if (success > 0 or skipped > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
                 
            try:
                from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
                Session = sessionmaker(bind=self.engine)
                with Session() as db:
                     log_scraper_execution(
                          db=db,
                          scraper_name="maximum-genc",
                          status=status,
                          total_found=len(urls),
                          total_saved=success,
                          total_skipped=skipped,
                          total_failed=failed,
                          error_details={"errors": error_details} if error_details else None
                     )
            except Exception as le:
                 print(f"⚠️ Could not save scraper log: {le}")
                 
        except Exception as e:
            print(f"❌ Scraper error: {e}")
            try:
                from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
                Session = sessionmaker(bind=self.engine)
                with Session() as db:
                     log_scraper_execution(db, "maximum-genc", "FAILED", 0, 0, 0, 1, {"error": str(e)})
            except:
                pass
            raise
        finally:
            self._stop_browser()


if __name__ == "__main__":
    import argparse  # type: ignore # pyre-ignore[21]
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of campaigns to scrape")
    parser.add_argument("--urls", type=str, default=None, help="Comma separated list of URLs to scrape")
    parser.add_argument("--force", action="store_true", help="Force update existing campaigns")
    args = parser.parse_args()
    
    url_list = None
    if args.urls:
        url_list = [u.strip() for u in args.urls.split(",") if u.strip()]
        
    scraper = IsbankMaximumGencScraper()
    scraper.run(limit=args.limit, urls=url_list, force=args.force)
