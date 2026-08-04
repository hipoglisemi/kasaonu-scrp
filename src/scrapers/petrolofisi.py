import os
import time
import random
import re
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from urllib.parse import urljoin

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sqlalchemy.orm import Session # type: ignore
from bs4 import BeautifulSoup # type: ignore
from dotenv import load_dotenv # type: ignore
from selenium import webdriver # type: ignore
from selenium.webdriver.chrome.webdriver import WebDriver # type: ignore
from selenium_stealth import stealth # type: ignore
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore

# Database & Services
from src.database import get_db_session # type: ignore
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand # type: ignore
from src.services.ai_parser import AIParser # type: ignore
from src.services.brand_matcher import get_or_create_brands_list # type: ignore
from src.services.ai_parser_golden import parse_api_campaign  # type: ignore
from src.utils.logger_utils import log_scraper_execution # type: ignore
from src.utils.scraper_utils import upsert_campaign, is_url_blocked # type: ignore
from src.utils.slug_generator import get_unique_slug # type: ignore

load_dotenv()

class PetrolOfisiScraper:
    BASE_URL = "https://www.petrolofisi.com.tr"
    TARGET_URL = "https://www.petrolofisi.com.tr/kampanyalar"
    SOURCE_NAME = "Petrol Ofisi"
    
    def __init__(self):
        self.driver: Optional[WebDriver] = None
        self.db: Optional[Session] = None
        self.parser = AIParser()
        
        # Caches
        self.bank_cache: Optional[Bank] = None
        self.card_cache: Dict[str, Card] = {}
        self.brand_cache: Dict[str, Brand] = {}

    def _clean_campaign_title(self, title: str) -> str:
        if not title:
            return ""
        cleaned = re.sub(r'_(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)(-[A-Za-zÇĞİÖŞÜçğıöşü]+)?\s*\d{4}', '', title, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+\d{4}', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+202\d$', '', cleaned)
        cleaned = re.sub(r'\s+Kampanyası$', '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def setup_driver(self):
        """Initialize Selenium with Stealth Mode."""
        if self.driver:
            return

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
        options.page_load_strategy = 'eager' # Don't wait for all assets to load/renderer to be 100% done
        
        if os.getenv("DOCKER_MODE") == "true" or os.environ.get("HEADLESS") == "1":
            options.add_argument('--headless=new')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-setuid-sandbox')
            options.add_argument('--disable-software-rasterizer')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--no-sandbox')

        # Add a small delay before starting driver to ensure Xvfb is ready
        time.sleep(2)
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(90) # Increase timeout for slow CI loads
        
        stealth(self.driver,
                languages=["tr-TR", "tr"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
                )

    def _get_or_create_bank(self, db: Session) -> Bank:
        if self.bank_cache:
            return self.bank_cache
            
        bank = db.query(Bank).filter(Bank.slug == "petrol-ofisi").first()
        if not bank:
            bank = Bank(
                name="Petrol Ofisi",
                slug="petrol-ofisi",
                logo_url="https://www.petrolofisi.com.tr/assets/images/logo.png",
                is_active=True
            )
            db.add(bank)
            db.commit()
            db.refresh(bank)
        self.bank_cache = bank
        return bank

    def _get_or_create_card(self, db: Session, bank_id: int) -> Card:
        slug = "petrol-ofisi-kart"
        if slug in self.card_cache:
            return self.card_cache[slug]
            
        card = db.query(Card).filter(Card.slug == slug).first()
        if not card:
            card = Card(
                bank_id=bank_id,
                name="Petrol Ofisi Kart",
                slug=slug,
                is_active=True
            )
            db.add(card)
            db.commit()
            db.refresh(card)
        self.card_cache[slug] = card
        return card

    def scrape(self, limit: Optional[int] = None):
        """Main scrape entry point. If limit is None, fetches all."""
        print(f"🚀 Starting {self.SOURCE_NAME} Scraper...")
        self.db = get_db_session()
        
        limit = limit or 999 # Safe high default for 'all'
        cards: List[Any] = []
        
        stats: Dict[str, Any] = {
            "total_found": 0,
            "total_saved": 0,
            "total_skipped": 0,
            "total_failed": 0,
            "total_revived": 0,
            "status": "SUCCESS",
            "errors": []
        }

        try:
            self.setup_driver()
            if not self.driver:
                raise Exception("Failed to initialize driver")

            driver = self.driver
            driver.get(self.TARGET_URL)
            time.sleep(5)

            # Accept cookies if any overlay appears
            try:
                # Specific "ANLADIM" button observed in browser test
                cookie_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn-accept, #CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, .btn.btn-primary:has-text('ANLADIM')"))
                )
                cookie_btn.click()
                time.sleep(1)
            except:
                pass

            # Handling "Daha Fazla Göster"
            print("   ⏳ Loading all campaigns (Clicking 'Daha Fazla Göster')...")
            click_count = 0
            while click_count < 10: # Safety break
                try:
                    # Selector for Petrol Ofisi 'Daha fazla göster' button
                    btn = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "button.show-more, .btn.btn-primary.show-more, .campaigns-more"))
                    )
                    
                    if not btn.is_displayed():
                        break
                        
                    # Scroll to button
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(1)
                    
                    try:
                        btn.click()
                    except:
                        driver.execute_script("arguments[0].click();", btn)
                        
                    click_count += 1
                    print(f"   🖱️ Clicked 'Show More' {click_count} times.")
                    time.sleep(3)
                except:
                    # Button no longer exists or not clickable
                    break

            # Collect cards
            time.sleep(5)
            source = driver.page_source
            soup = BeautifulSoup(source, "html.parser")
            cards = soup.select(".campaign-card, .card-campaign")
            
            if not cards:
                print("   ⚠️ No cards found with '.card-campaign'. Diagnostic info:")
                unique_classes = sorted(list(set([cls for el in soup.find_all(True) for cls in el.get("class", [])])))
                print(f"   📂 Found {len(unique_classes)} unique classes in DOM.")
                print(f"   📑 First 1000 chars of source: {source[:1000]}")
                # Try fallback selector
                cards = soup.select(".card")
                if cards:
                    print(f"   💡 Fallback selector '.card' found {len(cards)} cards.")

            print(f"   🎯 Found {len(cards)} potential campaign cards.")

            bank = self._get_or_create_bank(self.db)
            card = self._get_or_create_card(self.db, bank.id)

            processed_count = 0
            for card_soup in cards:
                if processed_count >= limit:
                    break

                try:
                    # Link & Title extraction
                    # Card itself might be the link, or it might contain multiple links
                    link_tag = card_soup if card_soup.name == "a" else card_soup.select_one("a[href*='kampanya'], a.detayli-bilgi, a.btn")
                    
                    if not link_tag and card_soup.name != "a":
                        link_tag = card_soup.select_one("a") # Fallback to any link
                        
                    if not link_tag or not link_tag.get("href"):
                        continue
                        
                    relative_url = link_tag.get("href")

                    # Skip non-campaign links or irrelevant pages
                    ignore_patterns = [
                        "biten-kampanyalar", "/kampanyalar$", "/kampanyalar/$", 
                        "bize-ulasin", "gizlilik", "kurumsal", "istasyonlar", 
                        "otopuan-nerede", "yardim", "kvkk"
                    ]
                    if any(p in relative_url.lower() for p in ignore_patterns):
                        continue

                    detail_url = urljoin(self.BASE_URL, relative_url)
                    
                    title_tag = card_soup.select_one(".card-title, h5, h4, .title")
                    title = title_tag.get_text(strip=True) if title_tag else ""
                    
                    if not title or title.lower() == "kampanyalar":
                        # If card title fails, we'll try to get it from detail page later or use a better fallback
                        title = "Petrol Ofisi Kampanyası"
                    
                    # Image
                    img_tag = card_soup.select_one("img")
                    img_url = urljoin(self.BASE_URL, img_tag.get("src")) if img_tag else None

                    # Check DB/Blocklist
                    if is_url_blocked(self.db, detail_url):
                        print(f"      🚫 Skipped (Blocklisted): {detail_url}")
                        stats["total_skipped"] += 1
                        continue

                    existing = self.db.query(Campaign).filter(Campaign.tracking_url == detail_url).first()
                    if existing and existing.is_active and existing.is_approved:
                        print(f"      ⏭️ Skipped (Already exists and active): {title}")
                        stats["total_skipped"] += 1
                        continue

                    # Visit Detail Page
                    print(f"   [{(processed_count+1)}] Processing: {detail_url}")
                    self.driver.get(detail_url)
                    time.sleep(2)
                    
                    detail_soup = BeautifulSoup(self.driver.page_source, "html.parser")
                    content_area = detail_soup.select_one("main, .content, .campaign-detail")
                    raw_html = str(content_area) if content_area else self.driver.page_source

                    # og:title for Header Sniper
                    og_title_el = detail_soup.find("meta", property="og:title")
                    og_title = og_title_el.get("content", "").strip() if og_title_el else title

                    # AI Parsing
                    ai_data = parse_api_campaign(
                        title=title,
                        short_description=None,
                        content_html=raw_html,
                        bank_name="Petrol Ofisi",
                        scraper_sector=None,
                        tracking_url=detail_url,
                        og_title=og_title
                    )

                    if not ai_data or ai_data.get("_ai_failed"):
                        print(f"      ⚠️ AI parsing failed for: {title}")
                        stats["total_failed"] += 1
                        continue

                    # Create Campaign & Slug
                    campaign_slug = get_unique_slug(title, self.db, Campaign)
                    
                    # Convert dates safely
                    s_date = ai_data.get('start_date')
                    e_date = ai_data.get('end_date')
                    
                    try:
                        start_dt = datetime.strptime(s_date, "%Y-%m-%d").date() if s_date else None
                    except:
                        start_dt = None
                        
                    try:
                        end_dt = datetime.strptime(e_date, "%Y-%m-%d").date() if e_date else None
                    except:
                        end_dt = None

                    new_campaign = Campaign(
                        card_id=card.id,
                        slug=campaign_slug,
                        title=ai_data.get("title", title),
                        reward_text=ai_data.get("reward_text"),
                        reward_value=ai_data.get("reward_value"),
                        reward_type=ai_data.get("reward_type"),
                        description=ai_data.get("description"),
                        ai_marketing_text=ai_data.get("ai_marketing_text"),
                        conditions="\n".join(ai_data.get("conditions", [])),
                        image_url=img_url or ai_data.get("image_url"),
                        participation=ai_data.get("participation"),
                        eligible_cards=", ".join(ai_data.get("cards", [])),
                        start_date=start_dt,
                        end_date=end_dt,
                        tracking_url=detail_url,
                        is_active=True,
                        clean_text=ai_data.get("_clean_text"),
                        sector_id=self._get_sector_id(ai_data.get("sector")),
                        category=ai_data.get("sector", "diger")
                    )

                    # Use centralized upsert_campaign for revival and quality control
                    new_campaign, op_status = upsert_campaign(self.db, new_campaign)
                    self.db.commit()

                    if op_status == "revived":
                        print(f"      ♻️  Revived Passive Campaign: {new_campaign.title[:50]}...")
                        stats["total_revived"] += 1
                    elif op_status == "saved":
                         print(f"      ✅ Saved: {new_campaign.title[:50]}...")
                         stats["total_saved"] += 1
                    
                    self.db.refresh(new_campaign)

                    # Brand Matching
                    brand_names = ai_data.get("brands", [])
                        
                    brand_ids = get_or_create_brands_list(
                        db=self.db,
                        names=brand_names,
                        brand_cache=self.brand_cache
                    )

                    for b_id in brand_ids:
                        existing_link = self.db.query(CampaignBrand).filter_by(campaign_id=new_campaign.id, brand_id=b_id).first()
                        if not existing_link:
                            cb = CampaignBrand(campaign_id=new_campaign.id, brand_id=b_id)
                            self.db.add(cb)

                    self.db.commit()
                    processed_count += 1
                    print(f"      ✅ Saved: {title}")

                except Exception as e:
                    print(f"      ❌ Error processing card: {e}")
                    stats["total_failed"] += 1
                    stats["errors"].append(str(e))
                    self.db.rollback()

            # -------------------------------------------------------------
            # STAGE 2: Mobile App API Scraping (Extra Mobile Campaigns)
            # -------------------------------------------------------------
            print("\n📱 Stage 2: Fetching Extra Mobile App Campaigns via API...")
            self._scrape_mobile_api(bank, card, stats)

        except Exception as e:
            print(f"   ❌ Scraper Crashed: {e}")
            stats["status"] = "FAILED"
            stats["errors"].append(str(e))
        finally:
            if self.driver:
                self.driver.quit()
            if self.db is not None:
                self.db.close()
            
        # Log Result
        log_scraper_execution(
            db=self.db,
            scraper_name=self.SOURCE_NAME,
            status=stats.get("status", "SUCCESS"),
            total_found=len(cards),
            total_revived=stats["total_revived"],
            error_details={"errors": stats["errors"]} if stats["errors"] else None
        )
        print(f"🏁 Finished {self.SOURCE_NAME}. Saved: {stats['total_saved']}, Revived: {stats['total_revived']}, Skipped: {stats['total_skipped']}, Failed: {stats['total_failed']}")

    def _get_guest_token(self) -> Optional[str]:
        """
        Returns an active Guest Bearer Token.
        First checks PETROL_OFISI_BEARER_TOKEN from .env.
        If missing or expired, dynamically fetches a fresh 60-day Guest token from Mobile API.
        """
        import requests
        
        env_token = os.getenv("PETROL_OFISI_BEARER_TOKEN")
        if env_token:
            return env_token
            
        print("   🔑 Fetching fresh dynamic Guest Token from Petrol Ofisi Mobile Auth API...")
        auth_url = "https://mobilapi.petrolofisi.com.tr/api/auth/guest"
        headers = {
            'X-Load-Test-Secret': '021ea2f3-bc71-4112-8d50-b97b0af2b890',
            'Content-Type': 'application/json',
            'X-Channel': 'ANDROID',
            'Accept-Language': 'tr',
            'User-Agent': 'okhttp/4.10.0'
        }
        
        try:
            res = requests.post(auth_url, headers=headers, json={}, timeout=10)
            if res.status_code == 200:
                token_data = res.json()
                access_token = token_data.get("accessToken")
                if access_token:
                    print("   ✅ Successfully generated new dynamic 60-day Guest Bearer Token!")
                    return access_token
        except Exception as e:
            print(f"   ⚠️ Dynamic Guest token fetch error: {e}")
            
        return None

    def _scrape_mobile_api(self, bank: Bank, card: Card, stats: Dict[str, Any]):
        """Scrapes extra campaigns exclusive to Petrol Ofisi Mobil App via API."""
        import requests
        
        token = self._get_guest_token()
        if not token:
            print("   ⚠️ Failed to acquire Guest Token. Skipping mobile API stage.")
            return

        headers = {
            'X-Load-Test-Secret': '021ea2f3-bc71-4112-8d50-b97b0af2b890',
            'Content-Type': 'application/json',
            'X-Channel': 'ANDROID',
            'Accept-Language': 'tr',
            'Authorization': f'Bearer {token}',
            'User-Agent': 'okhttp/4.10.0'
        }

        # Scan recent post ID window dynamically
        start_id = 8200
        max_id = 9000
        consecutive_404s = 0
        max_consecutive_404s = 35
        
        for post_id in range(start_id, max_id):
            tracking_url = f"https://mobilapi.petrolofisi.com.tr/api/posts/{post_id}"
            
            try:
                r = requests.get(tracking_url, headers=headers, timeout=5)
                if r.status_code != 200:
                    consecutive_404s += 1
                    if consecutive_404s >= max_consecutive_404s and post_id > 8550:
                        print(f"   ℹ️ Petrol Ofisi API: Reached {consecutive_404s} consecutive 404s at post_id={post_id}. Stopping scan.")
                        break
                    continue
                
                consecutive_404s = 0
                    
                data = r.json()
                title = data.get("title", "").strip()
                # Skip internal developer test posts or broken posts
                title_lower = title.lower()
                desc_lower = (data.get("description") or "").lower()
                test_indicators = ["katılımcı testi", "401 hatası", "test kampanya", "katılımcı"]
                if any(x in title_lower or x in desc_lower for x in test_indicators):
                    continue
                    
                # Extract internal Turkish campaign name if available
                c_list = data.get("data", {}).get("campaigns", [])
                c_name = c_list[0].get("campaignName") if (c_list and isinstance(c_list, list) and len(c_list) > 0 and isinstance(c_list[0], dict)) else None

                # Check if upper title is in English
                english_indicators = ['discount', 'campaign', 'now', 'up to', 'members', 'exclusive', 'join the', 'enjoy an', 'from petrol ofisi', 'customers', 'get ', 'special', 'buy ', 'offer', ' earn ', 'points']
                if any(x in title.lower() for x in english_indicators):
                    if c_name and not any(x in c_name.lower() for x in english_indicators):
                        title = c_name
                    else:
                        print(f"      ⏭️ Skipping English mobile campaign: {title}")
                        continue

                # Clean campaign title to match web campaign format and enable deduplication
                title = self._clean_campaign_title(title)
                if not title:
                    continue

                # DB / Blocklist check
                if is_url_blocked(self.db, tracking_url):
                    continue

                existing = self.db.query(Campaign).filter(Campaign.tracking_url == tracking_url).first()
                if existing and existing.is_active and existing.is_approved:
                    existing.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    self.db.commit()
                    stats["total_skipped"] += 1
                    continue

                # NEW: Check for title duplicates (twins) from the web scraper
                from src.utils.scraper_utils import normalize_text_for_comparison
                norm_title = normalize_text_for_comparison(title)
                twin_exists = False
                if norm_title:
                    all_camps = self.db.query(Campaign).filter(Campaign.card_id == card.id).all()
                    for c in all_camps:
                        if normalize_text_for_comparison(c.title) == norm_title and c.tracking_url != tracking_url:
                            print(f"      ⏭️ Skipping duplicate mobile twin: '{title}' (Twin of {c.id})")
                            twin_exists = True
                            break
                if twin_exists:
                    stats["total_skipped"] += 1
                    continue

                # Image URL fix: JSON key is 'image'
                medias = data.get("medias", [])
                image_url = None
                if medias and isinstance(medias, list) and len(medias) > 0 and isinstance(medias[0], dict):
                    image_url = medias[0].get("image") or medias[0].get("url")

                description_html = data.get("description", "")
                
                # AI Parsing
                ai_data = parse_api_campaign(
                    title=title,
                    short_description=None,
                    content_html=description_html,
                    bank_name="Petrol Ofisi",
                    scraper_sector=None,
                    tracking_url=tracking_url,
                    og_title=title
                )

                if not ai_data or ai_data.get("_ai_failed"):
                    continue

                # Dates
                s_date = ai_data.get('start_date')
                e_date = ai_data.get('end_date')
                try: start_dt = datetime.strptime(s_date, "%Y-%m-%d").date() if s_date else None
                except: start_dt = None
                try: end_dt = datetime.strptime(e_date, "%Y-%m-%d").date() if e_date else None
                except: end_dt = None

                campaign_slug = get_unique_slug(title, self.db, Campaign)

                new_campaign = Campaign(
                    card_id=card.id,
                    slug=campaign_slug,
                    title=ai_data.get("title", title),
                    reward_text=ai_data.get("reward_text"),
                    reward_value=ai_data.get("reward_value"),
                    reward_type=ai_data.get("reward_type"),
                    description=ai_data.get("description"),
                    ai_marketing_text=ai_data.get("ai_marketing_text"),
                    conditions="\n".join(ai_data.get("conditions", [])),
                    image_url=image_url or ai_data.get("image_url"),
                    participation=ai_data.get("participation"),
                    eligible_cards=", ".join(ai_data.get("cards", [])),
                    start_date=start_dt,
                    end_date=end_dt,
                    tracking_url=tracking_url,
                    is_active=True,
                    clean_text=ai_data.get("_clean_text"),
                    sector_id=self._get_sector_id(ai_data.get("sector")),
                    category=ai_data.get("sector", "diger")
                )

                new_campaign, op_status = upsert_campaign(self.db, new_campaign)
                self.db.commit()

                if op_status == "revived":
                    print(f"      📱 ♻️  Revived Mobile Campaign: {new_campaign.title[:50]}...")
                    stats["total_revived"] += 1
                elif op_status == "saved":
                    print(f"      📱 ✅ Saved Mobile Campaign: {new_campaign.title[:50]}...")
                    stats["total_saved"] += 1

                self.db.refresh(new_campaign)

                # Brand matching
                brand_names = ai_data.get("brands", [])
                brand_ids = get_or_create_brands_list(
                    db=self.db,
                    names=brand_names,
                    brand_cache=self.brand_cache
                )

                for b_id in brand_ids:
                    existing_link = self.db.query(CampaignBrand).filter_by(campaign_id=new_campaign.id, brand_id=b_id).first()
                    if not existing_link:
                        cb = CampaignBrand(campaign_id=new_campaign.id, brand_id=b_id)
                        self.db.add(cb)

                self.db.commit()

            except Exception as e:
                print(f"      ⚠️ Error in mobile post #{post_id}: {e}")
                self.db.rollback()

    def _get_sector_id(self, sector_slug: Optional[str]) -> Optional[int]:
        """Maps AI sector slug to DB sector ID."""
        if not sector_slug:
            return None
        sector = self.db.query(Sector).filter(Sector.slug == sector_slug).first()
        return sector.id if sector else None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit campaigns to process")
    args = parser.parse_args()
    
    scraper = PetrolOfisiScraper()
    scraper.scrape(limit=args.limit)

