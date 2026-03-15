



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
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]

class TurkTelekomScraper:
    """
    Türk Telekom Mobil Kampanyaları Scraper
    Uses Requests/BeautifulSoup for high efficiency since content is SSR.
    """
    
    BASE_URL = "https://bireysel.turktelekom.com.tr"
    LISTING_URL = "https://bireysel.turktelekom.com.tr/mobil/kampanyalar"
    
    def __init__(self, max_campaigns: int = 40, headless: bool = True):
        self.max_campaigns = max_campaigns
        # headless param kept for compatibility with other scrapers even if not used here
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
        print(f"🚀 Starting Türk Telekom Scraper (Request Mode)...")
        
        try:
            self.db = get_db_session()
            self._load_cache()
            
            # 1. Get List
            links = self._scrape_list()
            print(f"   Found {len(links)} campaigns in total.")
            
            # Limit
            if len(links) > self.max_campaigns:
                links = links[:self.max_campaigns]  # type: ignore # pyre-ignore[16,6]
            
            # 2. Process Details
            success_count = 0
            for i, url in enumerate(links, 1):
                print(f"   [{i}/{len(links)}] {url}")
                try:
                    if self._scrape_detail(url):
                        success_count += 1  # type: ignore # pyre-ignore[58]
                    # Small delay to be polite
                    time.sleep(random.uniform(0.5, 1.5))
                except Exception as e:
                    print(f"      ❌ Error processing {url}: {e}")
            
            print(f"\n✅ Scraping complete! Saved {success_count} campaigns.")

        except Exception as e:
            print(f"❌ Fatal error in Türk Telekom scraper: {e}")
            import traceback  # type: ignore # pyre-ignore[21]
            traceback.print_exc()
        finally:
            if self.db:
                self.db.close()  # type: ignore # pyre-ignore[16]

    def _scrape_list(self) -> List[str]:  # type: ignore # pyre-ignore[16,6]
        """Fetch listing page and extract campaign links"""
        print(f"   🌐 Loading listing page: {self.LISTING_URL}")
        try:
            response = requests.get(self.LISTING_URL, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            links = []
            # Extract links containing /mobil/kampanyalar/
            # The structure observed in browser: <a href="/mobil/kampanyalar/akaryakit-kampanyasi-petrol-ofisi-hediye-yakit-puan-kazandiriyor" ...>
            for a in soup.find_all('a', href=True):
                href = a['href']
                if "/mobil/kampanyalar/" in href and not href.endswith("/mobil/kampanyalar") and not "#" in href:
                    full_url = urljoin(self.BASE_URL, href)
                    if full_url not in links:
                        # Filter out category links if any (though usually they are nested deeper)
                        links.append(full_url)
            
            return links  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"   ❌ List extraction failed: {e}")
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
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else "Türk Telekom Kampanyası"

            # Final blocklist check with title
            if is_url_blocked(self.db, url):
                print(f"      🚫 Skipping (Blocklisted): {title}")
                return False  # type: ignore # pyre-ignore[7]
            
            # Image extraction
            img_tag = soup.select_one(".detail-text-img img")
            image_url = urljoin(self.BASE_URL, img_tag['src']) if img_tag else None
            
            # 3. Extract Accordion Content
            # Research showed .accordion-header and .accordion-content
            accordion_items = soup.select(".accordion")
            content_parts = []
            participation_text = ""

            # Sometimes the headers and contents are direct children of a container
            headers = soup.select(".accordion-header")
            for header in headers:
                header_text = header.get_text(strip=True)
                # The content is usually the next sibling or a sibling with .accordion-content
                content_div = header.find_next_sibling(class_="accordion-content")
                if not content_div:
                    # Alternative structure check
                    parent = header.parent
                    content_div = parent.find(class_="accordion-content")
                
                if content_div:
                    text = content_div.get_text(separator="\n", strip=True)
                    if text:
                        content_parts.append(f"### {header_text}\n{text}")
                        # Categorize for AI context
                        lower_header = header_text.lower()
                        if any(x in lower_header for x in ["katılım", "nasil", "faydalan", "detay"]):  # type: ignore # pyre-ignore[16,6]
                            participation_text += f"\n[{header_text}]: {text}"  # type: ignore # pyre-ignore[58,16,6]

            if not content_parts:
                # Fallback: check for .detail-page text
                detail_page = soup.select_one(".detail-page")
                raw_text = detail_page.get_text(separator="\n", strip=True) if detail_page else soup.get_text(separator="\n", strip=True)
            else:
                raw_text = "\n\n".join(content_parts)

            # Special Participation metadata
            if participation_text:
                raw_text = f"--- TÜRK TELEKOM DETAYLAR ---\n{participation_text}\n\n--- TÜM İÇERİK ---\n{raw_text}"

            # AI Parsing
            print(f"      🧠 Sending to AI Parser...")
            ai_data = self.parser.parse_campaign_data(
                raw_text=raw_text,
                title=title,
                bank_name="turk-telekom",
                card_name="Türk Telekom"
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
        card = self._get_or_create_card("Türk Telekom")
        
        # Sector
        sector = self._get_sector(data.get("sector"))
        
        # Brands
        brand_ids = self._get_or_create_brands(data.get("brands", []), sector.id if sector else None)  # type: ignore # pyre-ignore[16]
        
        # Slug
        slug = data.get("slug")
        if not slug:
            clean_title = data.get("title", "").lower()
            # Basic TR char normalize
            tr_map = str.maketrans("ığüşöç", "iguso-")
            clean_title = clean_title.translate(tr_map)
            slug = re.sub(r'[^a-z0-9-]', '-', clean_title)
            slug = re.sub(r'-+', '-', slug).strip('-')
            url_hash = uuid.uuid5(uuid.NAMESPACE_URL, url).hex[:8]  # type: ignore # pyre-ignore[16,6]
            slug = f"{slug}-{url_hash}"
        
        # Format for CampaignDetailClient.tsx
        participation = data.get("participation", "")
        ai_description = data.get("marketing_text") or data.get("description", "")
        
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
            conditions=data.get("conditions") if not isinstance(data.get("conditions"), list) else "\n".join(data.get("conditions")),
            reward_text=data.get("reward_text"),
            reward_value=data.get("reward_value"),
            reward_type=data.get("reward_type"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            image_url=image_url or "https://bireysel.turktelekom.com.tr/assets/img/tt-logo.png",
            tracking_url=url,
            is_active=True,
            ai_marketing_text=ai_marketing_text,
            eligible_cards="Türk Telekom Müşterileri",
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
        bank = self.db.query(Bank).filter(Bank.slug == "turk-telekom").first()  # type: ignore # pyre-ignore[16]
        if not bank:
            bank = Bank(name="Türk Telekom", slug="turk-telekom", is_active=True, logo_url="https://upload.wikimedia.org/wikipedia/tr/a/a2/T%C3%BCrk_Telekom_Logo.png")
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
        ids = []
        for n in names:
            if not n: continue
            key = n.lower().strip()
            if key in self.brand_cache:
                ids.append(self.brand_cache[key].id)
            else:
                brand = self.db.query(Brand).filter(Brand.name.ilike(n)).first()  # type: ignore # pyre-ignore[16]
                if not brand:
                    brand = Brand(name=n, slug=key.replace(" ", "-")[:50], is_active=True)  # type: ignore # pyre-ignore[16,6]
                    self.db.add(brand)  # type: ignore # pyre-ignore[16]
                    self.db.flush()  # type: ignore # pyre-ignore[16]
                self.brand_cache[key] = brand
                ids.append(brand.id)
        return list(set(ids))  # type: ignore # pyre-ignore[7]

if __name__ == "__main__":
    scraper = TurkTelekomScraper(max_campaigns=999)
    scraper.run()
