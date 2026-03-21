import os
import time
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from sqlalchemy.orm import Session
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium_stealth import stealth
from selenium.webdriver.common.by import By

from src.database import get_db_session
from src.models import Campaign, Bank, Card, Sector, Brand, CampaignBrand
from src.services.ai_parser import parse_api_campaign
from src.utils.slug_generator import get_unique_slug
from src.utils.scraper_utils import is_url_blocked
from src.utils.cache_manager import clear_cache

class ONDigitalScraper:
    """
    Scraper for ON Digital (Burgan Bank) campaigns.
    Uses Selenium with Stealth mode for navigation and BeautifulSoup for extraction.
    """
    
    BASE_URL = 'https://on.com.tr'
    LIST_URL = 'https://on.com.tr/kampanyalar'
    BANK_NAME = 'Burgan Bank'
    BRAND_NAME = 'ON Digital'
    CARD_NAME = 'ON Kredi Kartı'
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.db: Session = get_db_session()
        self.bank = self._get_or_create_bank()
        self.card = self._get_or_create_card()
        self.driver: Optional[WebDriver] = None
        
    def setup_driver(self):
        """Initialize Selenium with Stealth Mode."""
        if self.driver:
            return

        options = webdriver.ChromeOptions()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"user-agent={self.HEADERS['User-Agent']}")
        
        if os.getenv("DOCKER_MODE") == "true" or os.environ.get("HEADLESS") == "1" or os.environ.get("TEST_MODE") == "1":
            options.add_argument('--headless=new')
            options.add_argument('--disable-gpu')

        self.driver = webdriver.Chrome(options=options)
        
        stealth(self.driver,
                languages=["tr-TR", "tr"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
                )

    def _get_or_create_bank(self) -> Bank:
        bank_slug = "burgan-bank"
        bank = self.db.query(Bank).filter(Bank.slug == bank_slug).first()
        if not bank:
            print(f"✨ Creating bank: {self.BANK_NAME}")
            bank = Bank(
                name=self.BANK_NAME, 
                slug=bank_slug, 
                is_active=True,
                logo_url="/logos/cards/burgan.png"
            )
            self.db.add(bank)
            self.db.commit()
            self.db.refresh(bank)
        return bank

    def _get_or_create_card(self) -> Card:
        card_slug = "on-kredi-karti"
        card = self.db.query(Card).filter(Card.slug == card_slug).first()
        if not card:
            print(f"💳 Creating card: {self.CARD_NAME}")
            card = Card(
                name=self.CARD_NAME,
                bank_id=self.bank.id,
                slug=card_slug,
                card_type="credit",
                is_active=True
            )
            self.db.add(card)
            self.db.commit()
            self.db.refresh(card)
        return card

    def _fetch_campaign_data(self) -> List[Dict[str, Any]]:
        """Use Selenium to handle lazy loading and extract initial card data."""
        print(f"📥 Fetching campaign list from {self.LIST_URL} (Selenium)")
        campaigns = []
        
        try:
            self.setup_driver()
            driver = self.driver
            if not driver:
                return []

            driver.get(self.LIST_URL)
            time.sleep(5) # Allow dynamic content to start loading
            
            # Handle cookie banner if present
            try:
                # Using a more robust selector for the cookie button
                cookie_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Kabul Et')] | //*[contains(@class, 'cookie-accept')] | //*[contains(@id, 'gdpr-accept')]")
                cookie_btn.click()
                time.sleep(1)
            except: pass
            
            # Scroll to load all campaigns (Lazy Loading)
            last_height = driver.execute_script("return document.body.scrollHeight")
            for _ in range(15): # Limit scrolls
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            # Extract card data
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Updated selector based on recent research: .campaign-card
            cards = soup.select('.campaign-card') or soup.select('div.col-md-4') or soup.select('.card')
            
            print(f"   DEBUG: Found {len(cards)} potential card elements in the DOM")
            
            for card in cards:
                link_elm = card.select_one('a.stretched-link') or card.select_one('a[href*="-kampanyasi"]')
                img_elm = card.select_one('img.card-img-top') or card.select_one('img')
                
                if link_elm and link_elm.get('href'):
                    title = link_elm.get('title') or link_elm.get_text().strip()
                    # If title is still empty, try h2 or other headers
                    if not title:
                        title_elm = card.select_one('h2, h3, h4, .card-title')
                        title = title_elm.get_text().strip() if title_elm else "İsimsiz Kampanya"
                        
                    href = str(link_elm.get('href'))
                    image_url = img_elm.get('src') if img_elm else None
                    
                    # Extract sector/category badges
                    badges = card.select('.badge') or card.select('.tag')
                    sector_hint = ", ".join([b.get_text(strip=True) for b in badges])
                    
                    if image_url and not image_url.startswith('http'):
                        image_url = urljoin(self.BASE_URL, image_url)
                        
                    campaigns.append({
                        'title': title,
                        'url': urljoin(self.BASE_URL, href),
                        'initial_image': image_url,
                        'sector_hint': sector_hint
                    })
            
            # Filter matches to ensure they look like actual campaigns
            campaigns = [c for c in campaigns if c['url'] and c['title'] and c['title'] != 'İsimsiz Kampanya']
            print(f"✅ Found {len(campaigns)} verified campaign cards")
            
        except Exception as e:
            print(f"❌ Selenium Error: {e}")
        finally:
            driver = self.driver
            if driver:
                try:
                    driver.quit()
                except: pass
                self.driver = None
                
        return campaigns

    def _process_campaign(self, campaign_data: Dict[str, str]):
        url = campaign_data['url']
        title = campaign_data['title']
        list_image = campaign_data['initial_image']
        
        # Database Pre-check
        try:
            if is_url_blocked(self.db, url):
                print(f"   🚫 Skipped (Blocklisted): {url}")
                return "skipped"

            existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()
            if existing:
                print(f"   ⏭️ Skipped (Exists): {title}")
                return "skipped"
        except Exception as e:
            print(f"   ⚠️ DB Check error: {e}")

        try:
            print(f"   🔎 Processing: {title}")
            
            # Using Selenium for detail page to handle dynamic content & lazy loaded sections
            self.setup_driver()
            driver = self.driver
            if not driver:
                raise Exception("Driver not initialized")
                
            driver.get(url)
            time.sleep(3)
            
            # Scroll to ensure all content sections are rendered
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 1.5);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Use card image as primary (user request)
            image_url = list_image
            
            # Extraction logic for detail page
            content_sections = []
            
            # Look for main content area - using updated selectors
            main_content = soup.select_one('.kampanya-detay-icerik') or \
                           soup.select_one('article') or \
                           soup.select_one('.detail-content') or \
                           soup.select_one('.content')
                           
            if main_content:
                content_sections.append(main_content.get_text(separator="\n", strip=True))
            
            # Look for all text content if specific container not found
            if not content_sections:
                all_text = soup.select_one('main') or soup.find('body')
                if all_text:
                    content_sections.append(all_text.get_text(separator="\n", strip=True))

            # Look for conditions specifically
            conditions_elm = soup.select_one('#kampanya-kosullari') or \
                             soup.select_one('.conditions') or \
                             soup.select_one('.tab-pane') # Sometimes in tabs
            
            if conditions_elm:
                sep = '\n'
                content_sections.append(f"KAMPANYA KOŞULLARI:\n{conditions_elm.get_text(separator=sep, strip=True)}") # type: ignore
            
            raw_content = "\n\n".join(content_sections)
            
            # AI enrichment
            ai_data = parse_api_campaign(
                title=title,
                short_description=title,
                content_html=raw_content,
                bank_name=self.BANK_NAME,
                scraper_sector=campaign_data.get('sector_hint'),
                tracking_url=url
            )
            
            # Save to DB
            return self._save_campaign(
                title=ai_data.get('short_title') or title,
                image_url=image_url,
                tracking_url=url,
                ai_data=ai_data,
                raw_description=raw_content
            )
            
        except Exception as e:
            print(f"   ❌ Error processing {url}: {e}")
            return "error"
        finally:
            # We don't quit the driver here to reuse it in the loop
            pass

    def _save_campaign(self, title: str, image_url: Optional[str], 
                       tracking_url: str, ai_data: Dict[str, Any], 
                       raw_description: str):
        try:
            # Slug
            slug = get_unique_slug(title, self.db, Campaign)

            # Dates
            start_date = None
            end_date = None
            if ai_data.get('start_date'):
                try: start_date = datetime.strptime(ai_data['start_date'], "%Y-%m-%d")
                except: pass
            if ai_data.get('end_date'):
                try: end_date = datetime.strptime(ai_data['end_date'], "%Y-%m-%d")
                except: pass

            # Sector mapping
            sector_name = ai_data.get('sector', 'Diğer')
            sector = self.db.query(Sector).filter((Sector.slug == sector_name) | (Sector.name.ilike(sector_name))).first()
            if not sector:
                sector = self.db.query(Sector).filter(Sector.slug == 'diger').first()

            campaign = Campaign(
                slug=slug,
                title=title,
                card_id=self.card.id,
                sector_id=sector.id if sector else None,
                reward_value=ai_data.get('reward_value'),
                reward_type=ai_data.get('reward_type'),
                reward_text=ai_data.get('reward_text', 'Detayları İnceleyin'),
                description=str(ai_data.get('description') or raw_description)[:500],
                conditions='\n'.join(ai_data.get('conditions', [])),
                start_date=start_date,
                end_date=end_date,
                image_url=image_url,
                tracking_url=tracking_url,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            self.db.add(campaign)
            self.db.commit()
            print(f"   ✅ Saved: {campaign.title}")

            # Brands
            for b_name in ai_data.get('brands', []):
                brand = self.db.query(Brand).filter(Brand.name == b_name).first()
                if not brand:
                    brand = Brand(name=b_name, slug=get_unique_slug(b_name, self.db, Brand), is_active=True)
                    self.db.add(brand)
                    self.db.flush()
                
                self.db.add(CampaignBrand(campaign_id=campaign.id, brand_id=brand.id))
            
            self.db.commit()
            return "saved"

        except Exception as e:
            self.db.rollback()
            print(f"   ❌ Save Error: {e}")
            return "error"

    def run(self, limit: Optional[int] = None):
        print(f"🚀 Starting {self.BRAND_NAME} Scraper...")
        campaigns = self._fetch_campaign_data()
        
        # Using list() to ensure it's sliceable even if type hint is confusing
        campaigns_list = list(campaigns)
        campaigns_to_process = campaigns_list[:limit] if limit else campaigns_list
        if limit:
            print(f"   Using limit: {limit}")
            
        stats = {"saved": 0, "skipped": 0, "error": 0}
        
        for item in campaigns_to_process:
            res = self._process_campaign(item)
            stats[res if res in stats else "error"] += 1
            time.sleep(1)
            
        print(f"\n✅ Summary: {stats['saved']} saved, {stats['skipped']} skipped, {stats['error']} errors.")
        
        if self.driver:
            self.driver.quit()
            self.driver = None
            
        if stats['saved'] > 0:
            clear_cache('campaigns:*')

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Limit number of campaigns')
    args = parser.parse_args()
    
    scraper = ONDigitalScraper()
    scraper.run(limit=args.limit)
