


import sys
import os
import time  # type: ignore # pyre-ignore[21]
import re  # type: ignore # pyre-ignore[21]
import uuid  # type: ignore # pyre-ignore[21]
import asyncio  # type: ignore # pyre-ignore[21]
import random  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from typing import Optional, Dict, Any, List, Tuple  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]

from playwright.async_api import async_playwright, Page  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import Session  # type: ignore # pyre-ignore[21]

# Path setup to ensure imports work correctly
project_root = "/Users/hipoglisemi/Desktop/kasaonu-scrp"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]
from src.services.ai_parser_golden import parse_api_campaign  # type: ignore # pyre-ignore[21]
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked, upsert_campaign  # type: ignore

class KuveytTurkScraper:
    """
    Kuveyt Türk Sağlam Kart campaign scraper - Modernized with Playwright
    Handles 'Load More' button and uses AI for parsing.
    """

    BASE_URL = "https://saglamkart.kuveytturk.com.tr"
    CAMPAIGNS_URL = "https://saglamkart.kuveytturk.com.tr/kampanyalar"
    BANK_NAME = "Kuveyt Türk"
    CARD_SLUG = "saglam-kart"

    def __init__(self, max_campaigns: int = 999, headless: bool = True):
        self.max_campaigns = max_campaigns
        self.headless = headless
        self.db: Any = None
        self.parser = AIParser()
        
        # Cache
        self.bank_cache: Optional[Bank] = None  # type: ignore # pyre-ignore[16,6]
        self.card_cache: Dict[str, Card] = {}  # type: ignore # pyre-ignore[16,6]
        self.sector_cache: Dict[str, Sector] = {}  # type: ignore # pyre-ignore[16,6]
        self.brand_cache: Dict[str, Brand] = {}  # type: ignore # pyre-ignore[16,6]

    def run(self, limit: Optional[int] = None):  # type: ignore # pyre-ignore[16,6]
        """Entry point for synchronous execution"""
        if limit: self.max_campaigns = limit
        asyncio.run(self._run_async())

    async def _run_async(self):
        """Main async execution flow"""
        print(f"🚀 Starting {self.BANK_NAME} Scraper...")
        start_time = time.time()
        stats = {'total': 0, 'new': 0, 'updated': 0, 'revived': 0, 'failed': 0, 'skipped': 0}
        
        try:
            self.db = get_db_session()
            self._load_cache()
            
            bank_id = getattr(self.bank_cache, "id", None)
            card_id = getattr(self._get_or_create_card("Sağlam Kart"), "id", None)
            
            async with async_playwright() as p:
                # Using Chromium (compatible with both local and CI environments)
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={'width': 1280, 'height': 800}
                )
                
                # 1. Get List
                page = await context.new_page()
                urls, expired_urls = await self._scrape_list(page)
                await page.close()  # type: ignore # pyre-ignore[16]
                
                # Disable expired
                self.disable_expired_campaigns(expired_urls)
                
                print(f"   Found {len(urls)} active campaigns.")
                
                # Limit
                if len(urls) > self.max_campaigns:
                    urls = urls[:self.max_campaigns]  # type: ignore # pyre-ignore[16,6]
                
                # 2. Process Details
                for i, url in enumerate(urls, 1):
                    print(f"\n[{i}/{len(urls)}] Processing: {url}")  # type: ignore # pyre-ignore[16,6]
                    stats['total'] += 1  # type: ignore # pyre-ignore[58]
                    try:
                        # Existing and Blocklist check

                        existing = self.db.query(Campaign).filter_by(tracking_url=url).first()  # type: ignore # pyre-ignore[16]
                        is_test_mode = os.environ.get('TEST_MODE') == '1'
                        
                        if existing and not is_test_mode:
                            if existing.updated_at and (datetime.utcnow() - existing.updated_at).days < 2:
                                print(f"   ⏭️  Skipping recently updated campaign.")
                                stats['skipped'] += 1  # type: ignore # pyre-ignore[58]
                                continue

                        if await self._scrape_single_detail(context, url, bank_id, card_id, stats):
                            pass
                        await asyncio.sleep(random.uniform(1, 2))
                    except Exception as e:
                        print(f"      ❌ Error processing {url}: {e}")
                        stats['failed'] += 1  # type: ignore # pyre-ignore[58]
                
                await browser.close()  # type: ignore # pyre-ignore[16]
                
            elapsed = time.time() - start_time
            print(f"\n🎉 {self.BANK_NAME} scraping completed in {elapsed:.1f}s")
            print(f"📊 Stats: {stats['total']} processed | {stats['new']} new | {stats['updated']} updated | {stats.get('skipped', 0)} skipped | {stats['failed']} failed")  # type: ignore # pyre-ignore[16,6]
            
            log_scraper_execution(
                db=self.db,
                scraper_name=f"{self.BANK_NAME} Scraper",
                status="COMPLETED",
                total_found=stats['total'],
                total_saved=stats['new'] + stats['updated'],
                total_failed=stats['failed'],
                total_skipped=stats.get('skipped', 0),
                total_revived=stats.get('revived', 0)
            )

        except Exception as e:
            print(f"❌ Fatal error in Kuveyt Turk scraper: {e}")
            import traceback  # type: ignore # pyre-ignore[21]
            traceback.print_exc()
        finally:
            if self.db:
                self.db.close()  # type: ignore # pyre-ignore[16]

    async def _scrape_list(self, page: Any) -> Tuple[List[str], List[str]]:  # type: ignore # pyre-ignore[16,6]
        """Handles 'Load More' button to get all campaigns"""
        print(f"   🌐 Loading campaigns list: {self.CAMPAIGNS_URL}")
        active_urls = set()
        expired_urls = set()
        
        try:
            await page.goto(self.CAMPAIGNS_URL, wait_until="networkidle", timeout=60000)
            
            # 1. Wait for regular items
            await page.wait_for_selector(".campaign-card, a[href*='/kampanyalar/']", timeout=30000)

            # Click "Daha Fazla Göster" loop - Exit when count stops increasing
            click_count = 0
            MAX_CLICKS = 30
            consecutive_no_growth = 0
            
            while click_count < MAX_CLICKS:
                try:
                    # Count current unique campaign URLs
                    current_count = await page.evaluate('''() => {
                        const links = Array.from(document.querySelectorAll("a[href*='/kampanyalar/']"));
                        const unique = new Set(links.map(a => a.href).filter(h => !h.includes('biten-kampanyalar') && h.includes('/kampanyalar/')));
                        return unique.size;
                    }''')
                    print(f"      📊 Current unique campaigns visible: {current_count}")
                    
                    button = page.locator(".show-more")
                    if await button.count() == 0 or not await button.is_visible():
                        print(f"      ✨ No more 'Daha Fazla Göster' button or it is hidden. Total clicks: {click_count}")
                        break
                    
                    # Scroll to button and click robustly
                    await button.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    
                    await page.evaluate('''() => {
                        const btn = document.querySelector('.show-more');
                        if (btn) {
                            btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            btn.click();
                        }
                    }''')
                    
                    click_count += 1 # type: ignore
                    print(f"      👇 Clicked 'Daha Fazla Göster' ({click_count})...")
                    
                    await asyncio.sleep(3) # Wait for content to load
                    
                    # Check if count grew
                    new_count = await page.evaluate('''() => {
                        const links = Array.from(document.querySelectorAll("a[href*='/kampanyalar/']"));
                        const unique = new Set(links.map(a => a.href).filter(h => !h.includes('biten-kampanyalar') && h.includes('/kampanyalar/')));
                        return unique.size;
                    }''')
                    
                    if new_count <= current_count:
                        consecutive_no_growth += 1 # type: ignore
                        print(f"      ⚠️ No new campaigns after click (attempt {consecutive_no_growth}/3)...")
                        if consecutive_no_growth >= 3:
                            print(f"      ✅ Pagination done (no growth for 3 consecutive clicks).")
                            break
                    else:
                        consecutive_no_growth = 0
                        
                except Exception as b_err:
                    print(f"      ⚠️ Pagination interaction issue: {b_err}")
                    break

            # Extract Links
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            
            # Robust extraction - filter duplicates early
            potential_urls = set()
            all_a = soup.find_all("a", href=True)
            for a in all_a:
                href = a.get("href", "")
                if "/kampanyalar/" in href and "/biten-kampanyalar" not in href:
                    full_url = urljoin(self.BASE_URL, href)
                    potential_urls.add(full_url)  # type: ignore # pyre-ignore[16]
            
            print(f"      🎯 Found {len(potential_urls)} unique campaign links.")
            
            for full_url in potential_urls:
                # Check for "expired" indicators in URL
                if any(x in full_url.lower() for x in ["/arsiv", "/gecmis"]):  # type: ignore # pyre-ignore[16,6]
                    expired_urls.add(full_url)  # type: ignore # pyre-ignore[16]
                    continue
                
                # For Kuveyt Turk, we consider them active unless in /biten-kampanyalar (already filtered)
                active_urls.add(full_url)
            
            return list(active_urls), list(expired_urls)
        except Exception as e:
            print(f"      ❌ List load failed: {e}")
            return [], []

        # Database Pre-check (Skip Logic)
        try:
            with get_db_session() as db:
                existing = db.query(Campaign).filter(Campaign.tracking_url == url).first()  # type: ignore # pyre-ignore[16]
                if existing and existing.is_active and existing.is_approved:
                    existing.last_seen_at = datetime.utcnow()
                    db.commit()
                    print(f"   ⏭️ Skipped (Already active & last_seen_at updated): {existing.title[:40]}")
                    stats["skipped"] = stats.get("skipped", 0) + 1
                    return True
        except Exception as e:
            print(f"   ⚠️ DB Pre-check error: {e}")
            # Continue to scrape if DB check fails for some reason


        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(1)
            
            html_content = await page.content()
            soup = BeautifulSoup(html_content, "html.parser")
            
            title_el = soup.select_one("h1, .campaign-title, .title h2, .subpage-header h1")
            title = self._clean(title_el.text) if title_el else "Başlık Yok"

            # Blocklist check
            if is_url_blocked(self.db, url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                stats['skipped'] += 1  # type: ignore # pyre-ignore[58]
                return True
            
            # Clean unwanted elements
            for unwanted in soup.select("header, nav, .nav-wrapper, .breadcrumb, footer, .subpage-header"):
                unwanted.decompose()

            content_row = soup.select_one("div.row.search-content")
            
            main_description = ""
            conditions_text = ""
            if content_row:
                text_col = content_row.select_one("div.col-md-6:nth-child(1)")
                if text_col:
                    list_items = text_col.select("ul.list > li")
                    if list_items:
                        main_description = self._clean(list_items[0].get_text())
                        conditions_text = "\n".join([f"- {self._clean(li.get_text())}" for li in list_items[1:]])  # type: ignore # pyre-ignore[16,6]
            
            if not main_description:
                content_div = soup.select_one(".search-content, .subpage-wrapper .container, .ck-content")
                if content_div:
                    main_description = self._clean(content_div.get_text())[:800]  # type: ignore # pyre-ignore[16,6]
            
            # Image
            image_url = None
            img_candidates = soup.select("img")
            for img in img_candidates:
                src = img.get("src") or img.get("data-src")
                if not src or src.startswith("data:"): continue
                lower_src = src.lower()
                if any(x in lower_src for x in ["campaign", "kampanya", "detail", ".vsf", "banner"]):  # type: ignore # pyre-ignore[16,6]
                    image_url = urljoin(self.BASE_URL, src)
                    break
            
            if not image_url and content_row:
                img_el = content_row.select_one("img")
                if img_el:
                    image_url = urljoin(self.BASE_URL, img_el.get("src") or img_el.get("data-src")) # type: ignore # pyre-ignore[16]

            print("   🤖 Parsing with AI...")
            # og:title for Header Sniper
            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content", "").strip() if og_title_el else title

            # Full body HTML → parse_api_campaign centralised pipeline
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else html_content

            parsed_data = parse_api_campaign(
                title=title,
                short_description=None,
                content_html=raw_html,
                bank_name=self.BANK_NAME,
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            ) or {}
            
            if not parsed_data:
                print("   ❌ AI Parse failed")
                stats['failed'] += 1  # type: ignore # pyre-ignore[58]
                return False  # type: ignore # pyre-ignore[7]
                
            raw_data = {
                "title": title,
                "image_url": image_url,
                "description": main_description,
                "raw_text": raw_html,
                "source_url": url,
                "date_text": conditions_text # Fallback for date extraction
            }
            
            status = self._save_campaign(bank_id, card_id, parsed_data, raw_data)
            if status in ["saved", "updated", "revived"]:
                if status == "saved": stats['new'] += 1  # type: ignore # pyre-ignore[58,16,6]
                elif status == "revived": stats['revived'] += 1
                else: stats['updated'] += 1  # type: ignore # pyre-ignore[58,16,6]
                return True  # type: ignore # pyre-ignore[7]
            else:
                stats['failed'] += 1 # type: ignore
                return False
        except Exception as e:
            print(f"      ❌ Detail error: {e}")
            return False
        finally:
            await page.close()
        return False

    def _save_campaign(self, bank_id: int, card_id: int, parsed_data: Dict[str, Any], raw_data: Dict[str, Any]):  # type: ignore # pyre-ignore[16,6]
        title = raw_data["title"]
        source_url = raw_data["source_url"]
        from src.utils.slug_generator import get_unique_slug
        slug = get_unique_slug(
            title=title,
            db_session=self.db,
            campaign_model=Campaign,
            tracking_url=source_url,
            card_name="Kuveyt Türk Kredi Kartı",
            bank_name="Kuveyt Türk"
        )
        campaign = Campaign(
            card_id=card_id,
            sector_id=self._get_sector_id(str(parsed_data.get("sector") or "diger")),
            slug=slug,
            title=title,
            description=parsed_data.get("description") or raw_data.get("description", ""),
            ai_marketing_text=parsed_data.get("ai_marketing_text"),
            reward_text=parsed_data.get("reward_text"),
            reward_value=parsed_data.get("reward_value"),
            reward_type=parsed_data.get("reward_type"),
            conditions="\n".join(parsed_data.get("conditions", [])) if isinstance(parsed_data.get("conditions"), list) else str(parsed_data.get("conditions") or ""),
            eligible_cards=", ".join(parsed_data.get("cards", []))[:255] if isinstance(parsed_data.get("cards"), list) else str(parsed_data.get("cards") or "")[:255],
            participation=parsed_data.get("participation"),
            image_url=raw_data.get("image_url") or parsed_data.get("image_url"),
            start_date=self._parse_date_string(parsed_data.get("start_date")) or datetime.now().date(),
            end_date=self._parse_date_string(parsed_data.get("end_date")),
            is_active=True,
            tracking_url=source_url,
            clean_text=raw_data.get("raw_text"),
            updated_at=datetime.utcnow()
        )

        try:
            # Use centralized upsert_campaign for revival and quality control
            campaign, op_status = upsert_campaign(self.db, campaign)
            self.db.commit()

            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title[:50]}...")
            elif op_status == "updated":
                 print(f"   ✅ Updated: {campaign.title[:50]}...")
            
            self.db.refresh(campaign)

            # Brands
            brands_list = parsed_data.get("brands", [])
            if isinstance(brands_list, list):
                self.db.query(CampaignBrand).filter_by(campaign_id=campaign.id).delete()  # type: ignore # pyre-ignore[16]
                added_brand_ids = set()
                for brand_name in brands_list:
                    if not brand_name: continue
                    brand_obj = self._get_or_create_brand(brand_name)
                    if brand_obj and brand_obj.id not in added_brand_ids:
                        added_brand_ids.add(brand_obj.id)
                        cb = CampaignBrand(campaign_id=campaign.id, brand_id=brand_obj.id)  # type: ignore # pyre-ignore[16]
                        self.db.merge(cb)
                    
            self.db.commit()  # type: ignore # pyre-ignore[16]
            return op_status
        except Exception as e:
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            print(f"      ❌ DB Error: {e}")
            return False, False  # type: ignore # pyre-ignore[7]

    # --- HELPERS ---
    def _load_cache(self):
        bank = self.db.query(Bank).filter(Bank.slug.in_(['kuveyt-turk', 'kuveytturk'])).first()  # type: ignore # pyre-ignore[16]
        if not bank:
            bank = Bank(name="Kuveyt Türk", slug="kuveyt-turk", is_active=True)
            self.db.add(bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
        self.bank_cache = bank
        
        for s in self.db.query(Sector).all():  # type: ignore # pyre-ignore[16]
            self.sector_cache[s.slug] = s

    def _get_or_create_card(self, name: str) -> Card:
        key = name.lower()
        if key in self.card_cache: return self.card_cache[key]  # type: ignore # pyre-ignore[16,6]
        card = self.db.query(Card).filter(Card.bank_id == self.bank_cache.id, Card.name == name).first()  # type: ignore # pyre-ignore[16]
        if not card:
            card = Card(bank_id=self.bank_cache.id, name=name, slug=self._generate_slug(name), is_active=True)  # type: ignore # pyre-ignore[16]
            self.db.add(card)  # type: ignore # pyre-ignore[16]
            self.db.flush()  # type: ignore # pyre-ignore[16]
        self.card_cache[key] = card
        return card  # type: ignore # pyre-ignore[7]

    def _get_or_create_brand(self, name: str) -> Brand: # type: ignore
        from src.services.brand_matcher import get_or_create_brand
        b = get_or_create_brand(self.db, name, self.brand_cache)
        if not b:
            raise ValueError(f"Invalid brand name: {name}")
        return b # type: ignore
    def _get_sector_id(self, slug: str) -> Optional[int]:  # type: ignore # pyre-ignore[16,6]
        if slug in self.sector_cache: return self.sector_cache[slug].id  # type: ignore # pyre-ignore[16,6]
        return self.sector_cache.get("diger", {}).get("id")  # type: ignore # pyre-ignore[7]

    def _parse_date_string(self, date_str: Optional[str]) -> Optional[Any]:  # type: ignore # pyre-ignore[16,6]
        if not date_str or date_str == "None": return None
        try:
            return datetime.strptime(date_str.split('T')[0], "%Y-%m-%d").date()  # type: ignore # pyre-ignore[7]
        except: return None

    def _clean(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text.replace('\xa0', ' ')).strip()  # type: ignore # pyre-ignore[7]

    def _generate_slug(self, title: str) -> str:
        slug = str(title).lower().replace('ı', 'i').replace('ğ', 'g').replace('ü', 'u').replace('ş', 's').replace('ö', 'o').replace('ç', 'c')
        slug = re.sub(r'[^a-z0-9\s-]', '', slug)
        return re.sub(r'[\s-]+', '-', slug).strip('-')  # type: ignore # pyre-ignore[7]

    def disable_expired_campaigns(self, expired_urls: List[str]):  # type: ignore # pyre-ignore[16,6]
        if not expired_urls: return
        count = 0
        for url in expired_urls:
            camp = self.db.query(Campaign).filter_by(tracking_url=url, is_active=True).first()  # type: ignore # pyre-ignore[16]
            if camp:
                camp.is_active = False
                count += 1  # type: ignore # pyre-ignore[58]
        if count: self.db.commit()  # type: ignore # pyre-ignore[16]

if __name__ == "__main__":
    limit_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 999
    scraper = KuveytTurkScraper(headless=True)
    scraper.run(limit=limit_arg)
