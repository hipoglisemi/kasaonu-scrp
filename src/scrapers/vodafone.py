



import asyncio  # type: ignore # pyre-ignore[21]
import random  # type: ignore # pyre-ignore[21]
import time  # type: ignore # pyre-ignore[21]
import os
import re  # type: ignore # pyre-ignore[21]
import uuid  # type: ignore # pyre-ignore[21]
import sys
import requests  # type: ignore # pyre-ignore[21]
from typing import List, Dict, Any, Optional  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from decimal import Decimal  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import Session  # type: ignore # pyre-ignore[21]

# Path setup to ensure imports work correctly
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]
from src.services.ai_parser_golden import parse_api_campaign  # type: ignore # pyre-ignore[21]
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]

class VodafoneScraper:
    """
    Vodafone Kampanyaları Scraper
    Uses Requests/BeautifulSoup for high efficiency since content is SSR.
    """
    
    BASE_URL = "https://www.vodafone.com.tr"
    LISTING_URLS = [
        "https://www.vodafone.com.tr/kampanyalar/red-marka-ayricaliklari",
        "https://www.vodafone.com.tr/kampanyalar/freezone-guzellikleri",
        "https://www.vodafone.com.tr/kampanyalar/faturali-kampanyalar",
        "https://www.vodafone.com.tr/kampanyalar/kupon-kodu-kampanyalari",
        "https://www.vodafone.com.tr/kampanyalar/faturasiz-kampanyalar",
        "https://www.vodafone.com.tr/kampanyalar/ev-interneti-kampanyalari"
    ]
    
    def __init__(self, max_campaigns: int = 100, headless: bool = True):
        self.max_campaigns = max_campaigns
        self.db: Optional[Session] = None  # type: ignore # pyre-ignore[16,6]
        self.parser = AIParser()
        
        # Cache
        self.bank_cache: Optional[Bank] = None  # type: ignore # pyre-ignore[16,6]
        self.card_cache: Dict[str, Card] = {}  # type: ignore # pyre-ignore[16,6]
        self.sector_cache: Dict[str, Sector] = {}  # type: ignore # pyre-ignore[16,6]
        self.brand_cache: Dict[str, Brand] = {}  # type: ignore # pyre-ignore[16,6]

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def run(self):
        """Entry point for execution"""
        print(f"🚀 Starting Vodafone Scraper (Request Mode)...")
        
        try:
            self.db = get_db_session()
            self._load_cache()
            
            # 1. Get List of all campaigns from all categories
            all_links = []
            for url in self.LISTING_URLS:
                print(f"   🌐 Loading listing page: {url}")
                links = self._scrape_list(url)
                print(f"      Found {len(links)} links in category.")
                for link in links:
                    if link not in all_links:
                        all_links.append(link)
            
            print(f"   Total unique campaigns found: {len(all_links)}")
            
            # Limit
            if len(all_links) > self.max_campaigns:
                all_links = all_links[:self.max_campaigns]  # type: ignore # pyre-ignore[16,6]
            
            # 2. Process Details
            success_count = 0
            for i, url in enumerate(all_links, 1):
                print(f"   [{i}/{len(all_links)}] {url}")
                try:
                    if self._scrape_detail(url):
                        success_count += 1  # type: ignore # pyre-ignore[58]
                    time.sleep(random.uniform(0.5, 1.2))
                except Exception as e:
                    print(f"      ❌ Error processing {url}: {e}")
            
            print(f"\n✅ Scraping complete! Saved {success_count} campaigns.")

        except Exception as e:
            print(f"❌ Fatal error in Vodafone scraper: {e}")
            import traceback  # type: ignore # pyre-ignore[21]
            traceback.print_exc()
        finally:
            if self.db:
                self.db.close()  # type: ignore # pyre-ignore[16]

    def _scrape_list(self, url: str) -> List[str]:  # type: ignore # pyre-ignore[16,6]
        """Fetch listing page and extract campaign links"""
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            links = []
            # Based on research: <a href="/kampanyalar/tchibo-hediye-firsati" class="cmp-card">
            cards = soup.select("a.cmp-card")
            for a in cards:
                href = a.get('href')
                if href and "/kampanyalar/" in href:
                    # Fix: strip whitespace/newlines that might be in the href attribute
                    href = href.strip()
                    full_url = urljoin(self.BASE_URL, href)
                    if full_url not in links:
                        links.append(full_url)
            
            return links  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"      ❌ List extraction failed for {url}: {e}")
            return []  # type: ignore # pyre-ignore[7]

    def _scrape_detail(self, url: str) -> bool:
        """Fetch detail page and extract content from accordions"""
        
        # 1. Duplicate Check
        existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore # pyre-ignore[16]
        if existing:
            print(f"      ⏭️ Skipping (Already exists): {existing.title}")
            return False  # type: ignore # pyre-ignore[7]

        from src.utils.scraper_utils import is_url_blocked  # type: ignore
        if is_url_blocked(self.db, url):
            print(f"      🚫 Skipping (Blocklisted): {url}")
            return False  # type: ignore # pyre-ignore[7]

        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 2. Extract Basic Info
            h1 = soup.select_one(".gallery--header h1")
            title = h1.get_text(strip=True) if h1 else "Vodafone Kampanyası"

            # Final blocklist check with title
            if is_url_blocked(self.db, url):
                print(f"      🚫 Skipping (Blocklisted): {title}")
                return False  # type: ignore # pyre-ignore[7]
            
            # Enhanced Image extraction
            image_url = None
            banner_img = soup.select_one(".banner__image")
            if banner_img and 'src' in banner_img.attrs:
                image_url = urljoin(self.BASE_URL, banner_img['src'])
            
            if not image_url:
                img_tag = soup.select_one(".img-block img")
                if img_tag and 'src' in img_tag.attrs:
                    image_url = urljoin(self.BASE_URL, img_tag['src'])
            
            # Description (CMS Editor content)
            cms_editor = soup.select_one(".cms-editor")
            description = cms_editor.get_text(separator="\n", strip=True) if cms_editor else ""
            
            # 3. Extract Accordion Content
            # Structure: .Accordion-trigger (button) and .Accordion-panel (content)
            content_parts = []
            participation_text = ""
            
            # Add description as the first part if exists
            if description:
                content_parts.append(f"### Kampanya Hakkında\n{description}")

            accordions = soup.select(".Accordion-trigger")
            for trigger in accordions:
                header_text = trigger.get_text(strip=True)
                panel_id = trigger.get('aria-controls')
                if panel_id:
                    panel = soup.find(id=panel_id)
                    if panel:
                        text = panel.get_text(separator="\n", strip=True)
                        if text:
                            content_parts.append(f"### {header_text}\n{text}")
                            # Participation context
                            lower_header = header_text.lower()
                            if any(x in lower_header for x in ["katılım", "nasıl", "faydalan", "detay"]):  # type: ignore # pyre-ignore[16,6]
                                participation_text += f"\n[{header_text}]: {text}"  # type: ignore # pyre-ignore[58,16,6]

            # og:title for Header Sniper
            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content", "").strip() if og_title_el else title

            # Full body HTML → parse_api_campaign centralised pipeline
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else response.text

            # AI Parsing
            print(f"      🧠 Sending to AI Parser...")
            ai_data = parse_api_campaign(
                title=title,
                short_description=description or None,
                content_html=raw_html,
                bank_name="Vodafone",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            )

            if not ai_data:
                print(f"      ❌ AI parsing failed for {url}")
                return False  # type: ignore # pyre-ignore[7]

            # Override/Fixes
            if image_url and (not ai_data.get('image_url') or 'logo' in ai_data.get('image_url', '').lower()):
                ai_data['image_url'] = image_url
            
            # Save to DB
            self._save_campaign(ai_data, url, image_url)
            return True  # type: ignore # pyre-ignore[7]

        except Exception as e:
            print(f"      ❌ Detail error: {e}")
            return False  # type: ignore # pyre-ignore[7]

    def _save_campaign(self, data: Dict[str, Any], url: str, image_url: Optional[str]):  # type: ignore # pyre-ignore[16,6]
        """Save parsed campaign to DB"""
        
        # Bank & Card
        bank = self.bank_cache
        card = self._get_or_create_card("Vodafone")
        
        # Sector
        sector = self._get_sector(data.get("sector") or "")
        
        # Brands
        brand_ids = self._get_or_create_brands(data.get("brands", []), sector.id if sector else None)  # type: ignore # pyre-ignore[16]
        
        # Slug - always use generate_slug for consistency
        from src.utils.slug_generator import generate_slug  # type: ignore # pyre-ignore[21]
        url_hash = uuid.uuid5(uuid.NAMESPACE_URL, url).hex[:8]  # type: ignore # pyre-ignore[16,6]
        base_slug = generate_slug(data.get("title", ""))
        slug = f"{base_slug}-{url_hash}"
        
        # Format for CampaignDetailClient.tsx
        participation = data.get("participation", "")
        ai_description = data.get("ai_marketing_text") or data.get("description", "")
        
        if participation.strip():
            clean_part = re.sub(r'\[[^\]]+\]:\s*', '', participation.strip()).strip()  # type: ignore # pyre-ignore[16,6]
            ai_marketing_text = f"📱 Katılım: {clean_part}\n\n{ai_description}" if ai_description else f"📱 Katılım: {clean_part}"
        else:
            ai_marketing_text = ai_description
            
        campaign = Campaign(
            card_id=card.id,  # type: ignore # pyre-ignore[16]
            sector_id=sector.id if sector else None,  # type: ignore # pyre-ignore[16]
            title=data.get("title"),
            slug=slug,
            description=data.get("description"),
            conditions=data.get("conditions") if not isinstance(data.get("conditions"), list) else "\n".join(data.get("conditions") or []),  # type: ignore # pyre-ignore[16,6]
            reward_text=data.get("reward_text"),
            reward_value=data.get("reward_value"),
            reward_type=data.get("reward_type"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            image_url=image_url or "https://www.vodafone.com.tr/assets/img/vdf-logo.png",
            tracking_url=url,
            is_active=True,
            ai_marketing_text=ai_marketing_text,
            eligible_cards="Vodafone Müşterileri",
            category=data.get("category"),
            badge_color=data.get("badge_color"),
            clean_text=data.get("_clean_text"),
            quality_score=data.get("quality_score", 0)
        )
        
        try:
            self.db.add(campaign)  # type: ignore # pyre-ignore[16]
            self.db.flush()  # type: ignore # pyre-ignore[16]
            
            for bid in brand_ids:
                existing_link = self.db.query(CampaignBrand).filter_by(campaign_id=campaign.id, brand_id=bid).first()  # type: ignore # pyre-ignore[16]
                if not existing_link:
                    cb = CampaignBrand(campaign_id=campaign.id, brand_id=bid)  # type: ignore # pyre-ignore[16]
                    self.db.add(cb)  # type: ignore # pyre-ignore[16]
            
            self.db.commit()  # type: ignore # pyre-ignore[16]
            print(f"      ✅ Saved: {campaign.title}")
        except Exception as e:
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            print(f"      ❌ DB Save Error for {url}: {e}")

    # --- HELPERS ---
    def _load_cache(self):
        bank = self.db.query(Bank).filter(Bank.slug == "vodafone").first()  # type: ignore # pyre-ignore[16]
        if not bank:
            bank = Bank(name="Vodafone", slug="vodafone", is_active=True, logo_url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/af/Vodafone_2017_logo.svg/1200px-Vodafone_2017_logo.svg.png")
            self.db.add(bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
        self.bank_cache = bank
        for c in self.db.query(Card).filter(Card.bank_id == bank.id).all():  # type: ignore # pyre-ignore[16]
            self.card_cache[c.name.lower()] = c
        for s in self.db.query(Sector).all():  # type: ignore # pyre-ignore[16]
            self.sector_cache[s.slug] = s
            self.sector_cache[s.name.lower()] = s
        for b in self.db.query(Brand).filter(Brand.is_active == True).limit(500).all():  # type: ignore # pyre-ignore[16]
            self.brand_cache[b.name.lower()] = b

    def _get_or_create_card(self, name: str) -> Card:
        key = name.lower()
        if key in self.card_cache: return self.card_cache[key]  # type: ignore # pyre-ignore[16,6]
        card = Card(bank_id=self.bank_cache.id, name=name, slug=name.lower().replace(" ", "-"), is_active=True)  # type: ignore # pyre-ignore[16]
        self.db.add(card)  # type: ignore # pyre-ignore[16]
        self.db.flush()  # type: ignore # pyre-ignore[16]
        self.card_cache[key] = card
        return card  # type: ignore # pyre-ignore[7]

    def _get_sector(self, slug: str) -> Optional[Sector]:  # type: ignore # pyre-ignore[16,6]
        if not slug: return None
        return self.sector_cache.get(slug.lower()) or self.sector_cache.get("diğer")  # type: ignore # pyre-ignore[7]

    def _get_or_create_brands(self, names: List[str], sector_id: Optional[int]) -> List[uuid.UUID]:  # type: ignore # pyre-ignore[16,6]
        from src.services.brand_matcher import get_or_create_brands_list
        return get_or_create_brands_list(self.db, names, self.brand_cache, sector_id)

if __name__ == "__main__":
    max_c = 5 if os.environ.get('TEST_MODE') == '1' else 999
    scraper = VodafoneScraper(max_campaigns=max_c)
    scraper.run()
