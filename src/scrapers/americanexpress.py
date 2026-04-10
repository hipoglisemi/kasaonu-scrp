


"""
American Express Turkey Scraper
Powered by Playwright and AIParser
"""

import os
import sys
import time  # type: ignore # pyre-ignore[21]
import requests  # type: ignore # pyre-ignore[21]
import re  # type: ignore # pyre-ignore[21]
import traceback  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from typing import Optional, Dict, Any, List  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]

# Path setup - reach project root (parent of src)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.brand_matcher import get_or_create_brands_list  # type: ignore
from src.database import get_db_session  # type: ignore

try:
    from dotenv import load_dotenv  # type: ignore # pyre-ignore[21]
    load_dotenv(os.path.join(project_root, '.env'))
except Exception:
    pass

from sqlalchemy import create_engine  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import sessionmaker  # type: ignore # pyre-ignore[21]

AIParser = None

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

# PostgreSQL fix for modern SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
from src.scrapers.param import Bank, Card, Sector, Brand, CampaignBrand, Campaign, SECTOR_MAP  # type: ignore # pyre-ignore[21]
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked  # type: ignore

class AmericanExpressScraper:
    """American Express scraper - Playwright based"""

    BASE_URL = "https://www.americanexpress.com.tr"
    CAMPAIGNS_URL = "https://www.americanexpress.com.tr/kampanyalar"
    BANK_NAME = "American Express"
    BANK_SLUG = "american-express"

    def __init__(self):
        self.engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()
        
        try:
            from src.services.ai_parser import AIParser as _AIParser  # type: ignore # pyre-ignore[21]
        except ImportError:
            from services.ai_parser import AIParser as _AIParser  # type: ignore # pyre-ignore[21]
        global AIParser
        AIParser = _AIParser

        self.ai_parser = AIParser()
        self.stats = {"found": 0, "saved": 0, "skipped": 0, "failed": 0, "errors": []}  # type: ignore # pyre-ignore[16,6]

    @staticmethod
    def _slugify(text: str) -> str:
        """Generate a URL-safe slug from text"""
        import unicodedata  # type: ignore # pyre-ignore[21]
        text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
        text = re.sub(r'[^\w\s-]', '', text.lower()).strip()
        return re.sub(r'[-\s]+', '-', text)[:120]  # type: ignore # pyre-ignore[16,7,6]
        
    def _get_or_create_bank(self) -> Bank:
        bank = self.db.query(Bank).filter_by(slug=self.BANK_SLUG).first()  # type: ignore # pyre-ignore[16]
        if not bank:
            bank = Bank(name=self.BANK_NAME, slug=self.BANK_SLUG)
            self.db.add(bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
        return bank  # type: ignore # pyre-ignore[7]

    def _get_or_create_card(self, bank_id: int) -> Card:
        card = self.db.query(Card).filter_by(slug=self.BANK_SLUG).first()  # type: ignore # pyre-ignore[16]
        if not card:
            card = Card(
                name="American Express", 
                slug=self.BANK_SLUG, 
                bank_id=bank_id
            )
            self.db.add(card)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
        return card  # type: ignore # pyre-ignore[7]

    def _get_sector(self, sector_name: str) -> Sector:
        slug = self._slugify(sector_name)
        if not slug:
            slug = "diger"
            
        sector = self.db.query(Sector).filter_by(slug=slug).first()  # type: ignore # pyre-ignore[16]
        if not sector:
            sector = self.db.query(Sector).filter_by(slug="diger").first()  # type: ignore # pyre-ignore[16]
        return sector  # type: ignore # pyre-ignore[7]

    def _get_or_create_brands(self, brand_names: List[str]) -> List[Brand]:  # type: ignore # pyre-ignore[16,6]
        # Filter anti-hallucination out before passing
        cleaned_names = []
        for name in brand_names:
            if not name or len(name.strip()) < 2:
                continue
            lower_name = name.strip().lower()
            if any(forbidden in lower_name for forbidden in ["american", "express", "amex", "garanti", "bbva"]):
                continue
            cleaned_names.append(name.strip())
            
        uuid_list = get_or_create_brands_list(self.db, cleaned_names, getattr(self, 'brand_cache', {}))
        
        # Return Brand objects to match previous return type
        brands = []
        for bid in uuid_list:
            brand = self.db.query(Brand).filter_by(id=bid).first()
            if brand:
                brands.append(brand)
        return brands

    def run(self, max_runs: Optional[int] = None):  # type: ignore # pyre-ignore[16,6]
        """Execute the scraping process using simple requests"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting American Express scraper...")  # type: ignore # pyre-ignore[16,6]
        start_time = time.time()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        
        try:
            # 1. Init DB Relationships
            bank = self._get_or_create_bank()
            card = self._get_or_create_card(bank.id)  # type: ignore # pyre-ignore[16]
            self.card_id = card.id  # type: ignore # pyre-ignore[16]
            
            # 2. Get Campaign List
            print(f"Loading {self.CAMPAIGNS_URL}")
            response = requests.get(self.CAMPAIGNS_URL, headers=headers, timeout=30)
            
            if not response.ok:
                raise Exception(f"Failed to load main page. Status: {response.status_code}")
            
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            campaign_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'kampanyalar/' in href and href not in ('/kampanyalar', '/kampanyalar/', 'kampanyalar', 'kampanyalar/'):
                    full_url = urljoin(self.BASE_URL, href)
                    if full_url not in campaign_links:
                        campaign_links.append(full_url)
            
            print(f"Found {len(campaign_links)} campaign links")
            self.stats["found"] = len(campaign_links)
            
            if max_runs:
                campaign_links = campaign_links[:max_runs]  # type: ignore # pyre-ignore[16,6]
                print(f"Limiting to {max_runs} campaigns.")

            # 3. Process Each Campaign Detail
            for idx, link in enumerate(campaign_links, 1):
                print(f"Processing {idx}/{len(campaign_links)}: {link}")
                try:
                    self._process_campaign(link, headers)
                except Exception as e:
                    print(f"Error processing {link}: {e}")
                    # traceback.print_exc()
                    self.stats["failed"] += 1  # type: ignore # pyre-ignore[58]
                    self.stats["errors"].append({"url": link, "error": str(e)})  # type: ignore # pyre-ignore[16,6]

            log_scraper_execution(
                db=self.db,
                scraper_name="americanexpress",
                status="SUCCESS" if self.stats["failed"] == 0 else "PARTIAL",
                total_found=self.stats["found"],
                total_saved=self.stats["saved"],
                total_skipped=self.stats["skipped"],
                total_failed=self.stats["failed"],
                error_details=self.stats["errors"] if self.stats["errors"] else None
            )
            
        except Exception as e:
            error_msg = traceback.format_exc()
            print(f"Fatal error during American Express scraping:\n{error_msg}")
            log_scraper_execution(
                db=self.db,
                scraper_name="americanexpress",
                status="FAILED",
                total_found=self.stats["found"],
                total_saved=self.stats["saved"],
                total_skipped=self.stats["skipped"],
                total_failed=self.stats["failed"],
                error_details={"error": error_msg}
            )
        finally:
            self.db.close()  # type: ignore # pyre-ignore[16]
            elapsed = time.time() - start_time
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Extraction completed in {elapsed:.2f} seconds.")  # type: ignore # pyre-ignore[16,6]
            print(f"Stats: {self.stats}")
            
    def _process_campaign(self, url: str, headers: dict):
        # Check if already exists by URL
        existing = self.db.query(Campaign).filter_by(tracking_url=url).first()  # type: ignore # pyre-ignore[16]
        if existing:
            print(f"  -> Already exists (url): {existing.title}")
            self.stats["skipped"] += 1  # type: ignore # pyre-ignore[58]
            return
        
        
        # Check by URL slug as well
        slug = url.rstrip('/').split('/')[-1]
        existing_slug = self.db.query(Campaign).filter_by(slug=slug[:120]).first()  # type: ignore # pyre-ignore[16,6]
        if existing_slug:
            print(f"  -> Already exists (slug): {slug}")
            self.stats["skipped"] += 1  # type: ignore # pyre-ignore[58]
            return

        # Navigate to detail — force utf-8 decoding
        response = requests.get(url, headers=headers, timeout=30)
        if not response.ok:
            raise Exception(f"Failed to load details: {response.status_code}")
        response.encoding = 'utf-8'
            
        # Parse Page
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # ─── 1. Title ────────────────────────────────────────────────────────────
        title_elem = soup.find('h1')
        if not title_elem:
            raise ValueError("Could not find campaign title (h1)")
        raw_title = title_elem.get_text(separator='\n', strip=True)
        
        if is_url_blocked(self.db, url):
            print(f"  -> Skipped (Blocklisted): {raw_title}")
            self.stats["skipped"] += 1  # type: ignore # pyre-ignore[58]
            return
        
        # ─── 2. Hero Image ───────────────────────────────────────────────────────
        # The hero image is inside section.campaing-details, it's the img that is
        # NOT the logo and NOT the scroll gif:  col-px-left img
        img_url = None
        detail_section = soup.find('section', class_=re.compile(r'campaing-details'))
        if detail_section:
            right_col = detail_section.find('div', class_=re.compile(r'col-px-left'))
            if right_col:
                first_img = right_col.find('img')
                if first_img and first_img.get('src'):
                    img_url = urljoin(self.BASE_URL, first_img['src'])
            
            if not img_url:
                # fallback: any img that's not logo/gif
                for img in detail_section.find_all('img'):
                    src = img.get('src', '')
                    img_cls = ' '.join(img.get('class', []))
                    if src and 'logo' not in src.lower() and 'gif' not in img_cls.lower() and '.gif' not in src.lower():
                        img_url = urljoin(self.BASE_URL, src)  # type: ignore
                        break
        
        # ─── 3. Conditions ───────────────────────────────────────────────────────
        # There can be multiple section.public-container-campaing-text sections
        conditions_parts = []
        content_sections = soup.find_all('section', class_=re.compile(r'public-container-campaing-text|public-container-campaing$'))
        for section in content_sections:
            text = section.get_text(separator='\n', strip=True)
            if text and len(text) > 20:
                conditions_parts.append(text)
        
        full_conditions = "\n\n".join(conditions_parts)
        
        if not full_conditions or len(full_conditions) < 20:
            raise ValueError("Could not extract campaign conditions - no content sections found")
            
        # ─── 3.5 Extract Explicit Header Info ─────────────────────────────────────
        header_info = ""
        for div in soup.find_all('div', class_=re.compile(r'public-sub|campaing')):
            text = div.get_text(separator='\n', strip=True)
            if 'tarihi:' in text.lower() or 'sektör:' in text.lower() or 'marka:' in text.lower():
                header_info += text + "\n"  # type: ignore # pyre-ignore[58]
        
        if header_info:
            full_conditions = f"--- KAMPANYA ÖZET BİLGİLERİ ---\n{header_info}\n--- DETAYLAR ---\n" + full_conditions

        # ─── 4. AI Parsing ───────────────────────────────────────────────────────
        print(f"  -> Title: {raw_title}")
        print("  -> Sending to AI for parsing...")
        ai_data = self.ai_parser.parse_campaign_data(
            raw_text=full_conditions,
            title=raw_title,
            bank_name=self.BANK_NAME
        )

        if not ai_data or 'title' not in ai_data:
            raise ValueError("AI parsing yielded no data")

        # Extract values
        final_title = ai_data.get('title', raw_title)
        parsed_slug = self._slugify(final_title)
        
        # Check by AI-generated slug
        existing_ai_slug = self.db.query(Campaign).filter(Campaign.slug == parsed_slug).first()  # type: ignore # pyre-ignore[16]
        if existing_ai_slug:
            print(f"  -> Campaign already exists (ai slug): {parsed_slug}")
            self.stats["skipped"] += 1  # type: ignore # pyre-ignore[58]
            return

        # Dates
        def parse_date(date_str):
            if not date_str or str(date_str).lower() in ['none', 'null', 'belirtilmemiş', '']:  # type: ignore # pyre-ignore[16,6]
                return None  # type: ignore # pyre-ignore[7]
            try:
                return datetime.strptime(str(date_str), '%Y-%m-%d').date()  # type: ignore # pyre-ignore[7]
            except ValueError:
                return None  # type: ignore # pyre-ignore[7]

        start_date = parse_date(ai_data.get('start_date'))
        end_date = parse_date(ai_data.get('end_date'))

        # Sector
        ai_sector_name = ai_data.get('sector')
        if isinstance(ai_sector_name, list):
             ai_sector_name = ai_sector_name[0] if ai_sector_name else 'Diğer'
        sector_name = ai_sector_name if ai_sector_name else 'diger'
        sector = self._get_sector(sector_name)

        # ─── 5. Format Conditions & Insert Campaign ──────────────────────────────
        parsed_conditions = ai_data.get("conditions", [])
        
        # Build conditions lines starting with Participation and Cards
        conditions_lines = []
        participation = ai_data.get("participation")
        if participation and participation != "Detayları İnceleyin":
            pass  # participation field written separately to DB
        cards = ai_data.get("cards", [])
        if cards:
            pass  # eligible_cards field written separately to DB
        # Add actual conditions
        if isinstance(parsed_conditions, list):
            conditions_lines.extend(parsed_conditions)
        elif isinstance(parsed_conditions, str):
            conditions_lines.append(parsed_conditions)
            
        if not conditions_lines:
            conditions_lines.append(full_conditions[:1500] + "...") # fallback  # type: ignore # pyre-ignore[16,6]
            
        # Format as bullet points (except for our custom headers)
        final_conditions = "\n".join(
            f"- {c}" if not c.startswith("KATILIM:") and not c.startswith("GEÇERLİ KARTLAR:") else c 
            for c in conditions_lines if c
        )

        campaign = Campaign(  # type: ignore
            title=final_title,  # type: ignore
            slug=parsed_slug,  # type: ignore
            description=ai_data.get("description") or final_title,  # type: ignore
            image_url=img_url,  # type: ignore
            sector_id=sector.id,  # type: ignore # pyre-ignore[16]
            card_id=self.card_id,  # type: ignore
            start_date=start_date,  # type: ignore
            end_date=end_date,  # type: ignore
            reward_text=ai_data.get('reward_text'),  # type: ignore
            clean_text=ai_data.get('_clean_text'),  # type: ignore
            reward_type=ai_data.get('reward_type'),  # type: ignore
            reward_value=ai_data.get('reward_value'),  # type: ignore
            eligible_cards=", ".join(cards) or "American Express",
            participation=part,  # type: ignore
            is_active=True,  # type: ignore
            conditions=final_conditions,  # type: ignore
            tracking_url=url,  # type: ignore
        )

        self.db.add(campaign)  # type: ignore # pyre-ignore[16]
        self.db.commit()  # type: ignore # pyre-ignore[16]

        # ─── 6. Brands Linkage ───────────────────────────────────────────────────
        brands_data = ai_data.get('brands', [])
        if brands_data:
            brands = self._get_or_create_brands(brands_data)
            for brand in brands:
                exists = self.db.query(CampaignBrand).filter_by(  # type: ignore # pyre-ignore[16]
                    campaign_id=campaign.id, brand_id=brand.id  # type: ignore # pyre-ignore[16]
                ).first()
                if not exists:
                    cb = CampaignBrand(campaign_id=campaign.id, brand_id=brand.id)  # type: ignore # pyre-ignore[16]
                    self.db.add(cb)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]

        print(f"  -> Saved successfully (ID: {campaign.id}, img: {bool(img_url)})")
        self.stats["saved"] += 1  # type: ignore # pyre-ignore[58]

if __name__ == "__main__":
    import argparse  # type: ignore # pyre-ignore[21]
    parser = argparse.ArgumentParser(description="American Express Scraper")
    parser.add_argument("--limit", type=int, help="Maximum number of campaigns to process")
    args = parser.parse_args()
    
    scraper = AmericanExpressScraper()
    scraper.run(max_runs=args.limit)
