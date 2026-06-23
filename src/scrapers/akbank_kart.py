import sys
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.scrapers.akbank_base import AkbankBaseScraper
from src.database import get_db_session
from src.services.ai_parser import parse_api_campaign

class AkbankKartScraper(AkbankBaseScraper):
    def __init__(self):
        super().__init__(
            card_name="Akbank Kart",
            base_url="https://www.akbank.com",
            list_url="https://www.akbank.com/kampanyalar",
            referer_url="https://www.akbank.com/kampanyalar"
        )
    
    def _fetch_campaign_list(self) -> list:
        print(f"📥 Fetching campaign list for {self.card_name}...")
        response = self.session.get(self.list_url, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        campaign_urls = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Akbank kampanyalar page lists campaigns under /kampanyalar/
            if href.startswith('/kampanyalar/') and href not in campaign_urls:
                campaign_urls.append(urljoin(self.base_url, href))
                
        print(f"✅ Found {len(campaign_urls)} campaigns for {self.card_name}")
        return campaign_urls

    def _process_campaign(self, url: str, force: bool = False) -> str:
        print(f"🔍 Processing: {url}")
        try:
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            
            # Check for redirect to generic list/homepage
            redirect_status = self._check_redirect(response, url)
            if redirect_status == "skipped":
                return "skipped"
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 🛡️ EXPIRY BADGE CHECK: Akbank keeps dead campaigns alive with "Arşivden Gösterim"
            badge = soup.select_one('.campaign-item-box__badge')
            if badge and 'arşiv' in badge.get_text(strip=True).lower():
                print(f"   ⚠️ [Archived] Found 'Arşivden Gösterim' badge. Skipping.")
                with get_db_session() as db:
                    url_slug = url.strip('/').split('/')[-1]
                    from src.models import Campaign
                    all_camps = db.query(Campaign).filter(
                        Campaign.card_id == self.card_id,
                        Campaign.tracking_url.like(f"%/{url_slug}%")
                    ).all()
                    for camp in all_camps:
                        camp.is_active = False
                    db.commit()
                return "skipped"
            
            # --- 1. Raw HTML Extraction ---
            og_title_el = soup.find("meta", property="og:title")
            title = og_title_el.get("content") if og_title_el else "Kampanya"
            
            # Remove brand suffix if present
            if " | Akbank" in title:
                title = title.split(" | Akbank")[0]
            
            # Extract Image
            image_url = None
            img_el = soup.select_one('.detail-highlight__image-wrapper img')
            if img_el and img_el.get("src"):
                src = img_el.get("src")
                if src.startswith('/'):
                    image_url = urljoin(self.base_url, src)
                else:
                    image_url = src
            else:
                og_img_el = soup.find("meta", property="og:image")
                if og_img_el and og_img_el.get("content"):
                    src = og_img_el.get("content")
                    if "logo.svg" not in src:
                        if src.startswith('/'):
                            image_url = urljoin(self.base_url, src)
                        else:
                            image_url = src
            
            # Clean Noise (Breadcrumbs containing all other campaigns, footers, etc.)
            for noise in soup.find_all('div', class_='breadcrumb'):
                noise.decompose()
            for footer in soup.find_all('footer'):
                footer.decompose()
            for header in soup.find_all('header'):
                header.decompose()
            for nav in soup.find_all('nav'):
                nav.decompose()
            
            # Decompose swiper/slider containers and breadcrumb dropdowns of other campaigns to prevent brand/tag pollution
            for slider in soup.select('.product-list__slider, .product-list__grid, .swiper, .swiper-wrapper, .swiper-slide, .other-campaigns, .campaignDetail-others, .breadcrumb, noindex, .noindex, .dropdown__menu'):
                slider.decompose()
            
            main_el = soup.find("main")
            raw_html = str(main_el) if main_el else str(soup.find("body") or soup)
                
            # --- 2. AI Parsing (Using Global Cache) ---
            ai_data = parse_api_campaign(
                title=title,
                short_description=title, 
                content_html=raw_html,
                bank_name="Akbank",
                scraper_sector=None,
                tracking_url=url,
                force=force,
                og_title=og_title_el.get("content") if og_title_el else None
            )
            
            # --- 3. Save to DB ---
            return self._save_campaign(title, image_url, ai_data, url)
            
        except Exception as e:
            print(f"❌ Failed to process {url}: {e}")
            return "error"

if __name__ == "__main__":
    scraper = AkbankKartScraper()
    scraper.run()
