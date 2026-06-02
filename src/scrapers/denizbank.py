


import os
import time  # type: ignore # pyre-ignore[21]
import random  # type: ignore # pyre-ignore[21]
import re  # type: ignore # pyre-ignore[21]
import json  # type: ignore # pyre-ignore[21]
import requests  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from dotenv import load_dotenv  # type: ignore # pyre-ignore[21]
import sys
from typing import List, Dict, Any, Optional

# Path setup - reach project root (parent of src)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Internal Imports
from src.services.ai_parser import AIParser  # type: ignore
from src.services.ai_parser_golden import parse_api_campaign, get_golden_parser  # type: ignore
from src.services.brand_normalizer import cleanup_brands  # type: ignore
from src.utils.scraper_utils import is_url_blocked, upsert_campaign  # type: ignore
from src.models import Campaign, Sector, Brand, CampaignBrand  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

# Database Imports
from sqlalchemy import create_engine, text  # type: ignore
from sqlalchemy.dialects.postgresql import JSONB  # type: ignore

# Browser
from selenium import webdriver  # type: ignore # pyre-ignore[21]
from selenium.webdriver.chrome.service import Service  # type: ignore # pyre-ignore[21]
from webdriver_manager.chrome import ChromeDriverManager  # type: ignore # pyre-ignore[21]
from selenium_stealth import stealth  # ✅ AÇILDI - ÖNEMLİ!  # type: ignore # pyre-ignore[21]

# Virtual Display (for GitHub Actions / Headless)
try:
    from pyvirtualdisplay import Display  # type: ignore # pyre-ignore[21]
    HAS_VIRTUAL_DISPLAY = True
except ImportError:
    HAS_VIRTUAL_DISPLAY = False

load_dotenv()

# --- CONFIG ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

# AI Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("⚠️ GEMINI_API_KEY not found. AI parsing will be disabled/mocked.")

# ZenRows API Key (Optional - for Proxy Bypass)
ZENROWS_API_KEY = os.getenv("ZENROWS_API_KEY")

# Constants
BLACKLIST_IMAGES = [
    "denizbank-logo", "campaign-default", "placeholder", 
    "transparent.png", "blank.gif"
]

class DenizbankScraper:
    BASE_URL = "https://www.denizbonus.com"
    CAMPAIGNS_URL = "https://www.denizbonus.com/bonus-kampanyalari"

    def __init__(self):
        self.engine = create_engine(DATABASE_URL)
        if GEMINI_API_KEY:
            self.ai_parser = AIParser()
        else:
            self.ai_parser = None
            
        self.driver = None
        self.display = None
        self.card_id = None

    def setup_driver(self):
        """Initialize Selenium with Chrome + Stealth Mode."""
        if self.driver:
            return

        # Start Virtual Display if on Linux/Server and no ZenRows
        if sys.platform.startswith('linux') and HAS_VIRTUAL_DISPLAY and not ZENROWS_API_KEY:
            print("   🖥️ Starting Virtual Display (Xvfb)...")
            try:
                self.display = Display(visible=0, size=(1920, 1080))
                if self.display:
                    self.display.start() # type: ignore # pyre-ignore[16]
            except Exception as e:
                print(f"   ⚠️ Failed to start virtual display: {e}")

        print("   🔌 Initializing Browser Driver (Chrome + Stealth)...")
        options = webdriver.ChromeOptions()
        
        # ✅ GÜÇLÜ ANTİ-DETECTION AYARLARI
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Performance & Stability
        options.page_load_strategy = 'eager'  # 'eager' prevents getting stuck on slow resources
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--disable-web-security")
        
        # Headless Mode for CI / Server environments
        if os.getenv("CI") == "true" or sys.platform.startswith('linux'):
            print("   🤖 CI or Linux detected. Enabling Headless Chrome to prevent system freezes...")
            options.add_argument('--headless=new')
        else:
            # Optionally use headless locally to be less intrusive
            options.add_argument('--headless=new')
            
        # Gerçek User Agent
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.set_page_load_timeout(35)  # Max 35s limit to prevent infinite hangs
            print("   ⏱️ Set Page Load Timeout to 35 seconds.")
            
            # ✅ STEALTH MODE UYGULA - ÇOK ÖNEMLİ!
            stealth(self.driver,
                languages=["tr-TR", "tr"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
            
            # ✅ WebDriver Detection'ı Kaldır (CDP ile)
            if self.driver:
                self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', { # type: ignore # pyre-ignore[16]
                    'source': '''
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                        
                        // Chrome flaglerini gizle
                        window.chrome = {
                            runtime: {}
                        };
                        
                        // Permissions API'yi düzelt
                        const originalQuery = window.navigator.permissions.query;
                        window.navigator.permissions.query = (parameters) => (
                            parameters.name === 'notifications' ?
                            Promise.resolve({ state: Notification.permission }) :
                            originalQuery(parameters)
                        );
                    '''
                })
            
            print("   ✅ Browser launched successfully with STEALTH MODE.")
        except Exception as e:
            print(f"   ❌ Failed to launch browser: {e}")
            raise e

    def close_driver(self):
        if self.driver:
            print("   🛑 Closing Browser...")
            try:
                self.driver.quit() # type: ignore # pyre-ignore[16]
            except:
                pass
            self.driver = None
            
        if self.display:
            try:
                self.display.stop() # type: ignore # pyre-ignore[16]
            except:
                pass
            self.display = None

    def _fetch_html(self, url):
        """Fetch HTML. Uses ZenRows if Key exists, otherwise Selenium Stealth."""
        
        # --- MODE 1: ZenRows Proxy (Reliable) ---
        if ZENROWS_API_KEY:
            try:
                print(f"   🛡️ Fetching via ZenRows Proxy: {url}")
                proxy_url = "https://api.zenrows.com/v1/"
                params = {
                    "apikey": ZENROWS_API_KEY,
                    "url": url,
                    "js_render": "true",
                    "premium_proxy": "true",
                }
                response = requests.get(proxy_url, params=params, timeout=60)
                if response.status_code == 200:
                    # Force UTF-8 decode — ZenRows may return ISO-8859-1 Content-Type header
                    # even though the actual content is UTF-8 (denizbonus.com quirk)
                    return response.content.decode('utf-8', errors='replace')  # type: ignore # pyre-ignore[7]
                else:
                    print(f"   ❌ ZenRows Error: {response.status_code} - {response.text}")
                    return None  # type: ignore # pyre-ignore[7]
            except Exception as e:
                print(f"   ❌ ZenRows Exception: {e}")
                return None  # type: ignore # pyre-ignore[7]

        # --- MODE 2: Selenium Stealth (Free / Direct) ---
        self.setup_driver()
        try:
            print(f"   🌐 Navigating (Stealth Mode): {url}")
            
            # ✅ İnsan Davranışı Simülasyonu
            # Önce ana sayfaya git (referrer yaratmak için)
            if url != self.CAMPAIGNS_URL:
                print("   👤 First visiting homepage for natural browsing...")
                try:
                    self.driver.get(self.BASE_URL)
                except Exception as e:
                    print(f"   ⚠️ Homepage load timed out or hit resource freeze: {e}. Proceeding...")
                time.sleep(random.uniform(2.0, 4.0))
            
            # Hedef sayfaya git
            try:
                self.driver.get(url)
            except Exception as e:
                print(f"   ⚠️ Target page load timed out or hit resource freeze: {e}. Proceeding to extract DOM...")
            
            # ✅ Sayfa yüklenmesini bekle
            time.sleep(random.uniform(4.0, 7.0))
            
            # ✅ İnsan gibi scroll davranışı
            # ✅ İnsan gibi scroll davranışı ve Dinamik Yükleme
            print("   📜 Scrolling to load all campaigns...")
            
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_attempts = 15 # A reasonable limit to prevent true infinite loops
            
            while scroll_attempts < max_attempts:
                # Scroll down to bottom
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                
                # Wait for new elements to load
                time.sleep(random.uniform(2.0, 3.5))
                
                # Calculate new scroll height and compare with last scroll height
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                
                if new_height == last_height:
                    # Try one more time with a slightly different scroll to trigger lazy loading
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 100);")
                    time.sleep(1)
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                    
                    new_height = self.driver.execute_script("return document.body.scrollHeight")
                    if new_height == last_height:
                        print(f"   ✅ Reached bottom after {scroll_attempts} scrolls.")
                        break
                
                last_height = new_height
                scroll_attempts += 1  # type: ignore # pyre-ignore[58]
                print(f"   ⏬ Loaded more content (Scroll {scroll_attempts})...")
            
            # Biraz yukarı scroll (insan gibi)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 500);")
            time.sleep(1)
            
            # ✅ Mouse hareket simülasyonu (opsiyonel ama etkili)
            try:
                from selenium.webdriver.common.action_chains import ActionChains  # type: ignore # pyre-ignore[21]
                action = ActionChains(self.driver)
                element = self.driver.find_element("tag name", "body")
                action.move_to_element(element).perform()
            except:
                pass
            
            time.sleep(2)
            return self.driver.page_source  # type: ignore # pyre-ignore[7]
            
        except Exception as e:
            print(f"   ❌ Browser navigation failed: {e}")
            self.close_driver()
            return None  # type: ignore # pyre-ignore[7]

    def _get_slug(self, title):
        slug = title.lower()
        replacements = {
            'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
            'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c'
        }
        for src, dest in replacements.items():
            slug = slug.replace(src, dest)
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        slug = re.sub(r'\s+', '-', slug)
        return slug.strip('-')  # type: ignore # pyre-ignore[7]

    def _fetch_campaign_list(self, limit=None):
        html = self._fetch_html(self.CAMPAIGNS_URL)
        if not html:
            print("   ❌ Failed to fetch campaign list.")
            return []  # type: ignore # pyre-ignore[7]

        soup = BeautifulSoup(html, 'html.parser')
        campaign_urls = []
        
        links = soup.find_all('a', href=True)
        unique_urls = set()
        
        for link in links:
            href = link.get('href', '')
            if 'kampanyalar/' in href: 
                # Avoid social share links or other non-campaign links if any
                if any(x in href for x in ['facebook.com', 'twitter.com', 'linkedin.com', 'whatsapp:', 'google.com']):  # type: ignore # pyre-ignore[16,6]
                    continue
                
                full_url = href if href.startswith('http') else self.BASE_URL + (href if href.startswith('/') else '/' + href)
                unique_urls.add(full_url)  # type: ignore # pyre-ignore[16]

        campaign_urls = list(unique_urls)
        print(f"   🎉 Found {len(campaign_urls)} campaigns via scraping.")
        
        if limit and len(campaign_urls) > limit:
            campaign_urls = campaign_urls[:limit]  # type: ignore # pyre-ignore[16,6]
            
        return campaign_urls  # type: ignore # pyre-ignore[7]

    def _resolve_sector_by_name(self, sector_name):
        """Map AI sector slug to DB sector ID. (AI parser returns a sector slug like 'market-gida')"""
        if not sector_name:
            return 18 # Diğer  # type: ignore # pyre-ignore[7]
        try:
            with self.engine.connect() as conn:
                # Search by slug since AI is strictly instructed to return valid slugs
                result = conn.execute(
                    text("SELECT id FROM sectors WHERE slug = :slug LIMIT 1"),
                    {"slug": sector_name}
                ).fetchone()
                
                return result[0] if result else 18  # type: ignore # pyre-ignore[7]
        except Exception:
            return 18  # type: ignore # pyre-ignore[7]

    def _process_campaign(self, url):
        # Database Pre-check (Skip Logic - Only skip if active)
        try:
            from src.models import Campaign
            from sqlalchemy.orm import sessionmaker
            SessionLocal = sessionmaker(bind=self.engine)
            db = SessionLocal()
            try:
                existing = db.query(Campaign).filter(Campaign.tracking_url == url).first()
                # ♻️ Re-parse if campaign is passive OR pending approval to apply latest logic
                if existing and existing.is_active and existing.is_approved:
                    print(f"   ⏭️ Skipped (Already exists, active and approved): {existing.title[:50]}")
                    return "skipped"
            finally:
                db.close()
        except Exception as e:
            print(f"   ⚠️ DB Pre-check error: {e}")

        print(f"\n📄 Processing: {url}")
        html = self._fetch_html(url)
        if not html:
            return "skipped"  # type: ignore # pyre-ignore[7]

        # Always parse from bytes if possible to let BS4 auto-detect encoding.
        # _fetch_html returns a str (ZenRows UTF-8 decoded, Selenium page_source unicode).
        # Encode back to bytes so BS4 can use the <meta charset> to detect encoding correctly.
        soup = BeautifulSoup(html.encode('utf-8', errors='replace'), 'html.parser')

        # Context Extraction (Title & Image)
        title = "Kampanya Detayı"
        meta_title = soup.find("meta", property="og:title")
        if meta_title: title = meta_title.get("content", "").strip()
        else:
            h1 = soup.find('h1')
            if h1: title = h1.get_text(strip=True)


        # Blocklist check
        try:
            with self.engine.connect() as conn:
                blocked = conn.execute(
                    text("SELECT id FROM campaign_blocklist WHERE url = :url"),
                    {"url": url}
                ).fetchone()
                if blocked:
                    print(f"   🚫 Skipped (Blocklisted): {title}")
                    return "skipped"
        except Exception as e:
            print(f"   ⚠️ Blocklist check error: {e}")

        image_url = ""
        
        # Try campaign banner image first (most reliable)
        campaign_banner = soup.select_one('.campaign-banner img')
        if campaign_banner and campaign_banner.get('src'):
            src = campaign_banner['src']
            image_url = src if src.startswith('http') else self.BASE_URL + (src if src.startswith('/') else '/' + src)
        
        # Fallback to og:image
        if not image_url or any(x in image_url for x in BLACKLIST_IMAGES):
            meta_image = soup.find("meta", property="og:image")
            if meta_image: 
                image_url = meta_image.get("content", "")
        
        # Last resort: find largest image (excluding logos/icons)
        if not image_url or any(x in image_url for x in BLACKLIST_IMAGES):
            images = soup.find_all('img', src=True)
            for img in images:
                src = img['src']
                # More strict filtering
                if (not any(x in src.lower() for x in BLACKLIST_IMAGES + ['icon', 'logo', 'share']) 
                    and len(src) > 30  # Longer URLs are usually real images
                    and 'campaign' in src.lower()):  # Prefer campaign-related images
                    if src.startswith('http'):
                        image_url = src
                    else:
                        from urllib.parse import urljoin
                        image_url = urljoin(self.BASE_URL, src)
                    break

        # Raw Text for AI - Target the specific conditions container
        # Since the page is rendered (either by ZenRows or Selenium), we extract the left and right containers
        # using BeautifulSoup to support both Selenium and ZenRows modes natively without throwing NameErrors/AttributeErrors.
        raw_text = ""
        try:
            # Content areas
            left_el = (
                soup.select_one('.campaign-detail-text') or 
                soup.select_one('.campaign-detail') or 
                soup.select_one('.col-md-8') or 
                soup.select_one('.col-lg-8')
            )
            right_el = (
                soup.select_one('.container-right') or 
                soup.select_one('.campaign-startend-date') or 
                soup.select_one('.col-md-4') or 
                soup.select_one('.col-lg-4') or 
                soup.select_one('.campaign-sidebar')
            )

            # Heuristic for missing info (Participation, Dates)
            extra_parts = []
            targets = []
            for tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b', 'div', 'p', 'span']:
                for el in soup.find_all(tag_name):
                    t = el.get_text(strip=True)
                    if 0 < len(t) < 150 and any(kw in t for kw in ['KATILMAK İÇİN', 'KAMPANYA BAŞLANGIÇ', 'ÖDÜL GEÇERLİLİK']):
                        targets.append(el)

            added_parents = set()
            for el in targets:
                parent = el.parent
                if parent and parent.name in ['strong', 'b', 'span', 'p']:
                    if parent.parent:
                        parent = parent.parent
                
                if parent and parent not in added_parents:
                    parent_text = parent.get_text(separator="\n", strip=True)
                    if parent_text and not any(parent_text[:30] in x for x in extra_parts):
                        extra_parts.append(parent_text)
                        added_parents.add(parent)

            # Combine elements
            text_parts = []
            if extra_parts:
                text_parts.append("--- ÖNEMLİ BİLGİLER (KATILIM VE TARİHLER) ---\n\n" + "\n\n".join(extra_parts) + "\n\n--------------------------------------\n")
            
            left_text = left_el.get_text(separator="\n", strip=True) if left_el else ""
            right_text = right_el.get_text(separator="\n", strip=True) if right_el else ""
            
            if left_text:
                text_parts.append(left_text)
            if right_text and not any(right_text[:50] in x for x in text_parts):
                text_parts.append(right_text)
                
            raw_text = "\n\n".join(text_parts)
            
            # If BeautifulSoup didn't find enough and self.driver is active, use JS fallback
            if len(raw_text.strip()) < 100 and self.driver:
                print("   ⚠️ BS4 extracted too little, attempting JS fallback since browser driver is active...")
                raw_text_js = self.driver.execute_script("""
                    let text = "";
                    let extra = "";
                    const left = document.querySelector('.campaign-detail-text') || document.querySelector('.campaign-detail') || document.querySelector('.col-md-8') || document.querySelector('.col-lg-8');
                    const right = document.querySelector('.container-right') || document.querySelector('.campaign-startend-date') || document.querySelector('.col-md-4') || document.querySelector('.col-lg-4') || document.querySelector('.campaign-sidebar');
                    const elements = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6, strong, b, div, p, span'));
                    const targets = elements.filter(el => {
                        const t = el.innerText || "";
                        return t.length > 0 && t.length < 150 && (
                            t.includes('KATILMAK İÇİN') || 
                            t.includes('KAMPANYA BAŞLANGIÇ') || 
                            t.includes('ÖDÜL GEÇERLİLİK')
                        );
                    });
                    const addedParents = new Set();
                    targets.forEach(el => {
                        let parent = el.parentElement;
                        if (parent && (parent.tagName === 'STRONG' || parent.tagName === 'B' || parent.tagName === 'SPAN' || parent.tagName === 'P')) {
                            if (parent.parentElement) parent = parent.parentElement;
                        }
                        if (parent && !addedParents.has(parent)) {
                            const parentText = parent.innerText;
                            if (parentText && !extra.includes(parentText.substring(0, 30))) {
                                extra += "\\n\\n" + parentText;
                                addedParents.add(parent);
                            }
                        }
                    });
                    if (extra) text += "--- ÖNEMLİ BİLGİLER (KATILIM VE TARİHLER) ---\\n\\n" + extra + "\\n\\n--------------------------------------\\n\\n";
                    if (left && !text.includes(left.innerText.substring(0, 50))) text += left.innerText + "\\n\\n";
                    if (right && !text.includes(right.innerText.substring(0, 50))) text += right.innerText + "\\n\\n";
                    return text;
                """)
                if raw_text_js and len(raw_text_js.strip()) > 100:
                    raw_text = raw_text_js

            if raw_text:
                print(f"   ✨ Extracted {len(raw_text)} chars from content areas.")
            else:
                # Fallback to BeautifulSoup generic if both failed
                main_content = soup.select_one('.campaign-detail-text') or soup.select_one('.campaign-detail') or soup.find('div', class_=re.compile(r'detail|content|campaign'))
                raw_text = main_content.get_text(separator="\n", strip=True) if main_content else ""
                
        except Exception as e:
            print(f"   ⚠️ Text extraction failed: {e}")
            main_content = soup.select_one('.campaign-detail-text') or soup.select_one('.campaign-detail')
            raw_text = main_content.get_text(separator="\n", strip=True) if main_content else ""

        # Additional cleanup: remove any remaining references to other campaigns
        if raw_text:
            lines = raw_text.split('\n')
            filtered_lines = []
            skip_rest = False
            
            for line in lines:
                # Clean line for reliable Turkish matching
                line_lower = line.lower().replace('i̇', 'i').replace('ı', 'i')
                
                # If we hit "İlginizi Çekebilecek" or similar, skip rest
                if 'ilginizi çekebilecek' in line_lower or 'ilginizi cekebilecek' in line_lower or \
                   'diğer kampanyalar' in line_lower or 'diger kampanyalar' in line_lower or \
                   'benzer kampanyalar' in line_lower:
                    skip_rest = True
                    continue
                
                if not skip_rest:
                    filtered_lines.append(str(line))
            
            raw_text = '\n'.join(filtered_lines)

        # AI Parsing
        if self.ai_parser:
            print("   🧠 Analyzing with Gemini AI...")
            parser = get_golden_parser()
            ai_data = parser.parse_campaign(
                raw_html=raw_text, # Passing the extracted text to bypass aggressive cleaning
                bank_name="Denizbank",
                title=title,
                og_title=title,
                scraper_sector=None
            ) or {}
        else:
            print("   ⚠️ AI Parser unavailable, using basic extraction.")
            ai_data = {
                "title": title,
                "description": "",
                "sector": "Diğer",
                "start_date": None,
                "end_date": None,
                "conditions": [],  # type: ignore # pyre-ignore[16,6]
                "reward_text": None,
                "reward_value": None,
                "reward_type": None
            }

        slug_base = self._get_slug(ai_data.get('title') or title)
        slug = slug_base
        
        # Build conditions with participation info (like other scrapers)
        conditions_lines = []
        
        # Add participation info to conditions
        participation = ai_data.get('participation')
        if participation and participation not in ["Detayları İnceleyin", "Otomatik Katılım", "Otomatik katılım"]:  # type: ignore # pyre-ignore[16,6]
            pass  # participation field written separately to DB
        # Add eligible cards info
        eligible_cards_list = ai_data.get('cards', [])
        if eligible_cards_list:
            pass  # eligible_cards field written separately to DB
        # Add original conditions
        ai_conditions = ai_data.get('conditions', [])
        if isinstance(ai_conditions, list):
            conditions_lines.extend([str(c) for c in ai_conditions])  # type: ignore # pyre-ignore[16]
        
        # Convert eligible_cards list to string (max 255 chars)
        eligible_cards_str = ", ".join(eligible_cards_list) if eligible_cards_list else None
        if eligible_cards_str and len(eligible_cards_str) > 255:
            eligible_cards_str = eligible_cards_str[:255]  # type: ignore # pyre-ignore[16,6]
        
        campaign_data = {
            "title": ai_data.get('title') or title,
            "description": ai_data.get('description'),
            "ai_marketing_text": ai_data.get('ai_marketing_text') or ai_data.get('description') or title,
            "image_url": image_url,
            "tracking_url": url,
            "slug": slug,
            "start_date": ai_data.get('start_date'),
            "end_date": ai_data.get('end_date'),
            "is_active": True,
            "sector_id": self._resolve_sector_by_name(ai_data.get('sector')),
            "participation": participation,
            "conditions": "\n".join(conditions_lines), # type: ignore
            "eligible_cards": eligible_cards_str,
            "reward_text": ai_data.get('reward_text'),
            "reward_value": ai_data.get('reward_value'),
            "reward_type": ai_data.get('reward_type'),
            "clean_text": raw_text
        }

        return self._save_to_db(campaign_data, ai_data.get('brands', []))  # type: ignore # pyre-ignore[7]

    def _get_or_create_card(self):
        """Find or create Denizbank and DenizBonus card."""
        try:
            with self.engine.connect() as conn:
                # 1. Find or Create Bank
                result = conn.execute(text("SELECT id FROM banks WHERE slug = 'denizbank'")).fetchone()
                if result:
                    bank_id = result[0]
                else:
                    print("   🏦 Creating Bank: Denizbank")
                    result = conn.execute(text("""
                        INSERT INTO banks (name, slug, logo_url, is_active, created_at)
                        VALUES ('Denizbank', 'denizbank', 'https://www.denizbank.com/assets/img/logo.svg', true, NOW())
                        RETURNING id
                    """)).fetchone()
                    bank_id = result[0]
                    conn.commit()  # type: ignore # pyre-ignore[16]

                # 2. Find or Create Card
                result = conn.execute(text("SELECT id FROM cards WHERE slug = 'denizbonus'")).fetchone()
                if result:
                    self.card_id = result[0]
                else:
                    print("   💳 Creating Card: DenizBonus")
                    result = conn.execute(text("""
                        INSERT INTO cards (name, slug, bank_id, card_type, is_active, created_at)
                        VALUES ('DenizBonus', 'denizbonus', :bank_id, 'credit', true, NOW())
                        RETURNING id
                    """), {"bank_id": bank_id}).fetchone()
                    self.card_id = result[0]
                    conn.commit()  # type: ignore # pyre-ignore[16]
                    
                print(f"   ✅ Using Card ID: {self.card_id}")
        except Exception as e:
            print(f"   ❌ Failed to get/create card: {e}")
            raise e

    def _save_to_db(self, data: Dict[str, Any], brand_names: List[str] = None):
        if not hasattr(self, 'card_id') or not self.card_id:
            self._get_or_create_card()

        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=self.engine)
        db = SessionLocal()
        
        try:
            # 1. Blocklist check
            blocked = db.execute(
                text("SELECT id FROM campaign_blocklist WHERE url = :url"),
                {"url": data['tracking_url']}
            ).fetchone()
            if blocked:
                print(f"   🚫 Skipped (Blocklisted): {data['title']}")
                return "skipped"

            # Check if campaign already exists or generate new unique slug
            from sqlalchemy import func
            from src.utils.slug_generator import get_unique_slug
            
            existing = db.query(Campaign).filter(
                (Campaign.tracking_url == data['tracking_url']) | (func.lower(Campaign.title) == data['title'].lower()),
                Campaign.card_id == self.card_id
            ).first()
            
            if existing:
                campaign_slug = existing.slug
            else:
                campaign_slug = get_unique_slug(
                    title=data['title'],
                    db_session=db,
                    campaign_model=Campaign,
                    tracking_url=data['tracking_url'],
                    card_name="DenizBonus",
                    bank_name="Denizbank"
                )

            # 2. Prepare Campaign Object
            campaign = Campaign(
                card_id=self.card_id,
                sector_id=data.get('sector_id'),
                slug=campaign_slug,
                title=data.get('title'),
                description=data.get('description'),
                ai_marketing_text=data.get('ai_marketing_text'),
                reward_text=data.get('reward_text'),
                reward_value=data.get('reward_value'),
                reward_type=data.get('reward_type'),
                conditions=data.get('conditions'),
                eligible_cards=data.get('eligible_cards'),
                participation=data.get('participation'),
                image_url=data.get('image_url'),
                tracking_url=data.get('tracking_url'),
                is_active=True,
                clean_text=data.get('clean_text'),
                start_date=data.get('start_date'),
                end_date=data.get('end_date')
            )

            # 3. Use upsert_campaign for revival/quality
            campaign, op_status = upsert_campaign(db, campaign)
            db.commit()

            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title}")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title}")
            
            db.refresh(campaign)

            # 4. Handle Brands
            if brand_names:
                from src.services.brand_matcher import get_or_create_brands_list
                brand_ids = get_or_create_brands_list(db, brand_names, {}, data.get('sector_id'))
                for bid in brand_ids:
                    existing_link = db.query(CampaignBrand).filter(
                        CampaignBrand.campaign_id == campaign.id,
                        CampaignBrand.brand_id == bid
                    ).first()
                    if not existing_link:
                        db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                db.commit()

            return op_status
        except Exception as e:
            db.rollback()
            print(f"      ❌ DB Error: {e}")
            return "error"
        finally:
            db.close()

    def run(self, limit=1000):
        print("🚀 Starting Denizbank Hybrid Scraper...")
        if ZENROWS_API_KEY:
            print("   💎 Mode: Proxy API (ZenRows)")
        else:
            print("   🆓 Mode: Direct Selenium (STEALTH ENABLED)")
            
        try:
            from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
            from sqlalchemy.orm import sessionmaker  # type: ignore # pyre-ignore[21]
            SessionLocal = sessionmaker(bind=self.engine)
            db = SessionLocal()
            
            urls = self._fetch_campaign_list(limit=limit)
            print(f"   🎯 Processing {len(urls)} campaigns...")
            
            success_count = 0
            total_revived = 0
            skipped_count = 0
            failed_count = 0
            error_details = []
            
            for i, url in enumerate(urls, 1):
                try:
                    res = self._process_campaign(url)
                    if res == "saved":
                        success_count += 1  # type: ignore # pyre-ignore[58]
                    elif res == "revived":
                        total_revived += 1
                    elif res == "skipped":
                        skipped_count += 1  # type: ignore # pyre-ignore[58]
                    else:
                        failed_count += 1  # type: ignore # pyre-ignore[58]
                        error_details.append({"url": url, "error": f"Process returned {res}"})
                except Exception as e:
                    print(f"   ❌ Failed: {e}")
                    failed_count += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": url, "error": str(e)})
                
                # Sleep more if in free mode
                if not ZENROWS_API_KEY:
                    time.sleep(random.uniform(4, 8))  # Daha uzun ve rastgele
                    
            print(f"✅ Özet: {len(urls)} bulundu, {success_count} eklendi, {total_revived} canlandı, {skipped_count} atlandı, {failed_count} hata aldı.") # type: ignore
            
            status = "SUCCESS"
            if failed_count > 0:  # type: ignore # pyre-ignore[58]
                status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
                
            log_scraper_execution(
                db=db,
                scraper_name="denizbank",
                status=status,
                total_found=len(urls),
                total_saved=success_count,
                total_skipped=skipped_count,
                total_failed=failed_count,
                total_revived=total_revived,
                error_details={"errors": error_details} if error_details else None
            )
            db.close()  # type: ignore # pyre-ignore[16]
                    
        except Exception as e:
            print(f"❌ Scraper exception: {e}")
            from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
            from sqlalchemy.orm import sessionmaker  # type: ignore # pyre-ignore[21]
            SessionLocal = sessionmaker(bind=self.engine)
            db = SessionLocal()
            log_scraper_execution(
                db=db,
                scraper_name="denizbank",
                status="FAILED",
                total_found=0,
                total_saved=0,
                total_skipped=0,
                total_failed=1,
                error_details={"error": str(e)}
            )
            db.close()  # type: ignore # pyre-ignore[16]
        finally:
            self.close_driver()
            print("🏁 Scraper Finished.")

    def scrape_single_url(self, url):
        """Scrape a single campaign URL."""
        print(f"🚀 Starting Single URL Scrape: {url}")
        
        if ZENROWS_API_KEY:
            print("   💎 Mode: Proxy API (ZenRows)")
        else:
            print("   🆓 Mode: Direct Selenium (STEALTH ENABLED)")
            
        try:
            self.setup_driver()
            self._process_campaign(url)
            print("✅ Single scrape completed.")
        except Exception as e:
            print(f"❌ Single scrape failed: {e}")
        finally:
            self.close_driver()

if __name__ == "__main__":
    import argparse  # type: ignore # pyre-ignore[21]
    
    parser = argparse.ArgumentParser(description='Denizbank Scraper')
    parser.add_argument('--limit', type=int, help='Limit number of campaigns', default=1000)
    parser.add_argument('--url', type=str, help='Scrape a specific campaign URL')
    
    args = parser.parse_args()
    
    scraper = DenizbankScraper()
    
    if args.url:
        scraper.scrape_single_url(args.url)
    else:
        scraper.run(limit=args.limit)
