"""
İş Bankası Genel Kampanyalar Scraper (Playwright tabanlı)
https://www.isbank.com.tr/kampanyalar
"""
import os
import sys
import time
import re
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.scraper_utils import is_url_blocked, upsert_campaign
from src.services.brand_matcher import get_or_create_brands_list

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_root, '.env'))
except Exception:
    pass
try:
    with open(os.path.join(project_root, '.env'), 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                k, v = line.strip().split('=', 1)
                if k not in os.environ:
                    os.environ[k] = v.strip('"\'')
except Exception:
    pass

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models import Bank, Card, Sector, CampaignBrand, Campaign

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


class IsbankasiScraper:
    BASE_URL = "https://www.isbank.com.tr"
    CAMPAIGNS_URL = "https://www.isbank.com.tr/kampanyalar"
    BANK_NAME = "İşbankası"
    CARD_NAME = "İşbankası"
    CARD_SLUG = "isbankasi"

    def __init__(self):
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL is not set")
        self.engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()
        
        try:
            from src.services.ai_parser import AIParser
            from src.services.ai_parser_golden import parse_api_campaign as _parse_api_campaign
            self.parser = AIParser()
            self.parse_api_campaign = _parse_api_campaign
        except ImportError as e:
            print(f"[DEBUG] AIParser import FAILED: {e}")
            raise

        self.card_id = None
        self.page = None
        self.browser = None
        self.playwright = None
        self._init_card()
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"
        })

    def _init_card(self):
        bank = self.db.query(Bank).filter(
            Bank.slug.in_(['isbankasi', 'isbank'])
        ).first()
        if not bank:
            bank = Bank(name='İşbankası', slug='isbankasi')
            self.db.add(bank)
            self.db.commit()
            
        card = self.db.query(Card).filter(
            Card.slug.in_([self.CARD_SLUG, 'isbankasi-kampanyalari', 'bankamatik'])
        ).first()
        if not card:
            card = Card(bank_id=bank.id, name=self.CARD_NAME, slug=self.CARD_SLUG, is_active=True)
            self.db.add(card)
            self.db.commit()
            
        if card:
            self.card_id = card.id
        else:
            self.card_id = None

    def _start_browser(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        is_ci = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"
        connected = False

        if not is_ci:
            try:
                if self.playwright:
                    self.browser = self.playwright.firefox.connect_over_cdp("http://localhost:9222")
                connected = True
                if self.browser and len(self.browser.contexts) > 0:
                    context = self.browser.contexts[0]
                elif self.browser:
                    context = self.browser.new_context()
                else:
                    context = None
                    
                if context:
                    self.page = context.new_page()
                
                if self.page:
                    self.page.set_default_timeout(120000)
                return
            except Exception:
                pass
                
        if not connected and self.playwright:
            self.browser = self.playwright.firefox.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            if self.browser:
                context = self.browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                self.page = context.new_page()
            if self.page:
                self.page.set_default_timeout(120000)

    def _stop_browser(self):
        try:
            if hasattr(self, 'browser') and self.browser:
                self.browser.close()
            if hasattr(self, 'playwright') and self.playwright:
                self.playwright.stop()
        except Exception:
            pass

    def _fetch_campaign_urls(self, limit: Optional[int] = None) -> tuple[List[str], List[str]]:
        all_links = []
        
        # Query target cards and active campaigns from database to filter duplicates
        db_slugs = set()
        db_titles = set()
        
        def normalize_text(text):
            if not text:
                return ""
            text = text.lower()
            replacements = {
                'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
                'â': 'a', 'î': 'i', 'û': 'u', 'i̇': 'i'
            }
            for k, v in replacements.items():
                text = text.replace(k, v)
            return re.sub(r'[^a-z0-9]', '', text)
            
        def extract_slug(url):
            if not url:
                return ""
            url = url.split('#')[0].split('?')[0].rstrip('/')
            return url.split('/')[-1]

        try:
            Session = sessionmaker(bind=self.engine)
            temp_db = Session()
            try:
                target_cards = temp_db.query(Card).filter(
                    Card.slug.in_(["maximum", "maximiles", "maximum-genc"])
                ).all()
                target_card_ids = [c.id for c in target_cards]
                
                if target_card_ids:
                    active_db_camps = temp_db.query(Campaign).filter(
                        Campaign.card_id.in_(target_card_ids),
                        Campaign.is_active == True
                    ).all()
                    
                    for camp in active_db_camps:
                        slug = extract_slug(camp.tracking_url)
                        norm_title = normalize_text(camp.title)
                        if slug:
                            db_slugs.add(slug)
                        if norm_title:
                            db_titles.add(norm_title)
                    print(f"Loaded {len(active_db_camps)} active campaigns from DB for duplicate filtering.")
            finally:
                temp_db.close()
        except Exception as dbe:
            print(f"   ⚠️ Could not load active campaigns from DB for filtering: {dbe}")
        
        urls_to_fetch = [
            self.CAMPAIGNS_URL,
            self.CAMPAIGNS_URL + "?v=ticari"
        ]
        
        if not hasattr(self, 'page') or not self.page:
            self._start_browser()
            
        if not hasattr(self, 'page') or not self.page:
            return [], []
        
        for fetch_url in urls_to_fetch:
            print(f"📥 Fetching campaign list from {fetch_url}...")
            try:
                for attempt in range(3):
                    try:
                        self.page.goto(fetch_url, wait_until="domcontentloaded", timeout=120000)
                        time.sleep(5)
                        break
                    except Exception as ge:
                        if attempt == 2:
                            raise ge
                        print(f"      ⚠️ Attempt {attempt+1} failed: {ge}. Retrying in 5 seconds...")
                        time.sleep(5)
                
                try:
                    btn = self.page.query_selector("text=Kabul Et")
                    if btn and btn.is_visible():
                        btn.click()
                        time.sleep(1)
                except:
                    pass

                # Load active campaigns only
                click_count_active = 0
                while click_count_active < 50:
                    btn = self.page.query_selector("#kamp_moreCamp1")
                    if btn and btn.is_visible():
                        self.page.evaluate("element => element.click()", btn)
                        click_count_active += 1
                        time.sleep(1.5)
                    else:
                        break
                print(f"   ⏬ Clicked active load button {click_count_active} times.")
                        
                soup = BeautifulSoup(self.page.content(), "html.parser")
                
                # Active campaigns are inside div.kamp_cards33C
                skipped_duplicates = 0
                for div in soup.find_all('div', class_='kamp_cards33C'):
                    a = div.find('a', href=True)
                    title_el = div.find('div', class_='kamp_card33Title')
                    if a and 'kampanyalar/' in a['href'] and title_el:
                        full_url = urljoin(self.BASE_URL, a['href'])
                        clean_url = full_url.split('#')[0]
                        
                        slug = extract_slug(clean_url)
                        norm_title = normalize_text(title_el.get_text(strip=True))
                        
                        # Filter out duplicates
                        if slug in db_slugs or norm_title in db_titles:
                            skipped_duplicates += 1
                            continue
                            
                        all_links.append(clean_url)
                print(f"   Filtered out {skipped_duplicates} duplicate Maximum/Maximiles/Genç campaigns.")
            except Exception as e:
                print(f"   ⚠️ Error fetching {fetch_url}: {e}")

        unique_urls = list(dict.fromkeys(all_links))
        
        if limit is not None:
            unique_urls = unique_urls[:limit]
            
        print(f"✅ Found {len(unique_urls)} active unique campaigns")
        return unique_urls, []

    def _extract_campaign_data(self, url: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self.session.get(url, verify=False, timeout=30)
            if resp.status_code != 200:
                print(f"      ❌ Bad status code: {resp.status_code}")
                return None
                
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Title
            title_el = soup.find('h1') or soup.select_one(".page-title")
            title = self._clean(title_el.text) if title_el else ""
            if not title:
                og_title = soup.find("meta", property="og:title")
                title = og_title.get("content").strip() if og_title else ""
            
            # Image
            image_url = None
            img_el = soup.select_one(".kmp_dtyimage") or soup.select_one(".campaign-detail-img img")
            if img_el:
                src = img_el.get("src") or img_el.get("data-src")
                if src:
                    image_url = urljoin(self.BASE_URL, src)
            
            if not image_url:
                og_img = soup.find("meta", property="og:image")
                if og_img and og_img.get("content"):
                    og_src = og_img.get("content").strip()
                    if "isbank-og-image" not in og_src:
                        image_url = urljoin(self.BASE_URL, og_src)
                        
            # Full HTML
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else soup.get_text()
            
            og_title_val = soup.find("meta", property="og:title")
            og_title = og_title_val.get("content").strip() if og_title_val else title
            
            ai_data = self.parse_api_campaign(
                title=title,
                short_description=None,
                content_html=raw_html,
                bank_name="İşbankası",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            )

            if not ai_data:
                return None

            ai_data["source_url"] = url
            ai_data["og_title"] = og_title
            ai_data["image_url"] = image_url
            ai_data["raw_title"] = title
            
            return ai_data
            
        except Exception as e:
            print(f"   ⚠️ Error extracting {url}: {e}")
            return None

    def _clean(self, text: str) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text.replace("\n", " ").replace("\r", "")).strip()

    def _to_title_case(self, text: Any) -> str:
        if not text: return ""
        text_str = str(text)
        replacements = {"I": "ı", "İ": "i"}
        lower_text = text_str
        for k, v in replacements.items(): lower_text = lower_text.replace(k, v)
        lower_text = lower_text.lower()
        words = lower_text.split()
        capitalized = []
        for word in words:
            if not word: continue
            if word[0] == 'i': capitalized.append('İ' + word[1:])
            elif word[0] == 'ı': capitalized.append('I' + word[1:])
            else: capitalized.append(word.capitalize())
        return " ".join(capitalized)

    def _process_campaign(self, url: str, force: bool = False) -> str:
        existing = self.db.query(Campaign).filter(
            Campaign.tracking_url == url, Campaign.card_id == self.card_id
        ).first()
        if existing and existing.is_active and not force:
            print(f"   ⏭️  Skipped (Already exists and active): {existing.title[:40]}")
            return "skipped"

        if is_url_blocked(self.db, url):
            print(f"   🚫 Skipped (Blocklisted): {url}")
            return "skipped"

        print(f"🔍 Processing: {url}")
        data = self._extract_campaign_data(url)
        if not data:
            print("   ⏭️  Skipped (AI Failed)")
            return "skipped"

        try:
            formatted_title = self._to_title_case(data["raw_title"])
            from src.utils.slug_generator import get_unique_slug
            slug = get_unique_slug(
                title=formatted_title,
                db_session=self.db,
                campaign_model=Campaign,
                tracking_url=url,
                card_name=self.CARD_NAME,
                bank_name=self.BANK_NAME
            )
            
            ai_cat = data.get("sector", "Diğer")
            sector = self.db.query(Sector).filter(Sector.slug == ai_cat).first()
            if not sector:
                sector = self.db.query(Sector).filter(Sector.slug == 'diger').first()

            start_date, end_date = None, None
            for ai_key in ["start_date", "end_date"]:
                val = data.get(ai_key)
                if val:
                    try:
                        dt = datetime.strptime(val, "%Y-%m-%d")
                        if ai_key == "start_date": start_date = dt
                        else: end_date = dt
                    except Exception:
                        pass

            conds = data.get("conditions", [])
            if isinstance(conds, str):
                conds = [c.strip() for c in conds.split("\n") if c.strip()]
                
            participation = data.get("participation")
            
            cards_raw = data.get("cards", [])
            if isinstance(cards_raw, str):
                cards_raw = [c.strip() for c in cards_raw.split(",") if c.strip()]
            else:
                cards_raw = [str(c) for c in cards_raw] if cards_raw else []
                
            if not cards_raw:
                cards_raw.append(self.CARD_NAME)

            campaign = Campaign(
                card_id=self.card_id, sector_id=sector.id if sector else None,
                slug=slug, title=formatted_title,
                description=data.get("description") or data["raw_title"][:200],
                ai_marketing_text=data.get("ai_marketing_text"),
                reward_text=data.get("reward_text"),
                reward_value=data.get("reward_value"),
                reward_type=data.get("reward_type"),
                conditions="\n".join(conds),
                eligible_cards=", ".join(cards_raw) or None,
                participation=participation,
                image_url=data.get("image_url"),
                start_date=start_date, end_date=end_date,
                is_active=True, tracking_url=url,
                created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
                clean_text=data.get('_clean_text') or data.get('clean_text')
            )
            
            campaign, op_status = upsert_campaign(self.db, campaign)
            self.db.commit()

            brand_ids = get_or_create_brands_list(
                db=self.db,
                names=data.get("brands", []),
                brand_cache={},
                sector_id=sector.id if sector else None
            )

            for bid in brand_ids:
                try:
                    link = self.db.query(CampaignBrand).filter(
                        CampaignBrand.campaign_id == campaign.id,
                        CampaignBrand.brand_id == bid
                    ).first()
                    if not link:
                        self.db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                        self.db.commit()
                except Exception as e:
                    self.db.rollback()
                    print(f"   ⚠️ CampaignBrand link failed: {e}")

            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
                return "revived"
            elif op_status in ("saved", "updated"):
                 print(f"   ✅ Saved/Updated: {campaign.title[:50]}...")
                 return "saved"
            
            return "saved"
            
        except Exception as e:
            self.db.rollback()
            print(f"   ❌ Save failed: {e}")
            return "error"

    def run(self, limit: Optional[int] = None, urls: Optional[List[str]] = None, force: bool = False):
        try:
            print(f"🚀 Starting {self.CARD_NAME} Scraper...")
            
            if self.db:
                self.db.commit()
                self.db.close()
                
            if urls:
                print(f"🎯 Running specific URLs: {len(urls)}")
                active_urls = urls
                expired_urls = []
            else:
                active_urls, expired_urls = self._fetch_campaign_urls(limit=limit)
            
            Session = sessionmaker(bind=self.engine)
            self.db = Session()
            
            if expired_urls:
                print(f"🛑 Found {len(expired_urls)} expired campaigns. Checking DB for early end...")
                for e_url in expired_urls:
                    try:
                        existing = self.db.query(Campaign).filter(
                            Campaign.tracking_url == e_url,
                            Campaign.card_id == self.card_id,
                            Campaign.is_active == True
                        ).first()
                        if existing:
                            print(f"   🛑 Deactivating expired campaign from DB: {existing.title}")
                            existing.is_active = False
                            self.db.commit()
                    except Exception as e:
                        self.db.rollback()
                        print(f"   ⚠️ Could not update expired campaign {e_url}: {e}")
                        
            urls = active_urls
            success, revived, skipped, failed = 0, 0, 0, 0
            
            for i, url in enumerate(urls, 1):
                print(f"\n[{i}/{len(urls)}]")
                try:
                    res = self._process_campaign(url, force=force)
                    if res == "saved": success += 1
                    elif res == "revived": revived += 1
                    elif res == "skipped": skipped += 1
                    else: failed += 1
                except Exception as e:
                    print(f"❌ Error: {e}")
                    failed += 1
                time.sleep(1)
                
            print(f"\n🏁 Finished. {len(urls)} found, {success} saved, {revived} revived, {skipped} skipped, {failed} errors")
            
            status = "SUCCESS"
            if failed > 0:
                 status = "PARTIAL" if (success > 0 or skipped > 0) else "FAILED"
                 
            try:
                from src.utils.logger_utils import log_scraper_execution
                log_scraper_execution(
                    db=self.db,
                    scraper_name=self.CARD_SLUG,
                    status=status,
                    total_found=len(urls),
                    total_saved=success,
                    total_skipped=skipped,
                    total_failed=failed,
                    total_revived=revived
                )
            except Exception as le:
                print(f"⚠️ Could not save scraper log: {le}")
                 
        except Exception as e:
            print(f"❌ Scraper error: {e}")
            try:
                from src.utils.logger_utils import log_scraper_execution
                log_scraper_execution(self.db, self.CARD_SLUG, "FAILED", 0, 0, 0, 1, 0, {"error": str(e)})
            except:
                pass
            raise
        finally:
            self._stop_browser()
            self.session.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of campaigns to scrape")
    parser.add_argument("--urls", type=str, default=None, help="Comma separated list of URLs to scrape")
    parser.add_argument("--force", action="store_true", help="Force update existing campaigns")
    args = parser.parse_args()
    
    url_list = None
    if args.urls:
        url_list = [u.strip() for u in args.urls.split(",") if u.strip()]
        
    scraper = IsbankasiScraper()
    scraper.run(limit=args.limit, urls=url_list, force=args.force)
