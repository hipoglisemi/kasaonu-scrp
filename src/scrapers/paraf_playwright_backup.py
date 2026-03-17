



import asyncio  # type: ignore # pyre-ignore[21]
import random  # type: ignore # pyre-ignore[21]
import time  # type: ignore # pyre-ignore[21]
from typing import List, Dict, Any, Optional  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from decimal import Decimal  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]

from playwright.async_api import async_playwright, Page  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import Session  # type: ignore # pyre-ignore[21]
from src.services.brand_matcher import get_or_create_brands_list

from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]

class ParafScraper:
    """
    Halkbank (Paraf & Parafly) Scraper
    Uses Playwright for dynamic content and AI for parsing.
    """
    
    SOURCES = [
        {
            "base": "https://www.paraf.com.tr",
            "start": "https://www.paraf.com.tr/tr/kampanyalar.html",
            "name": "Paraf",
            "default_card": "Paraf"
        },
        {
            "base": "https://www.parafly.com.tr",
            "start": "https://www.parafly.com.tr/tr/kampanyalar.html",
            "name": "Parafly",
            "default_card": "Parafly"
        }
    ]
    
    def __init__(self, max_campaigns: int = 999, headless: bool = True):
        self.max_campaigns = max_campaigns
        self.headless = headless
        self.db: Optional[Session] = None  # type: ignore # pyre-ignore[16,6]
        self.parser = AIParser() # Singleton
        
        # Cache
        self.bank_cache: Optional[Bank] = None  # type: ignore # pyre-ignore[16,6]
        self.card_cache: Dict[str, Card] = {}  # type: ignore # pyre-ignore[16,6]
        self.sector_cache: Dict[str, Sector] = {}  # type: ignore # pyre-ignore[16,6]
        self.brand_cache: Dict[str, Brand] = {}  # type: ignore # pyre-ignore[16,6]

    def run(self):
        """Entry point for synchronous execution"""
        asyncio.run(self._run_async())

    async def _run_async(self):
        """Main async execution flow"""
        print(f"🚀 Starting Halkbank (Paraf/Parafly) Scraper...")
        
        try:
            self.db = get_db_session()
            self._load_cache()
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                
                for source in self.SOURCES:
                    print(f"\n🌍 Processing Source: {source['name']}")  # type: ignore # pyre-ignore[16,6]
                    await self._process_source(context, source)
                
                await browser.close()  # type: ignore # pyre-ignore[16]
                
            print(f"\n✅ Scraping complete!")

        except Exception as e:
            print(f"❌ Fatal error: {e}")
        finally:
            if self.db:
                self.db.close()  # type: ignore # pyre-ignore[16]

    async def _process_source(self, context, source: Dict):
        """Process a single website (Paraf or Parafly)"""
        page = await context.new_page()
        try:
            # 1. Get List
            links = await self._scrape_list(page, source['start'], source['base'])
            print(f"   Found {len(links)} campaigns for {source['name']}")
            
            # Limit
            if len(links) > self.max_campaigns:
                links = links[:self.max_campaigns]  # type: ignore # pyre-ignore[16,6]
            
            # 2. Process Details
            success_count = 0
            for i, url in enumerate(links, 1):
                print(f"   [{i}/{len(links)}] {url}")
                try:
                    if await self._scrape_detail(context, url, source):
                        success_count += 1  # type: ignore # pyre-ignore[58]
                    await asyncio.sleep(random.uniform(1, 2))
                except Exception as e:
                    print(f"      ❌ Error: {e}")
                    
        finally:
            await page.close()  # type: ignore # pyre-ignore[16]

    async def _scrape_list(self, page: Page, start_url: str, base_url: str) -> List[str]:  # type: ignore # pyre-ignore[16,6]
        """Scroll and load more to get all links"""
        print(f"   🌐 Loading {start_url}...")
        try:
            await page.goto(start_url, timeout=10000)
            
            # Click "Load More" loop
            max_clicks = 5 # Limit for testing, increase for prod
            for i in range(max_clicks):
                try:
                    # Scroll bottom
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)
                    
                    # Check button
                    button = await page.query_selector(".button--more-campaign a, .load-more-btn")
                    if button and await button.is_visible():
                        text = await button.inner_text()
                        if "DAHA FAZLA" in text.upper():
                            print(f"      👇 Clicked 'Load More' ({i+1})")
                            await button.click()
                            await asyncio.sleep(2) # Wait for content
                        else:
                            break
                    else:
                        break
                except:
                    break
        except Exception as e:
            print(f"   ❌ List Load Error: {e}")
            return []  # type: ignore # pyre-ignore[7]
        
        # Extract Links
        links = []
        # Selector based on legacy analysis
        elements = await page.query_selector_all('.cmp-list--campaigns .cmp-teaser__title a')
        
        for el in elements:
            href = await el.get_attribute('href')
            if href and "/kampanyalar/" in href and not href.endswith("kampanyalar.html"):
                full_url = urljoin(base_url, href)
                if full_url not in links:
                    links.append(full_url)
                    
        return links  # type: ignore # pyre-ignore[7]

    async def _scrape_detail(self, context, url: str, source: Dict) -> bool:
        """Scrape single campaign page"""
        
        # Check if exists
        existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore # pyre-ignore[16]
        if existing:
            print(f"      ⚠️ Skipping (Already exists)")
            return False  # type: ignore # pyre-ignore[7]

        page = await context.new_page()
        try:
            await page.goto(url, timeout=45000)
            
            # Content Extraction
            html = await page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Title
            title_el = soup.select_one('h1')
            title = title_el.get_text(strip=True) if title_el else "Kampanya"
            
            # Text Content
            # Legacy selector: .text--use-ulol .cmp-text OR .text-area
            content_div = soup.select_one('.text--use-ulol .cmp-text')
            if not content_div:
                content_div = soup.select_one('.text-area')
            
            raw_text = content_div.get_text(separator='\n', strip=True) if content_div else await page.evaluate("document.body.innerText")
            
            # Validations similar to generic scraper
            if len(raw_text) < 50:
                print("      ❌ Content too short")
                return False  # type: ignore # pyre-ignore[7]

            # Image Extraction
            image_url = await self._extract_image(page, source['base'])
            
            # AI Parse
            ai_data = self.parser.parse_campaign_data(
                raw_text=raw_text,
                title=title,
                bank_name="halkbank", # Triggers our rules
                card_name=source['default_card']
            )
            
            if not ai_data:
                return False  # type: ignore # pyre-ignore[7]
                
            # Save
            self._save_campaign(ai_data, url, image_url, source['default_card'])
            print(f"      ✅ Saved: {ai_data['title']}")  # type: ignore # pyre-ignore[16,6]
            return True  # type: ignore # pyre-ignore[7]
            
        except Exception as e:
            print(f"      ❌ Page Error: {e}")
            return False  # type: ignore # pyre-ignore[7]
        finally:
            await page.close()  # type: ignore # pyre-ignore[16]
        return False

    async def _extract_image(self, page: Page, base_url: str) -> Optional[str]:  # type: ignore # pyre-ignore[16,6]
        """Extract CSS background image or img tag"""
        return await page.evaluate(f'''() => {{  # type: ignore # pyre-ignore[7]
            const baseUrl = '{base_url}';
            let image = null;
            
            // 1. Banner Background
            const banner = document.querySelector('.master-banner__image');
            if (banner && banner.style.backgroundImage) {{
                const match = banner.style.backgroundImage.match(/url\\(['"]?(.*?)['"]?\\)/);
                if (match) image = match[1];
            }}
            
            // 2. Content Image
            if (!image) {{
                const img = document.querySelector('.subpage-detail img, .cmp-text img');
                if (img) image = img.getAttribute('src');
            }}
            
            if (image) {{
                if (image.includes('logo')) return null;
                if (image.startsWith('//')) return 'https:' + image;
                if (image.startsWith('/')) return baseUrl + image;
                return image;  # type: ignore # pyre-ignore[7]
            }}
            return null;  # type: ignore # pyre-ignore[7]
        }}''')

    def _save_campaign(self, data: Dict[str, Any], url: str, image_url: Optional[str], card_name: str):  # type: ignore # pyre-ignore[16,6]
        """Save to DB"""
        
        # Card
        # AI might find specific cards, but we default to source's card if empty
        target_cards = data.get("cards", [])
        if not target_cards: target_cards = [card_name]  # type: ignore # pyre-ignore[16,6]
        
        # Primary card is the first one found or default
        primary_card = self._get_or_create_card(target_cards[0])
        
        # Sector
        sector = self._get_sector(data.get("sector"))
        
        # Brands
        brand_ids = self._get_or_create_brands(data.get("brands", []), sector.id if sector else None)  # type: ignore # pyre-ignore[16]
        
        # Slug Generation
        slug = data.get("slug")
        if not slug:
            import re  # type: ignore # pyre-ignore[21]
            import hashlib  # type: ignore # pyre-ignore[21]
            # Turkish char replacement
            text = data.get("title", "").lower()
            text = text.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c")
            slug = re.sub(r'[^a-z0-9-]', '-', text)
            slug = re.sub(r'-+', '-', slug).strip('-')
            # Add URL hash for uniqueness
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]  # type: ignore # pyre-ignore[16,6]
            slug = f"{slug}-{url_hash}"
        
        campaign = Campaign(
            card_id=primary_card.id,  # type: ignore # pyre-ignore[16]
            sector_id=sector.id if sector else None,  # type: ignore # pyre-ignore[16]
            title=data.get("title"),
            slug=slug, # Use generated slug
            description=data.get("description"), # Combined title+desc or summary
            # details_text=data.get("description"), # REMOVED: Invalid field
            # conditions_text="\n".join(data.get("conditions", [])), # REMOVED: Invalid field
            conditions="\n".join(data.get("conditions", [])), # Correct field
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            reward_type=data.get("reward_type"),
            reward_value=data.get("reward_value"),
            reward_text=data.get("reward_text"),
            
            # AI Fields
            ai_marketing_text=data.get("description"), # Use description as AI summary
            eligible_cards=", ".join(target_cards),
            category=data.get("category"),
            badge_color=data.get("badge_color"),
            card_logo_url=data.get("card_logo_url"),

            # full_text=f"{data.get('title')} {data.get('description')}", # REMOVED: Invalid field
            
            clean_text=data.get('_clean_text') if data else None,
            tracking_url=url,
            image_url=image_url if image_url else "https://www.paraf.com.tr/content/dam/parafcard/paraf-logos/paraf-logo-yeni.png",
            is_active=True
        )
        
        self.db.add(campaign)  # type: ignore # pyre-ignore[16]
        self.db.commit()  # type: ignore # pyre-ignore[16]
        
        # Link Brands
        for bid in brand_ids:
            try:
                cb = CampaignBrand(campaign_id=campaign.id, brand_id=bid)  # type: ignore # pyre-ignore[16]
                self.db.add(cb)  # type: ignore # pyre-ignore[16]
            except: pass
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
            self.sector_cache[s.name.lower()] = s
            
        for b in self.db.query(Brand).all():  # type: ignore # pyre-ignore[16]
            self.brand_cache[b.name.lower()] = b

    def _get_or_create_card(self, name: str) -> Card:
        """Get or create card, but only for known Paraf variants."""
        name_lower = name.lower()
        
        # Mapping to prevent AI from creating variants
        if "fly" in name_lower:
            name = "Parafly"
        elif "troy" in name_lower:
            name = "Paraf TROY"
        else:
            name = "Paraf"
            
        key = name.lower()
        if key in self.card_cache:
            return self.card_cache[key]  # type: ignore # pyre-ignore[7]
        
        # Check DB
        card = self.db.query(Card).filter(  # type: ignore # pyre-ignore[16]
            Card.bank_id == self.bank_cache.id,  # type: ignore # pyre-ignore[16]
            Card.name == name
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

    def _get_sector(self, name: Optional[str]) -> Optional[Sector]:  # type: ignore # pyre-ignore[16,6]
        if not name: return None
        # Try exact match
        if name.lower() in self.sector_cache:
            return self.sector_cache[name.lower()]  # type: ignore # pyre-ignore[7]
        return self.sector_cache.get("diğer")  # type: ignore # pyre-ignore[7]

    def _get_or_create_brands(self, names: List[str], sector_id: Optional[int]) -> List[int]:  # type: ignore # pyre-ignore[16,6]
        return get_or_create_brands_list(self.db, names, getattr(self, 'brand_cache', {}), sector_id)

if __name__ == "__main__":
    try:
        scraper = ParafScraper(max_campaigns=5)
        scraper.run()
    except Exception as e:
        import traceback  # type: ignore # pyre-ignore[21]
        traceback.print_exc()
        print(f"CRITICAL ERROR: {e}")
