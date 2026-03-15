


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
from src.utils.scraper_utils import is_url_blocked  # type: ignore

class ParafGencScraper:
    """
    Halkbank (Paraf Genç) Scraper
    Uses JSON API endpoints for fast, reliable data extraction.
    """
    
    SOURCES = [
        {
            "name": "Paraf Genç",
            "api": "https://www.parafgenc.com.tr/content/parafree/tr/kampanyalar/_jcr_content/root/responsivegrid/filter.filtercampaigns.all.json",
            "base": "https://www.parafgenc.com.tr",
            "default_card": "Paraf Genç"
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

    def run(self):
        """Entry point for synchronous execution"""
        print(f"🚀 Starting Halkbank (Paraf Genç) API Scraper...")
        
        try:
            self.db = get_db_session()
            self._load_cache()
            
            for source in self.SOURCES:
                print(f"\n🌍 Processing Source: {source['name']}")  # type: ignore # pyre-ignore[16,6]
                self._process_source(source)
                
            print(f"\n✅ Scraping complete!")
            
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            import traceback  # type: ignore # pyre-ignore[21]
            traceback.print_exc()
        finally:
            if self.db:
                self.db.close()  # type: ignore # pyre-ignore[16]

    def _process_source(self, source: Dict):
        """Process a single API source"""
        try:
            # 1. Fetch campaigns from API
            campaigns = self._fetch_campaigns(source)
            print(f"   Found {len(campaigns)} campaigns for {source['name']}")
            
            # Limit
            if len(campaigns) > self.max_campaigns:
                campaigns = campaigns[:self.max_campaigns]  # type: ignore # pyre-ignore[16,6]
            
            # 2. Process each campaign
            success_count = 0
            skipped_count = 0
            failed_count = 0
            error_details = []
            for i, campaign_data in enumerate(campaigns, 1):
                url = urljoin(source['base'], campaign_data.get('url', ''))
                
                # Blocklist check
                if is_url_blocked(self.db, url):
                    print(f"   [{i}/{len(campaigns)}] 🚫 Skipped (Blocklisted): {url}")
                    skipped_count = int(skipped_count or 0) + 1
                    continue

                print(f"   [{i}/{len(campaigns)}] {url}")
                
                try:
                    res = self._scrape_detail(campaign_data, url, source)
                    if res == "saved":
                        success_count += 1  # type: ignore # pyre-ignore[58]
                    elif res == "skipped":
                        skipped_count += 1  # type: ignore # pyre-ignore[58]
                    else:
                        failed_count += 1  # type: ignore # pyre-ignore[58]
                        error_details.append({"url": url, "error": "Unknown DB failure"})
                        
                    time.sleep(1)  # Rate limiting
                except Exception as e:
                    print(f"      ❌ Error: {e}")
                    failed_count += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": url, "error": str(e)})
                    
            print(f"   ✅ Özet: {len(campaigns)} bulundu, {success_count} eklendi, {skipped_count + failed_count} atlandı/hata aldı.")
            
            status = "SUCCESS"
            if failed_count > 0:  # type: ignore # pyre-ignore[58]
                 status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
                 
            try:
                from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
                log_scraper_execution(
                     db=self.db,
                     scraper_name="paraf-genc",
                     status=status,
                     total_found=len(campaigns),
                     total_saved=success_count,
                     total_skipped=skipped_count,
                     total_failed=failed_count,
                     error_details={"errors": error_details} if error_details else None
                )
            except Exception as le:
                 print(f"⚠️ Could not save scraper log: {le}")
            
        except Exception as e:
            print(f"   ❌ Source Error: {e}")
            try:
                from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
                log_scraper_execution(self.db, "paraf-genc", "FAILED", 0, 0, 0, 1, {"error": str(e)})
            except:
                pass
            import traceback  # type: ignore # pyre-ignore[21]
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
            else:
                return []  # type: ignore # pyre-ignore[7]
                
        except Exception as e:
            print(f"      ❌ API Fetch Error: {e}")
            return []  # type: ignore # pyre-ignore[7]

    def _scrape_detail(self, campaign_data: Dict, url: str, source: Dict) -> bool:
        """Scrape single campaign detail page"""
        
        # Check if exists
        existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore # pyre-ignore[16]
        if existing:
            print(f"      ⏭️ Skipped (Already exists): {existing.title[:40]}")
            return "skipped"  # type: ignore # pyre-ignore[7]

        # Final blocklist check
        if is_url_blocked(self.db, url):
            print(f"      🚫 Skipped (Safety Check: Blocklisted)")
            return "skipped"  # type: ignore # pyre-ignore[7]

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title_el = soup.select_one('h1') or soup.select_one('.cmp-title__text')
            title = title_el.get_text(strip=True) if title_el else campaign_data.get('title', 'Kampanya')
            
            # Extract full conditions text - Adaptive for Paraf Genç
            content_div = soup.select_one('.cmp-text')
            if not content_div:
                content_div = soup.select_one('.text-area')
            
            raw_text = content_div.get_text(separator='\n', strip=True) if content_div else ""
            
            if len(raw_text) < 30:
                print("      ❌ Content too short")
                return "skipped"  # type: ignore # pyre-ignore[7]

            # Fix image URL
            image_url = self._fix_image_url(
                campaign_data.get('teaserImage') or campaign_data.get('logoImage'),
                source['base']
            )
            
            # AI Parse
            ai_data = self.parser.parse_campaign_data(
                raw_text=raw_text,
                title=title,
                bank_name="halkbank",
                card_name=source['default_card']
            )
            
            if not ai_data:
                print("      ❌ AI parsing failed")
                return "error"  # type: ignore # pyre-ignore[7]
                
            # Save
            return self._save_campaign(ai_data, url, image_url, source['default_card'])  # type: ignore # pyre-ignore[7]
            
        except Exception as e:
            print(f"      ❌ Page Error: {e}")
            return "error"  # type: ignore # pyre-ignore[7]

    def _fix_image_url(self, image_path: str, base_url: str) -> str:
        """Convert relative image paths to absolute URLs"""
        if not image_path:
            return "https://www.parafgenc.com.tr/content/dam/parafree/paraf-genc-logolar/paraf-genc-logo.png"  # type: ignore # pyre-ignore[7]
        if image_path.startswith('http'):
            return image_path  # type: ignore # pyre-ignore[7]
        if image_path.startswith('/'):
            return f"{base_url}{image_path}"  # type: ignore # pyre-ignore[7]
        return image_path  # type: ignore # pyre-ignore[7]

    def _save_campaign(self, data: Dict[str, Any], url: str, image_url: str, card_name: str):  # type: ignore # pyre-ignore[16,6]
        """Save to DB"""
        try:
            # Refresh card cache to avoid stale objects
            primary_card = self._get_or_create_card(card_name)
            
            # Sector
            sector = self._get_sector(data.get("sector"))
            
            # Brands
            brand_ids = self._get_or_create_brands(data.get("brands", []), sector.id if sector else None)  # type: ignore # pyre-ignore[16]
            
            # Slug
            text = data.get("title", "").lower()
            text = text.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")
            slug = re.sub(r'[^a-z0-9-]', '-', text)
            slug = re.sub(r'-+', '-', slug).strip('-')
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]  # type: ignore # pyre-ignore[16,6]
            slug = f"{slug}-{url_hash}"
            
            campaign = Campaign(
                card_id=primary_card.id,  # type: ignore # pyre-ignore[16]
                sector_id=sector.id if sector else None,  # type: ignore # pyre-ignore[16]
                title=data.get("title"),
                slug=slug,
                description=data.get("description"),
                conditions="\n".join(data.get("conditions", [])),
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
                reward_type=data.get("reward_type"),
                reward_value=data.get("reward_value"),
                reward_text=data.get("reward_text"),
                ai_marketing_text=data.get("description"),
                eligible_cards=card_name,
                category=data.get("category"),
                badge_color=data.get("badge_color"),
                card_logo_url="https://www.parafgenc.com.tr/content/dam/parafree/paraf-genc-logolar/paraf-genc-logo.png",
                clean_text=data.get('_clean_text'),
                tracking_url=url,
                image_url=image_url,
                is_active=True
            )
            
            if self.db is None: return "error"
            self.db.add(campaign)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
            
            for bid in brand_ids:
                try:
                    cb = CampaignBrand(campaign_id=campaign.id, brand_id=bid)  # type: ignore # pyre-ignore[16]
                    self.db.add(cb)  # type: ignore # pyre-ignore[16]
                except: pass
            self.db.commit()  # type: ignore # pyre-ignore[16]
            return "saved"  # type: ignore # pyre-ignore[7]
            
        except Exception as e:
            print(f"      ❌ Save error: {e}")
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            return "error"  # type: ignore # pyre-ignore[7]

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
            self.sector_cache[s.name.lower()] = s
        for b in self.db.query(Brand).all():  # type: ignore # pyre-ignore[16]
            self.brand_cache[b.name.lower()] = b

    def _get_or_create_card(self, name: str) -> Card:
        key = name.lower()
        if key in self.card_cache:
            return self.card_cache[key]  # type: ignore # pyre-ignore[7]
        
        slug_val = name.lower().replace(" ", "-")
        card = self.db.query(Card).filter(Card.bank_id == self.bank_cache.id, Card.slug == slug_val).first()  # type: ignore # pyre-ignore[16]
        if not card:
            card = Card(bank_id=self.bank_cache.id, name=name, slug=slug_val, is_active=True)  # type: ignore # pyre-ignore[16]
            self.db.add(card)  # type: ignore # pyre-ignore[16]
            self.db.flush()  # type: ignore # pyre-ignore[16]
        self.card_cache[key] = card
        return card  # type: ignore # pyre-ignore[7]

    def _get_sector(self, slug: str) -> Optional[Sector]:  # type: ignore # pyre-ignore[16,6]
        if not slug: return None
        return self.sector_cache.get(slug.lower(), self.sector_cache.get("diğer"))  # type: ignore # pyre-ignore[7]

    def _get_or_create_brands(self, names: List[str], sector_id: int) -> List[int]:  # type: ignore # pyre-ignore[16,6]
        ids = []
        for n in names:
            key = n.lower()
            if key in self.brand_cache:
                ids.append(self.brand_cache[key].id)
            else:
                b = Brand(name=n, slug=key.replace(" ", "-"), is_active=True)
                self.db.add(b)  # type: ignore # pyre-ignore[16]
                self.db.commit()  # type: ignore # pyre-ignore[16]
                self.brand_cache[key] = b
                ids.append(b.id)
        return ids  # type: ignore # pyre-ignore[7]

if __name__ == "__main__":
    scraper = ParafGencScraper()
    scraper.run()
