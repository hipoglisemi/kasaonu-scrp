


import sys
import os

# Dynamic path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


import requests  # type: ignore # pyre-ignore[21]
import time  # type: ignore # pyre-ignore[21]
from typing import List, Dict, Any, Optional  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from decimal import Decimal  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
import hashlib  # type: ignore # pyre-ignore[21]
import re  # type: ignore # pyre-ignore[21]

from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import Session  # type: ignore # pyre-ignore[21]

from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked  # type: ignore

class ParafScraper:
    """
    Halkbank (Paraf & Parafly) Scraper
    Uses JSON API endpoints for fast, reliable data extraction.
    """
    
    SOURCES = [
        {
            "name": "Paraf",
            "api": "https://www.paraf.com.tr/content/parafcard/tr/kampanyalar/_jcr_content/root/responsivegrid/filter.filtercampaigns.all.json",
            "base": "https://www.paraf.com.tr",
            "default_card": "Paraf"
        },
        {
            "name": "Parafly",
            "api": "https://www.parafly.com.tr/content/parafly/tr/kampanyalar/_jcr_content/root/responsivegrid/filter.filtercampaigns.all.json",
            "base": "https://www.parafly.com.tr",
            "default_card": "Parafly"
        }
    ]
    
    def __init__(self, max_campaigns: int = 999):
        self.max_campaigns = max_campaigns
        self.db: Optional[Session] = None  # type: ignore # pyre-ignore[16,6]
        self.parser = AIParser()
        
        # Cache
        self.bank_cache: Optional[Bank] = None  # type: ignore # pyre-ignore[16,6]
        self.card_cache: Dict[str, Card] = {}  # type: ignore # pyre-ignore[16,6]
        self.sector_cache: Dict[str, Sector] = {}  # type: ignore # pyre-ignore[16,6]
        self.brand_cache: Dict[str, Brand] = {}  # type: ignore # pyre-ignore[16,6]

    def run(self, limit: Optional[int] = None, urls: Optional[List[str]] = None, force: bool = False):  # type: ignore # pyre-ignore[16,6]
        """Entry point for synchronous execution"""
        print(f"🚀 Starting Halkbank (Paraf/Parafly) API Scraper...")
        
        try:
            self.db = get_db_session()
            self._load_cache()
            
            for source in self.SOURCES:
                print(f"\n🌍 Processing Source: {source['name']}")  # type: ignore # pyre-ignore[16,6]
                self._process_source(source, limit=limit, urls=urls, force=force)
                
            print(f"\n✅ Scraping complete!")
            
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            import traceback  # type: ignore # pyre-ignore[21]
            traceback.print_exc()
        finally:
            if self.db:
                self.db.close()  # type: ignore # pyre-ignore[16]

    def _process_source(self, source: Dict, limit: Optional[int] = None, urls: Optional[List[str]] = None, force: bool = False):  # type: ignore # pyre-ignore[16,6]
        """Process a single API source (Paraf or Parafly)"""
        try:
            # 1. Fetch campaigns from API
            campaigns = self._fetch_campaigns(source)
            print(f"   Found {len(campaigns)} campaigns for {source['name']}")
            
            # Filter if specific URLs provided
            if urls:
                filtered = []
                for c in campaigns:
                    c_url = urljoin(source['base'], c.get('url', ''))
                    if c_url in urls:
                        filtered.append(c)
                campaigns = filtered
            elif limit:
                campaigns = campaigns[:limit]  # type: ignore # pyre-ignore[16,6]
            
            # 2. Process each campaign
            success_count = 0
            skipped_count = 0
            failed_count = 0
            for i, campaign_data in enumerate(campaigns, 1):
                url = urljoin(source['base'], campaign_data.get('url', ''))
                
                # Blocklist check
                if is_url_blocked(self.db, url):
                    title = campaign_data.get('title') or url
                    print(f"   [{i}/{len(campaigns)}] 🚫 Skipped (Blocklisted): {title}")
                    skipped_count = int(skipped_count or 0) + 1  # type: ignore
                    continue

                print(f"   [{i}/{len(campaigns)}] {url}")
                
                try:
                    res = self._scrape_detail(campaign_data, url, source, force=force)
                    if res == "saved":
                        success_count += 1  # type: ignore # pyre-ignore[58]
                    elif res == "skipped":
                        skipped_count += 1  # type: ignore # pyre-ignore[58]
                    else:
                        failed_count += 1  # type: ignore # pyre-ignore[58]
                    time.sleep(1)  # Rate limiting
                except Exception as e:
                    print(f"      ❌ Error: {e}")
                    failed_count += 1  # type: ignore # pyre-ignore[58]
                    
            print(f"   ✅ Özet: {len(campaigns)} bulundu, {success_count} eklendi, {skipped_count} atlandı, {failed_count} hata aldı.")
            
            # Log execution to Database
            log_scraper_execution(
                db=self.db,
                scraper_name=source['name'].lower(),
                status="SUCCESS" if failed_count == 0 else ("PARTIAL" if success_count > 0 else "FAILED"),  # type: ignore # pyre-ignore[58]
                total_found=len(campaigns),
                total_saved=success_count,
                total_skipped=skipped_count,
                total_failed=failed_count
            )
            
        except Exception as e:
            print(f"   ❌ Source Error: {e}")
            import traceback  # type: ignore # pyre-ignore[21]
            error_details = {"traceback": traceback.format_exc(), "error": str(e)}
            log_scraper_execution(
                db=self.db,
                scraper_name=source['name'].lower(),
                status="FAILED",
                error_details=error_details
            )
            traceback.print_exc()

    def _fetch_campaigns(self, source: Dict) -> List[Dict]:  # type: ignore # pyre-ignore[16,6]
        """Fetch campaigns from JSON API"""
        try:
            response = requests.get(source['api'], timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if isinstance(data, list):
                return data  # type: ignore # pyre-ignore[7]
            elif isinstance(data, dict) and 'campaigns' in data:
                return data['campaigns']  # type: ignore # pyre-ignore[7]
            return []  # type: ignore # pyre-ignore[7]
                
        except Exception as e:
            print(f"      ❌ API Fetch Error: {e}")
            return []  # type: ignore # pyre-ignore[7]

    def _scrape_detail(self, campaign_data: Dict, url: str, source: Dict, force: bool = False) -> str:
        """Scrape single campaign detail page"""
        
        # Check if exists
        if not force:
            existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore # pyre-ignore[16]
            if existing:
                print(f"      ⏭️ Skipped (Already exists): {existing.title[:40]}")
                return "skipped"  # type: ignore # pyre-ignore[7]

        # Final blocklist check
        if is_url_blocked(self.db, url):
            print(f"      🚫 Skipped (Safety Check: Blocklisted): {title if 'title' in locals() else url}")
            return "skipped"  # type: ignore # pyre-ignore[7]

        try:
            # Fetch detail page for full conditions text
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract og:title for better cleaning anchors
            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            # Extract FULL BODY for Autofix-standard global cleaning
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else response.text
            
            # AI Parse (Autofix-standard)
            from src.services.ai_parser import parse_api_campaign
            ai_data = parse_api_campaign(
                title=title,
                short_description=None,
                content_html=raw_html,
                bank_name="Halkbank",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            )
            
            if not ai_data:
                print("      ❌ AI parsing failed")
                return "error"  # type: ignore # pyre-ignore[7]
                
            # Save
            self._save_campaign(ai_data, url, image_url, source['default_card'])
            print(f"      ✅ Saved: {ai_data['title']}")  # type: ignore # pyre-ignore[16,6]
            return "saved"  # type: ignore # pyre-ignore[7]
            
        except Exception as e:
            print(f"      ❌ Page Error: {e}")
            return "error"  # type: ignore # pyre-ignore[7]

    def _fix_image_url(self, image_path: str, base_url: str) -> str:
        """Convert relative image paths to absolute URLs"""
        if not image_path:
            return "https://www.paraf.com.tr/content/dam/parafcard/paraf-logos/paraf-logo-yeni.png"  # type: ignore # pyre-ignore[7]
        
        # Already absolute
        if image_path.startswith('http'):
            return image_path  # type: ignore # pyre-ignore[7]
        
        # Relative path
        if image_path.startswith('/'):
            return f"{base_url}{image_path}"  # type: ignore # pyre-ignore[7]
        
        return image_path  # type: ignore # pyre-ignore[7]

    def _save_campaign(self, data: Dict[str, Any], url: str, image_url: str, card_name: str):  # type: ignore # pyre-ignore[16,6]
        """Save to DB"""
        
        # Card
        target_cards = data.get("cards", [])
        if not target_cards:
            target_cards = [card_name]
        
        # Bütün Parafly kampanyalarının Paraf'a kaymasını engellemek için AI'ın bulduğu ilk kart yerine, 
        # scraper'ın çalıştığı asıl kaynağın adını (Paraf veya Parafly) baz alıyoruz.
        primary_card = self._get_or_create_card(card_name)
        
        # Sector
        sector = self._get_sector(data.get("sector"))
        
        # Brands
        brand_ids = self._get_or_create_brands(data.get("brands", []), sector.id if sector else None)  # type: ignore # pyre-ignore[16]
        
        # Slug Generation
        slug = data.get("slug")
        if not slug:
            # Turkish char replacement
            text = data.get("title", "").lower()
            text = text.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")
            slug = re.sub(r'[^a-z0-9-]', '-', text)
            slug = re.sub(r'-+', '-', slug).strip('-')
            # Add URL hash for uniqueness
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]  # type: ignore # pyre-ignore[16,6]
            slug = f"{slug}-{url_hash}"
        
        # Prepare marketing text with participation method
        participation = data.get("participation", "")
        marketing_text = data.get("ai_marketing_text") or data.get("description", "")
        if participation:
            marketing_text = f"{marketing_text}\n\n📱 Katılım: {participation}"
        
        # Map card logo URL based on eligible cards
        card_logo_url = None
        if target_cards:
            first_card = target_cards[0].lower()
            if "paraf troy" in first_card:
                card_logo_url = "https://www.paraf.com.tr/content/dam/parafcard/paraf-logos/paraf-troy-logo.png"
            elif "parafly" in first_card:
                card_logo_url = "https://www.parafly.com.tr/content/dam/parafly/parafly-logos/parafly-logo.png"
            elif "paraf" in first_card:
                card_logo_url = "https://www.paraf.com.tr/content/dam/parafcard/paraf-logos/paraf-logo-yeni.png"
        
        campaign = Campaign(  # type: ignore
            card_id=primary_card.id,  # type: ignore 
            sector_id=sector.id if sector else None,  # type: ignore 
            title=data.get("title"),  # type: ignore 
            slug=slug,  # type: ignore 
            description=data.get("description"),  # type: ignore 
            conditions="\n".join(data.get("conditions", [])),  # type: ignore 
            start_date=data.get("start_date"),  # type: ignore 
            end_date=data.get("end_date"),  # type: ignore 
            reward_type=data.get("reward_type"),  # type: ignore 
            reward_value=data.get("reward_value"),  # type: ignore 
            reward_text=data.get("reward_text"),  # type: ignore 
            
            # AI Fields
            ai_marketing_text=marketing_text,  # type: ignore 
            eligible_cards=", ".join(target_cards),  # type: ignore 
            category=data.get("category"),  # type: ignore 
            badge_color=data.get("badge_color"),  # type: ignore 
            card_logo_url=card_logo_url,  # type: ignore 
            
            clean_text=data.get('_clean_text'),  # type: ignore 
            tracking_url=url,  # type: ignore 
            image_url=image_url,  # type: ignore 
            participation=data.get("participation"), # type: ignore
            is_active=True  # type: ignore
        )
        
        if self.db is None: return
        self.db.add(campaign)  # type: ignore # pyre-ignore[16]
        self.db.commit()  # type: ignore # pyre-ignore[16]
        
        # Link Brands
        for bid in brand_ids:
            try:
                cb = CampaignBrand(campaign_id=campaign.id, brand_id=bid)  # type: ignore # pyre-ignore[16]
                self.db.add(cb)  # type: ignore # pyre-ignore[16]
            except:
                pass
        self.db.commit()  # type: ignore # pyre-ignore[16]

    # --- HELPERS ---
    def _load_cache(self):
        bank = self.db.query(Bank).filter(Bank.slug == "halkbank").first()  # type: ignore # pyre-ignore[16]
        if not bank:
            bank = Bank(name="Halkbank", slug="halkbank", is_active=True)
            self.db.add(bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
        self.bank_cache = bank
        
        for c in self.db.query(Card).filter(Card.bank_id == bank.id).all():  # type: ignore # pyre-ignore[16]
            self.card_cache[c.name.lower()] = c
            
        for s in self.db.query(Sector).all():  # type: ignore # pyre-ignore[16]
            self.sector_cache[s.slug] = s
            # Fallback for names
            self.sector_cache[s.name.lower()] = s
            
        for b in self.db.query(Brand).all():  # type: ignore # pyre-ignore[16]
            self.brand_cache[b.name.lower()] = b

    def _get_or_create_card(self, name: str) -> Card:
        """Get or create card, but only for known Paraf variants."""
        name_lower = name.lower()
        
        # Prevent AI from creating variants like "Paraf Gold", "Paraf Platinum" etc.
        if "parafly" in name_lower or "fly" in name_lower:
            name = "Parafly"
        elif "troy" in name_lower:
            name = "Paraf TROY"
        else:
            name = "Paraf" # Default all others to main "Paraf"
            
        key = name.lower()
        if key in self.card_cache:
            return self.card_cache[key]  # type: ignore # pyre-ignore[7]
        
        # If not in cache, check DB
        slug_val = name.lower().replace(" ", "-")
        card = self.db.query(Card).filter(  # type: ignore # pyre-ignore[16]
            Card.bank_id == self.bank_cache.id,  # type: ignore # pyre-ignore[16]
            Card.slug == slug_val
        ).first()
        
        if not card:
            print(f"   ➕ Creating standard card: {name}")
            card = Card(
                bank_id=self.bank_cache.id,  # type: ignore # pyre-ignore[16]
                name=name,
                slug=name.lower().replace(" ", "-"),
                is_active=True
            )
            self.db.add(card)  # type: ignore # pyre-ignore[16]
            self.db.flush()  # type: ignore # pyre-ignore[16]
            
        self.card_cache[key] = card
        return card  # type: ignore # pyre-ignore[7]

    def _get_sector(self, slug: Optional[str]) -> Optional[Sector]:  # type: ignore # pyre-ignore[16,6]
        if not slug:
            return None  # type: ignore # pyre-ignore[7]
        return self.sector_cache.get(slug.lower()) or self.sector_cache.get("diğer")  # type: ignore # pyre-ignore[7]

    def _get_or_create_brands(self, names: List[str], sector_id: int) -> List[int]:
        from src.services.brand_matcher import get_or_create_brands_list
        return get_or_create_brands_list(self.db, names, self.brand_cache, sector_id)
if __name__ == "__main__":
    try:
        import argparse  # type: ignore # pyre-ignore[21]
        parser = argparse.ArgumentParser()
        parser.add_argument("--limit", type=int, help="Limit campaigns")
        parser.add_argument("--force", action="store_true", help="Force refresh")
        args = parser.parse_args()
        
        scraper = ParafScraper()
        scraper.run(limit=args.limit, force=args.force)
    except Exception as e:
        import traceback  # type: ignore # pyre-ignore[21]
        traceback.print_exc()
        print(f"CRITICAL ERROR: {e}")
