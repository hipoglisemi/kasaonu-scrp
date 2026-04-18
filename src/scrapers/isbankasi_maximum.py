



import sys
import os
import time  # type: ignore # pyre-ignore[21]
import re  # type: ignore # pyre-ignore[21]
import uuid  # type: ignore # pyre-ignore[21]
import traceback  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from typing import Optional, Dict, Any, List, cast  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.scraper_utils import is_url_blocked  # type: ignore
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]

# Load Env - same pattern as ziraat.py
try:
    from dotenv import load_dotenv  # type: ignore # pyre-ignore[21]
    load_dotenv()
except Exception as e:
    print(f"[DEBUG] dotenv load failed: {e}")  # type: ignore # pyre-ignore[16,6]
try:
    with open(os.path.join(project_root, '.env'), 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                k, v = line.strip().split('=', 1)
                if k not in os.environ:
                    os.environ[k] = v.strip('"\'')
except Exception:
    pass

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Date, Numeric, Text, ForeignKey  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import sessionmaker, relationship, declarative_base  # type: ignore # pyre-ignore[21]
from sqlalchemy.dialects.postgresql import UUID  # type: ignore # pyre-ignore[21]

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
print(f"[DEBUG] DATABASE_URL set: {'YES' if DATABASE_URL else 'NO'}")  # type: ignore # pyre-ignore[16,6]

# AIParser is lazy-imported in __init__ to avoid google.generativeai hang
AIParser = None




from src.models import Bank, Card, Sector, Brand, CampaignBrand, Campaign  # type: ignore # pyre-ignore[21]


SECTOR_MAP = {
    "Market & Gıda": "Market",
    "Giyim & Aksesuar": "Giyim",
    "Restoran & Kafe": "Restoran & Kafe",
    "Seyahat": "Seyahat",
    "Turizm & Konaklama": "Seyahat",
    "Elektronik": "Elektronik",
    "Mobilya & Dekorasyon": "Mobilya & Dekorasyon",
    "Kozmetik & Sağlık": "Kozmetik & Sağlık",
    "E-Ticaret": "E-Ticaret",
    "Otomotiv": "Otomotiv",
    "Sigorta": "Sigorta",
    "Eğitim": "Eğitim",
    "Diğer": "Diğer",
}


class IsbankMaximumScraper:
    """İşbankası Maximum card campaign scraper - Playwright based"""

    BASE_URL = "https://www.maximum.com.tr"
    CAMPAIGNS_URL = "https://www.maximum.com.tr/kampanyalar"
    BANK_NAME = "İşbankası"
    CARD_SLUG = "maximum-card"  # seed.ts'deki gerçek slug

    def __init__(self):
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL is not set")
        self.engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        # Lazy import of AIParser to avoid google.generativeai hanging at module import time
        try:
            from src.services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]
            self.parser = AIParser()
        except ImportError:
            try:
                from services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]
                self.parser = AIParser()
            except ImportError as e:
                print(f"[DEBUG] AIParser import FAILED: {e}")  # type: ignore # pyre-ignore[16,6]
                raise
        print("[DEBUG] AIParser initialized")
        
        self.page = None
        self.browser = None
        self.playwright = None


    def _get_or_create_bank(self) -> int:
        bank = self.session.query(Bank).filter(  # type: ignore # pyre-ignore[16]
            Bank.slug.in_([
                'i-sbankasi',   # gerçek DB slug
                'isbank',       # seed.ts slug
                'isbankasi', 'is-bankasi', 'turkiye-is-bankasi',
            ])
        ).first()
        if not bank:
            bank = self.session.query(Bank).filter(  # type: ignore # pyre-ignore[16]
                Bank.name.ilike('%İş Bank%') | Bank.name.ilike('%İşbank%')
            ).first()
        if not bank:
            print(f"⚠️  {self.BANK_NAME} not found in DB, creating...")
            bank = Bank(name=self.BANK_NAME, slug='isbank')
            self.session.add(bank)  # type: ignore # pyre-ignore[16]
            self.session.commit()  # type: ignore # pyre-ignore[16]
        if bank and hasattr(bank, 'id'):
            return bank.id  # type: ignore # pyre-ignore[7]
        return 0 # Or handle as error  # type: ignore # pyre-ignore[7]

    def _get_or_create_card(self, bank_id: int) -> int:
        card = self.session.query(Card).filter(  # type: ignore # pyre-ignore[16]
            Card.slug.in_([
                'maximum-card', 'maximum', 'isbank-maximum',
                'isbankasi-maximum', 'maximumcard',
            ])
        ).first()
        if not card:
            card = self.session.query(Card).filter(  # type: ignore # pyre-ignore[16]
                Card.name.ilike('%Maximum%'),
                Card.bank_id == bank_id
            ).first()
        if not card:
            print(f"⚠️  Card 'maximum-card' not found, creating...")
            card = Card(bank_id=bank_id, name='Maximum Card', slug='maximum-card', is_active=True)
            self.session.add(card)  # type: ignore # pyre-ignore[16]
            self.session.commit()  # type: ignore # pyre-ignore[16]
        if card and hasattr(card, 'id'):
            return card.id  # type: ignore # pyre-ignore[7]
        return 0 # Or handle as error  # type: ignore # pyre-ignore[7]

    def _start_browser(self):
        from playwright.sync_api import sync_playwright  # type: ignore # pyre-ignore[21]
        self.playwright = sync_playwright().start()
        
        # Consistent with Maximiles stealth pattern
        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu", "--window-size=1920,1080",
                  "--disable-blink-features=AutomationControlled",
                  "--disable-extensions", "--disable-web-security"]
        )
        context = self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="tr-TR",
            timezone_id="Europe/Istanbul",
            extra_http_headers={"Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"}
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.page = context.new_page()
        self.page.set_default_timeout(60000)
        print("✅ Playwright browser started for Maximum Scraper.")

    def _stop_browser(self):
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass


    def _fetch_campaign_urls(self, limit: Optional[int] = None) -> tuple[List[str], List[str]]:  # type: ignore # pyre-ignore[16,6]
        print(f"📥 Fetching campaign list from {self.CAMPAIGNS_URL}...")
        
        import requests  # type: ignore # pyre-ignore[21]
        import urllib3  # type: ignore # pyre-ignore[21]
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # We fetch the first page. Maximum usually loads a bunch of HTML blocks, and potentially has a load-more API.
        # But for simplification and immediate WAF bypass, we fetch the main HTML.
        all_campaign_links = []
        try:
            response = requests.get(self.CAMPAIGNS_URL, headers=self.headers, verify=False, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Extract links
            links = soup.find_all("a", href=True)
            for a in links:
                if "/kampanyalar/" in a["href"] and "arsiv" not in a["href"] and "gecmis" not in a["href"] and len(a["href"]) > 20:  # type: ignore # pyre-ignore[16,6]
                    all_campaign_links.append(a)
                    
        except Exception as e:
            print(f"   ❌ Failed to fetch campaign list: {e}")
            return [], []  # type: ignore # pyre-ignore[7]

        excluded_suffixes = [
            "-kampanyalari",
            "-kampanyalar",
            "premium-kampanyalar",
            "tum-kampanyalar"
        ]
        
        excluded_paths = [
            "/kampanyalar/seyahat",
            "/kampanyalar/turizm",
            "/kampanyalar/akaryakit",
            "/kampanyalar/giyim-aksesuar",
            "/kampanyalar/market",
            "/kampanyalar/elektronik",
            "/kampanyalar/beyaz-esya",
            "/kampanyalar/mobilya-dekorasyon",
            "/kampanyalar/egitim-kirtasiye",
            "/kampanyalar/online-alisveris",
            "/kampanyalar/otomotiv",
            "/kampanyalar/vergi-odemeleri",
            "/kampanyalar/maximum-mobil",
            "/kampanyalar/diger",
            "/kampanyalar/yeme-icme",
            "/kampanyalar/maximum-pati-kart",
            "/kampanyalar/arac-kiralama",
            "/kampanyalar/bankamatik",
            "/kampanyalar/bireysel",
            "/kampanyalar/ticari",
            "/kampanyalar/ozel-bankacilik",
            "bireysel", "ticari", "diger-kampanyalar",
            "movenpick", "arsivi", "ozel-bankacilik",
            "/kampanyalar/arsiv",
            "/kampanyalar/yurtdisi"
        ]

        # Known slugs that look like campaigns but redirect to category pages
        excluded_slug_keywords = [
            "solariste-gunes-gozlugu",
        ]


        unique_urls = []
        unique_expired = []
        seen = set()

        for a in all_campaign_links:
            href = str(a["href"]).strip()  # type: ignore # pyre-ignore[16,6]
            
            if href in excluded_paths: continue
            if any(href.endswith(s) for s in excluded_suffixes): continue
            if any(kw in href for kw in excluded_slug_keywords): continue

            
            full_url = urljoin(self.BASE_URL, cast(str, href))
            if full_url in seen: continue
            seen.add(full_url)
            
            # Check for expired status based on class or text
            parent_text = ""
            parent = None
            if hasattr(a, 'find_parent'):
                a_tag = cast(Any, a)
                parent = a_tag.find_parent("div", class_="card") or a_tag.find_parent("div", class_="campaign-card") or a_tag.find_parent("div", class_="opportunity-result") or getattr(a_tag, 'parent', None)
            
            if parent:
                parent_text = parent.get_text(separator='\n', strip=True).lower()

            if a.find(class_="expired") or "gecmis" in href or "geçmiş" in a.text.lower() or \
               "sona ermiştir" in parent_text or "bitmiştir" in parent_text or "sona erdi" in parent_text or "süresi doldu" in parent_text:
                unique_expired.append(full_url)
            else:
                unique_urls.append(full_url)
                
        if limit is not None:
            try:
                limit_val = int(limit)  # type: ignore # pyre-ignore[6]
                unique_urls = cast(List[str], unique_urls)[:limit_val]  # type: ignore # pyre-ignore[16]
            except Exception:
                pass

        print(f"✅ Found {len(unique_urls)} active campaigns, and {len(unique_expired)} expired campaigns")
        return unique_urls, unique_expired  # type: ignore # pyre-ignore[7]

    def _extract_campaign_data(self, url: str) -> Optional[Dict[str, Any]]:  # type: ignore # pyre-ignore[16,6]
        try:
            success = False
            for attempt in range(3):
                try:
                    if not self.page:
                        print("      ❌ self.page is None")
                        return None
                    
                    self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    # Simple scroll to ensure lazy content loads
                    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
                    time.sleep(1)
                    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)
                    
                    html_content = self.page.content()
                    success = True
                    break
                except Exception as e:
                    print(f"      ⚠️ Detail load attempt {attempt+1}/3 failed: {e}. Retrying...")
                    time.sleep(3 + attempt * 2)
            
            if not success:
                print(f"      ❌ Could not load detail page after 3 attempts: {url}")
                return None  # type: ignore # pyre-ignore[7]

                
            import urllib3  # type: ignore # pyre-ignore[21]
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            soup = BeautifulSoup(html_content, "html.parser")
            title_el = soup.select_one("h1.gradient-title-text") or soup.find("h1")
            title = self._clean(title_el.text) if title_el else "Başlık Yok"

            if "gecmis" in url or "geçmiş" in title.lower() or "bulunamadı" in title.lower() or "bulunamadı" in title.lower():
                print(f"   ⏭️ Skipped (Broken/Expired title): {title}")
                return None  # type: ignore # pyre-ignore[7]

            # Kategori/index sayfası tuzağı: eğer sayfada kampanya görseli (CampaignImage) yoksa
            # bu URL bireysel gibi bir kategori sayfasına yönlendirilmiştir, atla.
            campaign_img_el = soup.select_one("img[id$='CampaignImage']")
            if not campaign_img_el:
                # kategori başlıkları içeriyorsa kesinlikle atla
                category_titles = ["Bireysel Kart Kampanyaları", "Ticari Kart Kampanyaları", "Tüm Kampanyalar"]
                if any(ct.lower() in title.lower() for ct in category_titles):
                    print(f"   ⏭️ Skipped (Category redirect page): {title}")
                    return None  # type: ignore # pyre-ignore[7]


            # Blocklist check
            from src.database import get_db_session  # type: ignore
            with get_db_session() as db:
                 if is_url_blocked(db, url):
                      print(f"   🚫 Skipped (Blocklisted): {title}")
                      return None

            # 404 kontrolü - Geçersiz/silinmiş sayfa filtresi
            page_text = soup.get_text()
            if any(phrase in page_text for phrase in [
                "Üzgünüz, aradığınız sayfayı bulamadık",
                "404",
                "Sayfa Bulunamadı",
                "Kampanya Bulunamadı",
                "Kampanya bulunamadı",
                "Sayfaya ulaşılamıyor",
                "Bu kampanya sona ermiştir",
            ]):
                print(f"   ⏭️  Skipped (404/expired page): {url}")
                return None  # type: ignore # pyre-ignore[7]

            # Date
            date_text = ""
            for sel in ["span[id$='KampanyaTarihleri']", ".campaign-date", ".date"]:  # type: ignore # pyre-ignore[16,6]
                el = soup.select_one(sel)
                if el:
                    date_text = self._clean(el.text)
                    break

            # Skip expired
            end_iso = self._parse_date(date_text, is_end=True)
            if end_iso:
                try:
                    if datetime.strptime(end_iso, "%Y-%m-%d").date() < datetime.now().date():
                        return None  # type: ignore # pyre-ignore[7]
                except Exception:
                    pass

            # Participation
            participation_text = ""
            for sel in ["span[id$='KatilimSekli']"]:  # type: ignore # pyre-ignore[16,6]
                el = soup.select_one(sel)
                if el:
                    participation_text = self._clean(el.text)
                    break

            # Description / Conditions
            desc_el = soup.select_one(".campaign-detail, .campaignDetail, .content, .detail-content, .editor-content")
            full_text = ""
            if desc_el:
                for br in desc_el.find_all("br"):
                    br.replace_with("\n")
                full_text = "\n".join([self._clean(l) for l in desc_el.get_text().split("\n") if len(self._clean(l)) > 0])  # type: ignore # pyre-ignore[58]
            else:
                full_text = self._clean(soup.get_text())[:2000]  # type: ignore # pyre-ignore[16,6]

            # Image — multiple fallback strategies
            image_url = None
            img_el = (
                soup.select_one("img[id$='CampaignImage']")
                or soup.select_one(".campaign-detail img")
                or soup.select_one(".campaign-banner img")
                or soup.select_one(".opportunity-image img")
                or soup.select_one("section.banner img")
                or soup.select_one("section img")
            )
            if img_el:
                src = img_el.get("data-original") or img_el.get("data-src") or img_el.get("src")
                if src and not src.startswith("data:") and "logo" not in src.lower():
                    if isinstance(src, str):
                        image_url = urljoin(self.BASE_URL, src)
            # 2. Background-image in style attribute
            if not image_url:
                for sel in ["section.banner", "div.banner", ".campaign-banner", ".campaign-detail"]:
                    banner = soup.select_one(sel)
                    if banner and "style" in banner.attrs:
                        match = re.search(r"url\(['\"]?(.*?)['\"]?\)", banner["style"])
                        if match and "logo" not in match.group(1).lower():
                            image_url = urljoin(self.BASE_URL, match.group(1))
                            break

            return {  # type: ignore # pyre-ignore[7]
                "title": title, "image_url": image_url,
                "date_text": date_text, "full_text": full_text,
                "source_url": url,
                "raw_text": full_text # Feed clean text to AI, not entire HTML
            }
        except Exception as e:
            print(f"   ⚠️ Error extracting {url}: {e}")
            return None  # type: ignore # pyre-ignore[7]

    def _parse_date(self, date_text: str, is_end: bool = False) -> Optional[str]:  # type: ignore # pyre-ignore[16,6]
        if not date_text:
            return None  # type: ignore # pyre-ignore[7]
        text = date_text.replace("İ", "i").lower()
        
        # Check dd.mm.yyyy format first: 1.1.2026 - 31.12.2026
        pattern_dot = r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s*-\s*(\d{1,2})\.(\d{1,2})\.(\d{4})"
        match_dot = re.search(pattern_dot, text)
        if match_dot:
            d1, m1, y1, d2, m2, y2 = match_dot.groups()
            if is_end:
                return f"{y2}-{m2.zfill(2)}-{d2.zfill(2)}"  # type: ignore # pyre-ignore[7]
            return f"{y1}-{m1.zfill(2)}-{d1.zfill(2)}"  # type: ignore # pyre-ignore[7]
            
        months = {
            "ocak": "01", "şubat": "02", "mart": "03", "nisan": "04",
            "mayıs": "05", "haziran": "06", "temmuz": "07", "ağustos": "08",
            "eylül": "09", "ekim": "10", "kasım": "11", "aralık": "12",
        }
        try:
            pattern = r"(\d{1,2})\s*([a-zğüşıöç]+)?\s*-\s*(\d{1,2})\s*([a-zğüşıöç]+)\s*(\d{4})"
            match = re.search(pattern, text)
            if match:
                day1, month1, day2, month2, year = match.groups()
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
        text_str = str(text or "")
        replacements = {"I": "ı", "İ": "i"}
        lower_text = text_str
        for k, v in replacements.items(): lower_text = lower_text.replace(k, v)
        lower_text = lower_text.lower()
        words = lower_text.split()
        capitalized_words = []
        for word in words:
            if not word: continue
            if word[0] == 'i': capitalized_words.append('İ' + word[1:])  # type: ignore # pyre-ignore[16,6]
            elif word[0] == 'ı': capitalized_words.append('I' + word[1:])  # type: ignore # pyre-ignore[16,6]
            else: capitalized_words.append(word.capitalize())
        return " ".join(capitalized_words)  # type: ignore # pyre-ignore[7]

    def _get_or_create_slug(self, title: str) -> str:
        from src.utils.slug_generator import generate_slug  # type: ignore # pyre-ignore[21]
        base = generate_slug(title)
        slug = base
        counter = 2
        while self.session.query(Campaign).filter(Campaign.slug == slug).first():  # type: ignore # pyre-ignore[16]
            slug = f"{base}-{counter}"
            counter += 1
        return slug  # type: ignore # pyre-ignore[7]

    def _save_campaign(self, data: Dict[str, Any], bank_id: int, card_id: int) -> Optional[int]:  # type: ignore # pyre-ignore[16,6]
        try:
            # Final blocklist check before saving
            if is_url_blocked(self.session, data["source_url"]):
                print(f"   🚫 Skipped (Safety Check: Blocklisted): {data['source_url']}")
                return None

            raw_title = data.get("title") or ""
            formatted_title = self._to_title_case(raw_title)
            slug = self._get_or_create_slug(formatted_title)

            ai_cat = data.get("sector", "Diğer")
            db_sector_name = ai_cat
            sector = self.session.query(Sector).filter(Sector.slug == db_sector_name).first()  # type: ignore # pyre-ignore[16]
            if not sector:
                sector = self.session.query(Sector).filter(Sector.slug == 'diger').first()  # type: ignore # pyre-ignore[16]

            start_date = None
            end_date = None
            if data.get("start_date"):
                try:
                    start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
                except Exception:
                    pass
            if data.get("end_date"):
                try:
                    end_date = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
                except Exception:
                    pass
            if not start_date:
                sd = self._parse_date(data["date_text"], is_end=False)
                if sd:
                    try:
                        start_date = datetime.strptime(sd, "%Y-%m-%d").date()
                    except Exception:
                        pass
            if not end_date:
                ed = self._parse_date(data["date_text"], is_end=True)
                if ed:
                    try:
                        end_date = datetime.strptime(ed, "%Y-%m-%d").date()
                    except Exception:
                        pass

            conds = data.get("conditions", [])
            part = data.get("participation")
            final_conditions = "\n".join(conds)


            eligible = ", ".join(data.get("cards", [])) or None

            campaign = Campaign(  # type: ignore
                card_id=card_id,  # type: ignore
                sector_id=sector.id if sector else None,  # type: ignore
                slug=slug,  # type: ignore
                title=formatted_title,  # type: ignore
                description=data.get("description") or data["title"][:200],  # type: ignore
                ai_marketing_text=data.get("ai_marketing_text") or data.get("description") or data["title"][:200],  # type: ignore
                reward_text=data.get("reward_text"),  # type: ignore
                reward_value=data.get("reward_value"),  # type: ignore
                reward_type=data.get("reward_type"),  # type: ignore
                conditions=final_conditions,  # type: ignore
                eligible_cards=eligible,
                participation=part,  # type: ignore
                clean_text=data.get("_clean_text"),  # type: ignore

                image_url=data["image_url"],  # type: ignore
                start_date=start_date,  # type: ignore
                end_date=end_date,  # type: ignore
                is_active=True,  # type: ignore
                tracking_url=data["source_url"],  # type: ignore
                created_at=datetime.utcnow(),  # type: ignore
                updated_at=datetime.utcnow(),  # type: ignore
            )
            if self.session is None: return None
            self.session.add(campaign)  # type: ignore # pyre-ignore[16]
            self.session.commit()  # type: ignore # pyre-ignore[16]


            from src.services.brand_matcher import get_or_create_brands_list  # type: ignore # pyre-ignore[21]
            brand_ids = get_or_create_brands_list(
                db=self.session,
                names=data.get("brands", []),
                brand_cache=getattr(self, 'brand_cache', {}),
                sector_id=sector.id if sector else None
            )


            for bid in brand_ids:


                try:


                    link = self.session.query(CampaignBrand).filter(


                        CampaignBrand.campaign_id == campaign.id,


                        CampaignBrand.brand_id == bid


                    ).first()


                    if not link:


                        self.session.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))


                        self.session.commit()


                except Exception as e:


                    self.session.rollback()


                    print(f"   ⚠️ CampaignBrand link failed: {e}")



            print(f"   ✅ Saved: {campaign.title[:50]}")  # type: ignore # pyre-ignore[16,6]
            return campaign.id  # type: ignore # pyre-ignore[7]
        except Exception as e:
            self.session.rollback()  # type: ignore # pyre-ignore[16]
            print(f"   ❌ Save failed: {e}")
            traceback.print_exc()
            return None  # type: ignore # pyre-ignore[7]

    def run(self, limit: Optional[int] = None, urls: Optional[List[str]] = None, force: bool = False):  # type: ignore # pyre-ignore[16,6]
        """Main execution flow"""

        bank_id = self._get_or_create_bank()
        card_id = self._get_or_create_card(bank_id)

        print(f"✅ Bank: {self.BANK_NAME} (ID: {bank_id}, slug: isbankasi)")
        print(f"✅ Card: Maximum (ID: {card_id}, slug: {self.CARD_SLUG})")
        print("🚀 Starting İşbankası Maximum Scraper (Requests + Playwright)...")
        
        self._start_browser()


        try:
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
                        existing = self.session.query(Campaign).filter(  # type: ignore # pyre-ignore[16]
                            Campaign.tracking_url == e_url,
                            Campaign.card_id == card_id,
                            Campaign.is_active == True
                        ).first()
                        if existing:
                            print(f"   🛑 Deleting expired campaign from DB: {existing.title}")
                            self.session.delete(existing)
                            self.session.commit()  # type: ignore # pyre-ignore[16]
                    except Exception as e:
                        self.session.rollback()  # type: ignore # pyre-ignore[16]
                        print(f"   ⚠️ Could not update expired campaign {e_url}: {e}")
                        
            urls = active_urls
            results = []
            success: int = 0
            skipped: int = 0
            failed: int = 0
            error_details: List[Dict[str, Any]] = []  # type: ignore # pyre-ignore[16,6]
            
            for i, url in enumerate(urls, 1):
                if limit is not None:
                    try:
                        limit_val = int(limit)  # type: ignore # pyre-ignore[6]
                        if i > limit_val:
                            break
                    except Exception:
                        pass
                    
                print(f"\n[{i}/{len(urls)}]")
                print(f"🔍 Processing: {url}")
                
                # Blocklist check
                if is_url_blocked(self.session, url):
                    print(f"   🚫 Skipped (Blocklisted): {url}")
                    skipped += 1  # type: ignore # pyre-ignore[58]
                    continue

                # DB Cache query
                existing = self.session.query(Campaign).filter(  # type: ignore # pyre-ignore[16]
                    Campaign.tracking_url == url,
                    Campaign.card_id == card_id
                ).first()
                if existing and not force:
                    existing_img = existing.image_url  # type: ignore # pyre-ignore[16]
                    is_placeholder = (
                        not existing_img
                        or existing_img.strip() == ''
                        or existing_img.startswith("/placeholders/")
                        or "logo" in existing_img.lower()
                        or "kartavantaj" in existing_img.lower()
                    )
                    
                    # If it's not a placeholder, check if it's actually broken (404/401)
                    if not is_placeholder:
                        try:
                            import requests
                            img_resp = requests.head(existing_img, timeout=5, verify=False)
                            if img_resp.status_code in [404, 401, 403]:
                                print(f"   ⚠️ Image is broken ({img_resp.status_code}): {existing_img}")
                                is_placeholder = True
                        except Exception:
                            pass

                    if is_placeholder:
                        # Görsel güncelleme: sadece detay sayfasından görsel çek
                        print(f"   🔄 Görsel eksik, güncelleniyor: {existing.title[:40]}")  # type: ignore # pyre-ignore[16,6]
                        res_data = self._extract_campaign_data(url)
                        if res_data and res_data.get("image_url"):
                            existing.image_url = res_data["image_url"]  # type: ignore # pyre-ignore[16]
                            existing.updated_at = datetime.utcnow()  # type: ignore # pyre-ignore[16]
                            self.session.commit()  # type: ignore # pyre-ignore[16]
                            print(f"   ✅ Görsel güncellendi: {res_data['image_url'][:60]}")
                        else:
                            print(f"   ⚠️ Görsel bulunamadı, atlandı")
                    else:
                        print(f"   ⏭️ Skipped (Already exists): [{existing.id}] {existing.title[:40]}")  # type: ignore # pyre-ignore[16,6]
                    skipped += 1  # type: ignore # pyre-ignore[58]
                    continue
                    
                try:
                    res_data = self._extract_campaign_data(url)
                    if not res_data:
                        skipped += 1  # type: ignore # pyre-ignore[58]
                        continue
                        
                    try:
                        ai_data = self.parser.parse_campaign_data(
                            raw_text=res_data["raw_text"],
                            title=res_data["title"],
                            bank_name=self.BANK_NAME,
                            card_name="Maximum Card",
                            tracking_url=url, # for global cache
                            force=force
                        )
                        if ai_data:
                            print("   ✅ AI parsed successfully")
                            res_data.update(ai_data)
                    except Exception as ai_e:
                        print(f"   ⚠️ AI parse error: {ai_e}")
                        
                    saved_id = self._save_campaign(res_data, bank_id, card_id)
                    if saved_id:
                        success += 1  # type: ignore # pyre-ignore[58]
                        results.append(saved_id)
                    else:
                        failed += 1  # type: ignore # pyre-ignore[58]
                        error_details.append({"url": url, "error": "Save returned None"})
                        
                except Exception as e:
                    print(f"❌ Error during details extraction: {e}")
                    self.session.rollback()  # type: ignore # pyre-ignore[16]
                    failed += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": url, "error": str(e)})
                
                time.sleep(1.5)

            print(f"\n🏁 Finished. {len(urls)} found, {success} saved, {skipped} skipped, {failed} errors")
            
            status = "SUCCESS"
            if int(failed or 0) > 0:  # type: ignore # pyre-ignore[58]
                status = "PARTIAL" if (int(success or 0) > 0 or int(skipped or 0) > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
                
            log_scraper_execution(
                db=self.session,
                scraper_name="isbankasi_maximum",
                status=status,
                total_found=len(urls),
                total_saved=int(success or 0),
                total_skipped=int(skipped or 0),
                total_failed=int(failed or 0),
                error_details={"errors": error_details} if error_details else None
            )
            
        except Exception as e:
            print(f"❌ Scraper error: {e}")
            
            status = "FAILED"
            Session = sessionmaker(bind=self.engine)
            err_db = Session()
            try:
                log_scraper_execution(
                    db=err_db,
                    scraper_name="isbankasi_maximum",
                    status=status,
                    total_found=0,
                    total_saved=0,
                    total_skipped=0,
                    total_failed=1,
                    error_details={"error": str(e)}
                )
            except:
                pass
            finally:
                err_db.close()  # type: ignore # pyre-ignore[16]
                
            raise
        finally:
            self.session.close()  # type: ignore # pyre-ignore[16]
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

    scraper = IsbankMaximumScraper()
    scraper.run(limit=args.limit, urls=url_list, force=args.force)
