


import os
import time  # type: ignore # pyre-ignore[21]
import random  # type: ignore # pyre-ignore[21]
import re  # type: ignore # pyre-ignore[21]
import json  # type: ignore # pyre-ignore[21]
import requests  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from dotenv import load_dotenv  # type: ignore # pyre-ignore[21]
import sys

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Database
from sqlalchemy import create_engine, text  # type: ignore # pyre-ignore[21]
from sqlalchemy.dialects.postgresql import JSONB  # type: ignore # pyre-ignore[21]

# AI
from services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]
from services.brand_normalizer import cleanup_brands  # type: ignore # pyre-ignore[21]
from utils.scraper_utils import is_url_blocked  # type: ignore

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
        options.page_load_strategy = 'normal'  # 'eager' yerine 'normal' - daha güvenilir
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--disable-web-security")
        
        # Headless Mode (opsiyonel - bot detection riski var)
        # options.add_argument('--headless=new')  # Eğer headless çalıştırmak istersen
        
        # Gerçek User Agent
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            
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
                    return response.text  # type: ignore # pyre-ignore[7]
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
                self.driver.get(self.BASE_URL)
                time.sleep(random.uniform(2.0, 4.0))
            
            # Hedef sayfaya git
            self.driver.get(url)
            
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
        # Database Pre-check (Skip Logic)
        try:
            with self.engine.connect() as conn:
                existing = conn.execute(
                    text("SELECT id FROM campaigns WHERE tracking_url = :url"),
                    {"url": url}
                ).fetchone()
                if existing:
                    # Try to get title from DB if possible
                    existing_title = conn.execute(
                        text("SELECT title FROM campaigns WHERE tracking_url = :url"),
                        {"url": url}
                    ).fetchone()
                    title_log = existing_title[0] if existing_title else url
                    print(f"   ⏭️ Skipped (Already exists): {title_log}")
                    return "skipped"  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"   ⚠️ DB Pre-check error: {e}")

        print(f"\n📄 Processing: {url}")
        html = self._fetch_html(url)
        if not html:
            return "skipped"  # type: ignore # pyre-ignore[7]

        soup = BeautifulSoup(html, 'html.parser')

        # Context Extraction (Title & Image)
        title = "Kampanya Detayı"
        meta_title = soup.find("meta", property="og:title")
        if meta_title: title = meta_title.get("content", "").strip()
        else:
            h1 = soup.find('h1')
            if h1: title = h1.get_text(strip=True)

        # Blocklist check (move here to get title for log)
        try:
            with self.engine.connect() as conn:
                blocked = conn.execute(
                    text("SELECT id FROM campaign_blocklist WHERE url = :url"),
                    {"url": url}
                ).fetchone()
                if blocked:
                    print(f"   🚫 Skipped (Blocklisted): {title}")
                    return "skipped"  # type: ignore # pyre-ignore[7]
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
        # Since it uses a custom scrollbar (Perfect Scrollbar), 
        # we use JS to get innerText to ensure we get everything inside.
        raw_text = ""
        try:
            raw_text_js = self.driver.execute_script("""
                const el = document.querySelector('.campaign-detail-text');
                return el ? el.innerText : "";
            """)
            if raw_text_js and len(raw_text_js.strip()) > 100:
                print(f"   ✨ Extracted {len(raw_text_js)} chars via JS from .campaign-detail-text")
                raw_text = raw_text_js
            else:
                # Fallback to BeautifulSoup if JS fails or returns too little
                main_content = soup.select_one('.campaign-detail-text') or soup.select_one('.campaign-detail')
                if not main_content:
                    # Fallback to generic content extraction
                    main_content = soup.find('div', class_=re.compile(r'detail|content|campaign'))
                
                raw_text = main_content.get_text(separator="\n", strip=True) if main_content else ""
        except Exception as e:
            print(f"   ⚠️ JS text extraction failed: {e}")
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
            ai_data = self.ai_parser.parse_campaign_data(
                raw_text=raw_text,
                title=title,
                bank_name="Denizbank",
                card_name="DenizBonus"
            )
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

    def _save_to_db(self, data, brands=None):
        if not hasattr(self, 'card_id') or not self.card_id:
            self._get_or_create_card()

        campaign_id = None
        try:
            with self.engine.begin() as conn:
                existing = conn.execute(
                    text("SELECT id FROM campaigns WHERE tracking_url = :url"),
                    {"url": data['tracking_url']}  # type: ignore # pyre-ignore[16,6]
                ).fetchone()

                if existing:
                    print(f"   ⏭️ Skipped (Already exists): {data['title']}")  # type: ignore # pyre-ignore[16,6]
                    return "skipped"

                # Check Blocklist using raw SQL since we are in a connection
                blocked = conn.execute(
                    text("SELECT id FROM campaign_blocklist WHERE url = :url"),
                    {"url": data['tracking_url']}
                ).fetchone()
                
                if blocked:
                    print(f"   🚫 Skipped (Blocklisted): {data['title']}")
                    return "skipped"
                try:
                    result = conn.execute(
                        text("""
                            INSERT INTO campaigns (
                                title, description, slug, image_url, tracking_url, is_active, 
                                sector_id, card_id, start_date, end_date, conditions, participation,
                                eligible_cards, reward_text, reward_value, reward_type,
                                created_at, updated_at
                            )
                            VALUES (
                                :title, :description, :slug, :image_url, :tracking_url, true, 
                                :sector_id, :card_id, :start_date, :end_date, :conditions, :participation,
                                :eligible_cards, :reward_text, :reward_value, :reward_type,
                                NOW(), NOW()
                            )
                            RETURNING id
                        """), 
                        {**data, "card_id": self.card_id}
                    )
                    campaign_id = result.fetchone()[0]
                except Exception as e:
                    if "unique constraint \"campaigns_slug_key\"" in str(e).lower():
                        print(f"   ⚠️ Slug collision detected, retrying with bank suffix...")
                        data['slug'] = f"{data['slug']}-denizbank"
                        result = conn.execute(
                            text("""
                                INSERT INTO campaigns (
                                    title, description, slug, image_url, tracking_url, is_active, 
                                    sector_id, card_id, start_date, end_date, conditions, participation,
                                    eligible_cards, reward_text, reward_value, reward_type,
                                    created_at, updated_at
                                )
                                VALUES (
                                    :title, :description, :slug, :image_url, :tracking_url, true, 
                                    :sector_id, :card_id, :start_date, :end_date, :conditions, :participation,
                                    :eligible_cards, :reward_text, :reward_value, :reward_type,
                                    NOW(), NOW()
                                )
                                RETURNING id
                            """), 
                            {**data, "card_id": self.card_id}
                        )
                        campaign_id = result.fetchone()[0]
                    else:
                        raise e
                
                # Save brands (like other scrapers)
                if brands and campaign_id:
                    clean_brand_list = cleanup_brands(brands)
                    
                    for brand_name in clean_brand_list:
                        # Get or create brand
                        brand_result = conn.execute(
                            text("SELECT id FROM brands WHERE name = :name"),
                            {"name": brand_name}
                        ).fetchone()
                        
                        if brand_result:
                            brand_id = brand_result[0]
                        else:
                            # Create brand with slug
                            import re  # type: ignore # pyre-ignore[21]
                            slug = re.sub(r'[^a-z0-9]+', '-', brand_name.lower()).strip('-')
                            slug = f"{slug}-{int(time.time())}"
                            
                            brand_result = conn.execute(
                                text("""
                                    INSERT INTO brands (name, slug, is_active, created_at)
                                    VALUES (:name, :slug, true, NOW())
                                    RETURNING id
                                """),
                                {"name": brand_name, "slug": slug}
                            )
                            brand_id = brand_result.fetchone()[0]
                            print(f"      ✨ Created Brand: {brand_name}")
                        
                        # Link brand to campaign (check if exists first)
                        existing_link = conn.execute(
                            text("""
                                SELECT 1 FROM campaign_brands 
                                WHERE campaign_id = :campaign_id AND brand_id = CAST(:brand_id AS uuid)
                            """),
                            {"campaign_id": campaign_id, "brand_id": brand_id}
                        ).fetchone()
                        
                        if not existing_link:
                            conn.execute(
                                text("""
                                    INSERT INTO campaign_brands (campaign_id, brand_id)
                                    VALUES (:campaign_id, CAST(:brand_id AS uuid))
                                """),
                                {"campaign_id": campaign_id, "brand_id": brand_id}
                            )
                            print(f"      🔗 Linked Brand: {brand_name}")
                            
            return True
        except Exception as e:
            print(f"      ❌ Detail error: {e}")
            return False

    def run(self, limit=20):
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
            skipped_count = 0
            failed_count = 0
            error_details = []
            
            for i, url in enumerate(urls, 1):
                try:
                    res = self._process_campaign(url)
                    if res == "saved":
                        success_count += 1  # type: ignore # pyre-ignore[58]
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
                    
            print(f"✅ Özet: {len(urls)} bulundu, {success_count} eklendi, {str(skipped_count) + ' ' + str(failed_count)} atlandı/hata aldı.") # type: ignore
            
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
    parser.add_argument('--limit', type=int, help='Limit number of campaigns', default=20)
    parser.add_argument('--url', type=str, help='Scrape a specific campaign URL')
    
    args = parser.parse_args()
    
    scraper = DenizbankScraper()
    
    if args.url:
        scraper.scrape_single_url(args.url)
    else:
        scraper.run(limit=args.limit)
