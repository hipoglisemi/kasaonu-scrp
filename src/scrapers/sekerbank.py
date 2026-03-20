
import os
import time
import random
import re
import json
import sys
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urljoin

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.orm import Session # type: ignore
from sqlalchemy.exc import IntegrityError # type: ignore
from bs4 import BeautifulSoup # type: ignore
from dotenv import load_dotenv # type: ignore
from selenium import webdriver # type: ignore
from selenium.webdriver.chrome.webdriver import WebDriver # type: ignore
from selenium.webdriver.chrome.service import Service # type: ignore
from webdriver_manager.chrome import ChromeDriverManager # type: ignore
from selenium_stealth import stealth # type: ignore
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore

# Database & Services
from src.database import get_db_session # type: ignore
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand # type: ignore
from src.services.ai_parser import AIParser # type: ignore
from src.utils.logger_utils import log_scraper_execution # type: ignore
from src.utils.scraper_utils import should_skip_campaign # type: ignore

try:
    from pyvirtualdisplay import Display # type: ignore
    HAS_VIRTUAL_DISPLAY = True
except ImportError:
    HAS_VIRTUAL_DISPLAY = False
    def Display(*args, **kwargs): return None

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

class SekerbankScraper:
    BASE_URL = "https://www.sekerbank.com.tr"
    SOURCES = [
        {
            "name": "Şekerbank Bonus",
            "url": "https://www.sekerbank.com.tr/bireysel/kampanyalar/kart-kampanyalari",
            "default_card": "Şekerbank Bonus"
        },
        {
            "name": "Şekerbank Diamond",
            "url": "https://www.sekerbank.com.tr/bireysel/kampanyalar/diamond-kart-kampanyalari",
            "default_card": "Şekerbank Diamond"
        }
    ]

    def __init__(self):
        self.driver: Optional[WebDriver] = None
        self.display: Optional[Any] = None
        self.db: Optional[Session] = None
        self.parser = AIParser()
        
        # Caches
        self.bank_cache: Optional[Bank] = None
        self.card_cache: Dict[str, Card] = {}
        self.sector_cache: Dict[str, Sector] = {}
        self.brand_cache: Dict[str, Brand] = {}

    def setup_driver(self):
        """Initialize Selenium with Stealth Mode."""
        if self.driver:
            return

        if sys.platform.startswith('linux') and HAS_VIRTUAL_DISPLAY:
            try:
                self.display = Display(visible=0, size=(1920, 1080))
                if self.display:
                    self.display.start() # type: ignore # pyre-ignore[16]
            except Exception as e:
                print(f"⚠️ Failed to start virtual display: {e}")

        print("   🔌 Initializing Browser Driver (Chrome + Stealth)...")
        options = webdriver.ChromeOptions()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        
        # Check if running in a container or if headless is preferred
        if os.getenv("DOCKER_MODE") == "true" or os.environ.get("HEADLESS") == "1":
            options.add_argument('--headless=new')

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            
            stealth(self.driver,
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
            raise e

    def close_driver(self):
        driver = self.driver
        if driver:
            print("   🛑 Closing Browser...")
            try:
                self.driver.close() # type: ignore # pyre-ignore[16]
            except:
                pass
            self.driver = None
            
        display = self.display
        if display:
            try:
                display.stop()
            except:
                pass
            self.display = None

    def run(self, limit: Optional[int] = None, force: bool = False):
        print(f"🚀 Starting Şekerbank Scraper...")
        try:
            self.db = get_db_session()
            self._load_cache()
            self.setup_driver()

            for source in self.SOURCES:
                print(f"\n🌍 Processing Source: {source['name']}")
                if self.driver:
                    self._process_source(source, limit=limit, force=force)

        except Exception as e:
            print(f"❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.close_driver()
            if self.db:
                self.db.close() # type: ignore # pyre-ignore[16]

    def _load_cache(self):
        """Pre-load essential data from DB to reduce queries."""
        if not self.db: return # type: ignore

        bank = self.db.query(Bank).filter(Bank.slug == "sekerbank").first() # type: ignore # pyre-ignore[16]
        if not bank:
            bank = Bank(name="Şekerbank", slug="sekerbank", is_active=True)  # type: ignore
            if self.db:
                self.db.add(bank)  # type: ignore
                self.db.commit()  # type: ignore
        self.bank_cache = bank
        if not self.db: return # type: ignore
        for c in self.db.query(Card).filter(Card.bank_id == bank.id).all(): # type: ignore # pyre-ignore[16]
            self.card_cache[c.name.lower()] = c
            
        for s in self.db.query(Sector).all(): # type: ignore # pyre-ignore[16]
            self.sector_cache[s.slug] = s # type: ignore
            self.sector_cache[s.name.lower()] = s # type: ignore
            
        for b in self.db.query(Brand).all(): # type: ignore # pyre-ignore[16]
            self.brand_cache[b.name.lower()] = b # type: ignore

    def _process_source(self, source: Dict, limit: Optional[int] = None, force: bool = False):
        """Navigate to list page, load all campaigns, and process them."""
        driver = self.driver
        if not driver:
            return
        driver.get(source['url'])
        time.sleep(3)

        # Accept cookies if the popup appears
        try:
            cookie_btn = driver.find_element(By.ID, "onetrust-accept-btn-handler")
            cookie_btn.click()
            time.sleep(1)
        except:
            pass

        # "Daha Fazla Görüntüle" button logic
        print("   ⏳ Loading all campaigns (Scroll & Click)...")
        click_count = 0
        while True:
            try:
                # Scroll down to make button visible
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                # Look for the button
                show_more = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btn--showmore"))
                )
                
                if show_more.is_displayed():
                    driver.execute_script("arguments[0].click();", show_more)
                    click_count += 1
                    time.sleep(3)
                else:
                    break
            except Exception:
                # Button not found or not clickable anymore
                break
        
        if click_count > 0:
            print(f"   🖱️ Clicked 'Show More' {click_count} times.")

        # Find all card links first
        print("   🔍 Collecting campaign cards and filtering active ones...")
        all_links = driver.find_elements(By.CSS_SELECTOR, "a.btn--link")
        
        # Determine the starting Y coordinate of 'Geçmiş Kampanyalar' section
        past_y = 999999
        try:
            past_heading = driver.find_element(By.XPATH, "//h2[contains(text(), 'Geçmiş Kampanyalar')]")
            past_y = past_heading.location['y']
            print(f"   ⚠️ 'Geçmiş Kampanyalar' section starts at Y={past_y}. Filtering...")
        except:
            pass

        link_elements = []
        found_items: List[Dict[str, str]] = [] # Explicit typing
        for l in all_links:
            try:
                if l.location['y'] < past_y:
                    link_elements.append(l)
            except:
                continue

        print(f"   🎯 Found {len(link_elements)} active campaign cards to process.")

        # Tüm sayfayı scroll et — lazy-load görseller için
        print("   📸 Lazy loading görseller için tam sayfa scroll ediliyor...")
        try:
            scroll_height = driver.execute_script("return document.body.scrollHeight")
            for pos in range(0, int(scroll_height), 400):
                driver.execute_script(f"window.scrollTo(0, {pos})")
                time.sleep(0.05)
            driver.execute_script(f"window.scrollTo(0, {scroll_height})")
            time.sleep(2.5)  # Görsellerin yüklenmesi için bekle
            driver.execute_script("window.scrollTo(0, 0)")
        except Exception:
            pass

        # TEK JS çağrısıyla href → imgUrl haritası çek
        img_map: Dict[str, str] = {}
        try:
            js_result = driver.execute_script("""
                var results = {};
                var links = document.querySelectorAll('a.btn--link');
                links.forEach(function(link) {
                    var href = link.href || link.getAttribute('href');
                    if (!href) return;
                    // Kart container'ı bul (NextJS ve Bootstrap uyumlu iteratif parent araması)
                    var card = link;
                    var foundCard = null;
                    for (var k = 0; k < 5; k++) {
                        if (card.parentElement) card = card.parentElement;
                        if (card && card.querySelector('img')) {
                            foundCard = card;
                            break;
                        }
                    }
                    card = foundCard || card;
                    var imgUrl = '';
                    if (card) {
                        // Tüm img elementleri dene
                        var imgs = card.querySelectorAll('img');
                        for (var i = 0; i < imgs.length; i++) {
                            var imgInfo = imgs[i];
                            var src = imgInfo.getAttribute('src') 
                                   || imgInfo.src 
                                   || imgInfo.dataset.src
                                   || imgInfo.getAttribute('data-lazy');
                            if (src && !src.startsWith('data:') && src.indexOf('logo') === -1) {
                                imgUrl = src;
                                break;
                            }
                        }
                    }
                    results[href] = imgUrl || '';
                });
                return results;
            """)
            if js_result and isinstance(js_result, dict):
                img_map = js_result
                non_empty = sum(1 for v in img_map.values() if v)
                print(f"   🖼️  JS img_map: {len(img_map)} kart, {non_empty} görsel bulundu")
        except Exception as e:
            print(f"   ⚠️ JS img_map hatası: {e}")

        for idx, link_el in enumerate(link_elements):
            try:
                href = link_el.get_attribute('href') or ''
                if not href:
                    continue
                url = urljoin(self.BASE_URL, href)

                # Süresi dolmuş kontrolü (kısa yol, Selenium element text)
                try:
                    card_text = driver.execute_script(
                        "return (arguments[0].closest('.col-xs-12,.col-sm-6,.col-md-4,[class*=\"col-\"]') || arguments[0].parentElement || arguments[0]).textContent.toLowerCase();",
                        link_el
                    ) or ""
                    if "sona ermiştir" in card_text or "kampanya süresi dolmuştur" in card_text:
                        continue
                except Exception:
                    pass

                # Haritadan görsel al
                img_url = img_map.get(href, '') or ''
                if img_url and not img_url.startswith('http'):
                    img_url = urljoin(self.BASE_URL, img_url)

                # Avoid duplicates
                if not any(item['url'] == url for item in found_items):
                    found_items.append({
                        'url': url,
                        'list_image': img_url
                    })
                    if len(found_items) % 5 == 0:
                        print(f"      📸 Collected {len(found_items)} campaigns...")
            except Exception:
                continue

        print(f"   ✅ Collected {len(found_items)} active campaigns for {source['name']}.")
        
        # Ensure correct slicing type for IDE
        if isinstance(limit, int) and limit > 0:
            found_items = found_items[0:limit] # type: ignore # pyre-ignore[16]

        success_count = 0
        skipped_count = 0
        failed_count = 0

        for i, item in enumerate(found_items, 1):
            url = item['url']
            list_image = item['list_image']
            print(f"   [{i}/{len(found_items)}] {url}")
            try:
                res = self._scrape_detail(url, source, list_image=list_image, force=force)
                if res == "saved":
                    success_count += 1
                elif res == "skipped":
                    skipped_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                print(f"      ❌ Detail Error: {e}")
                failed_count += 1
            
            # Small random delay to be respectful
            time.sleep(random.uniform(1, 2))

        log_scraper_execution(
            db=self.db,
            scraper_name=f"sekerbank_{source['default_card'].lower().replace(' ', '_')}",
            status="SUCCESS" if failed_count == 0 else "PARTIAL",
            total_found=len(found_items),
            total_saved=success_count,
            total_skipped=skipped_count,
            total_failed=failed_count
        )

    def _scrape_detail(self, url: str, source: Dict, list_image: str = "", force: bool = False) -> str:
        """Scrape campaign details, images and use AI to parse metadata."""
        if not force and self.db:
            # Blocklist check
            from src.utils.scraper_utils import is_url_blocked  # type: ignore
            if is_url_blocked(self.db, url):
                print(f"      🚫 Skipped (Blocklisted): {url}")
                return "skipped"

            # Existing campaign check — görsel eksikse güncelle
            existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore
            if existing:
                existing_img = existing.image_url  # type: ignore
                is_placeholder = (
                    not existing_img
                    or existing_img.strip() == ''
                    or existing_img.startswith("/placeholders/")
                    or "logo" in existing_img.lower()
                    or "kartavantaj" in existing_img.lower()
                )
                if not is_placeholder:
                    print(f"      ⏭️ Skipped (Already exists): {existing.title}")  # type: ignore
                    return "skipped"
                print(f"      🔄 Görsel eksik/geçersiz, güncelleniyor: {existing.title}")

        driver = self.driver
        if not driver:
            return "failed"

        driver.get(url)
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Extraction
        title_el = soup.select_one('h1')
        title = title_el.get_text(strip=True) if title_el else "Şekerbank Kampanya"

        image_url = ""
        image_el = soup.select_one('.slick-active img')
        if not image_el:
            image_el = soup.select_one('main img')
        if not image_el:
            image_el = soup.select_one('.img-responsive')
        
        if image_el:
            image_url = self._extract_best_image(image_el)
        
        # Fallback to list image if detail image is missing or still a placeholder
        is_placeholder = not image_url or any(x in image_url.lower() for x in ["placeholder", "default", "logo", "bank-bg", "banka-ill"])
        if is_placeholder:
            image_url = list_image

        # Eğer mevcut kampanyada sadece görsel güncelleme yapıyorsak (is_placeholder path'i) — AI parse gereksiz
        if not force and self.db:
            upd_existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore
            if upd_existing and image_url:
                upd_existing.image_url = image_url  # type: ignore
                upd_existing.updated_at = datetime.utcnow()  # type: ignore
                self.db.commit()  # type: ignore
                print(f"      ✅ Görsel güncellendi: {image_url[:60]}")
                return "skipped"

        # Content/Details - Extract from MAIN as Next.js doesn't use stable classes for detail blocks
        content_el = soup.find('main')
        if not content_el:
            content_el = soup.select_one('.campaign-detail__content') or soup.find('body')
            
        # Get text but exclude header/footer if possible
        # Use BeautifulSoup to clean and get structured text for AI
        soup_content = BeautifulSoup(str(content_el), 'html.parser') if content_el else BeautifulSoup("", 'html.parser')
        raw_text = soup_content.get_text(separator='\n', strip=True)

        if len(raw_text) < 200:
            print(f"      ❌ Content too short ({len(raw_text)} chars), skipping details.")
            return "skipped"

        # AI Parse
        print(f"      🧠 AI Parsing details ({len(raw_text)} chars collected)...")
        ai_data = self.parser.parse_campaign_data(
            raw_text=raw_text,
            title=title,
            bank_name="sekerbank",
            card_name=source['default_card'],
            tracking_url=url,
            force=force
        )

        if not ai_data:
            print("      ❌ AI parsing failed.")
            return "error"

        # Save to DB
        self._save_campaign(ai_data, url, image_url, source['default_card'])
        print(f"      ✅ Saved: {ai_data['title']}")
        return "saved"

    def _save_campaign(self, data: Dict, url: str, image_url: str, default_card_name: str):
        """Save structured data and linked entities to the database."""
        # Primary card for the relationship
        primary_card = self._get_or_create_card(default_card_name)
        
        # Sector
        sector_slug = data.get("sector", "diger")
        sector = self._get_sector(sector_slug)
        
        # Brands
        brand_ids = self._get_or_create_brands(data.get("brands", []), sector.id if sector else None)
        
        # SEO Slug (Standard format: title-hashed-url)
        text_for_slug = data.get("title", "").lower()
        # Turkish character normalizing
        replacements = {'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c'}
        for tr, en in replacements.items():
            text_for_slug = text_for_slug.replace(tr, en)
        
        slug_base = re.sub(r'[^a-z0-9-]', '-', text_for_slug)
        slug_base = re.sub(r'-+', '-', slug_base).strip('-')
        
        # Ensure slug_base is string (IDE fix)
        slug_base_str = str(slug_base)
        url_hash_full = hashlib.md5(url.encode()).hexdigest()
        url_hash = str(url_hash_full)[0:8] # type: ignore
        final_slug = f"{slug_base_str}-{url_hash}"

        # Clean reward type
        reward_type = (data.get("reward_type") or "discount").lower()
        if reward_type not in ["cashback", "points", "discount", "installment"]:
            reward_type = "discount"

        # Campaign Object
        campaign = Campaign(  # type: ignore
            card_id=primary_card.id if primary_card else None,  # type: ignore
            sector_id=sector.id if sector else None,  # type: ignore
            title=data.get("title"),  # type: ignore
            slug=final_slug,  # type: ignore
            description=data.get("description"),  # type: ignore
            conditions="\n".join(data.get("conditions", [])),  # type: ignore
            start_date=data.get("start_date"),  # type: ignore
            end_date=data.get("end_date"),  # type: ignore
            reward_type=reward_type,  # type: ignore
            reward_value=data.get("reward_value"),  # type: ignore
            reward_text=data.get("reward_text"),  # type: ignore
            
            # Additional metadata
            ai_marketing_text=data.get("ai_marketing_text") or data.get("description"),  # type: ignore
            participation=data.get("participation"),  # type: ignore
            eligible_cards=", ".join(data.get("cards", [])),  # type: ignore
            category=data.get("category"),  # type: ignore
            clean_text=data.get("_clean_text"),  # type: ignore
            
            tracking_url=url,  # type: ignore
            image_url=image_url,  # type: ignore
            is_active=True,  # type: ignore
            affiliate_network="sekerbank"  # type: ignore
        )
        
        try:
            if not self.db: return # type: ignore
            self.db.add(campaign) # type: ignore # pyre-ignore[16]
            self.db.commit() # type: ignore # pyre-ignore[16]
            
            # Map Brands
            for bid in brand_ids:
                try:
                    cb = CampaignBrand(campaign_id=campaign.id, brand_id=bid) # type: ignore # pyre-ignore[16]
                    if self.db:
                        self.db.add(cb) # type: ignore # pyre-ignore[16]
                except Exception:
                    if self.db:
                        self.db.rollback() # type: ignore # pyre-ignore[16]
            if self.db:
                self.db.commit() # type: ignore # pyre-ignore[16]
        except Exception as e:
            print(f"      ❌ Saving Error: {e}")
            if self.db:
                self.db.rollback() # type: ignore # pyre-ignore[16]

    def _get_or_create_card(self, name: str) -> Card:
        """Helper to get card by name (caching included)."""
        key = name.lower()
        if key in self.card_cache:
            return self.card_cache[key]
        
        if not self.db or not self.bank_cache:
             return Card(name=name, slug=name.lower())  # type: ignore

        bank_instance = self.bank_cache
        bank_id = bank_instance.id # type: ignore # pyre-ignore[16]
        
        card = self.db.query(Card).filter( # type: ignore # pyre-ignore[16]
            Card.bank_id == bank_id,
            Card.name == name
        ).first()
        
        if not card:
            card = Card(  # type: ignore
                bank_id=bank_id,  # type: ignore
                name=name,  # type: ignore
                slug=name.lower().replace(" ", "-"),  # type: ignore
                is_active=True  # type: ignore
            )
            if self.db:
                self.db.add(card)  # type: ignore
                self.db.flush()  # type: ignore
            
        self.card_cache[key] = card
        return card

    def _get_sector(self, slug: str) -> Optional[Sector]:
        """Map sector slug to Sector entity."""
        if not slug:
            return self.sector_cache.get("diger")
        
        return self.sector_cache.get(slug.lower()) or self.sector_cache.get("diger")

    def _get_or_create_brands(self, names: List[str], sector_id: Optional[int]) -> List[Any]:
        """Normalize and match/create brands found in text using shared matcher."""
        from src.services.brand_matcher import get_or_create_brands_list
        if not self.db:
            return []
        return get_or_create_brands_list(self.db, names, self.brand_cache, sector_id)

    def _extract_best_image(self, img_el) -> str:
        """Extract higher quality or non-placeholder image from srcset or data attributes."""
        if not img_el:
            return ""
            
        # Preference: 1. srcset (usually contains high-res), 2. data-src/data-original, 3. src
        candidates = []
        
        # 1. Try to parse srcset (e.g., "url 1x, url 2x")
        srcset = img_el.get('srcset')
        if srcset:
            parts = [p.strip().split(' ')[0] for p in srcset.split(',')]
            candidates.extend(parts)
            
        # 2. Try data attributes
        for attr in ['data-src', 'data-original', 'data-lazy', 'data-srcset']:
            val = img_el.get(attr)
            if val:
                candidates.append(val)
                
        # 3. Add default src
        src = img_el.get('src')
        if src:
            candidates.append(src)
            
        # Filter and prioritize
        for candidate in candidates:
            if not candidate or candidate.startswith('data:'):
                continue
            # Skip if common placeholder or tiny icon
            lower_c = candidate.lower()
            is_generic = any(x in lower_c for x in ["placeholder", "default.png", "bank-bg", "banka-ill", "loading"])
            if is_generic and len(candidates) > 1:
                continue
                
            full_url = urljoin(self.BASE_URL, candidate)
            # Accept any image from sekerbank domain or an absolute https URL
            if "sekerbank.com.tr" in full_url or full_url.startswith("https://"):
                return full_url
                
        # Default back to the first available non-empty candidate if nothing ideal found
        if candidates:
            first = next((c for c in candidates if c and not c.startswith('data:')), None)
            return urljoin(self.BASE_URL, first) if first else ""
        return ""

    def _extract_best_image_selenium(self, img_el) -> str:
        """Selenium version: Extract higher quality or non-placeholder image from srcset or data attributes."""
        if not img_el:
            return ""
            
        candidates = []
        
        # 1. Try srcset
        srcset = img_el.get_attribute('srcset')
        if srcset:
            parts = [p.strip().split(' ')[0] for p in srcset.split(',')]
            candidates.extend(parts)
            
        # 2. Try various data attributes common in lazy-loaders
        for attr in ['data-src', 'data-original', 'data-lazy', 'data-srcset', 'data-echo']:
            val = img_el.get_attribute(attr)
            if val:
                candidates.append(val)
                
        # 3. Add default src
        src = img_el.get_attribute('src')
        if src:
            candidates.append(src)
            
        # Filter and prioritize
        for candidate in candidates:
            if not candidate or candidate.startswith('data:'):
                continue
            # Skip common placeholders
            lower_c = candidate.lower()
            is_generic = any(x in lower_c for x in ["placeholder", "default.png", "bank-bg", "banka-ill", "loading", "base64"])
            if is_generic and len(candidates) > 1:
                continue
                
            full_url = urljoin(self.BASE_URL, candidate)
            # Accept any image from sekerbank domain or absolute https URL
            if "sekerbank.com.tr" in full_url or full_url.startswith("https://"):
                return full_url
                
        if candidates:
            first = next((c for c in candidates if c and not c.startswith('data:')), None)
            return urljoin(self.BASE_URL, first) if first else ""
        return ""

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit campaigns to process")
    parser.add_argument("--force", action="store_true", help="Force update existing records")
    args = parser.parse_args()
    
    scraper = SekerbankScraper()
    scraper.run(limit=args.limit, force=args.force)
