import sys
import os
import time
import traceback
import requests
from typing import Dict, Optional, List, Any
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from src.models import Bank, Card, Sector, Campaign, CampaignBrand
from src.utils.scraper_utils import is_url_blocked, upsert_campaign, should_skip_campaign
from src.services.brand_matcher import get_or_create_brands_list
from src.services.ai_parser import parse_api_campaign
from src.utils.slug_generator import get_unique_slug
from src.utils.logger_utils import log_scraper_execution

# PostgreSQL fix for modern SQLAlchemy
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    os.environ["DATABASE_URL"] = DATABASE_URL

class TkpayScraper:
    BASE_URL = "https://tkpay.com/tr/all-campaigns"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        self.db = get_db_session()
        
        self.sector_cache: Dict[str, Sector] = {}
        self._load_cache()
        
        self.bank = self.db.query(Bank).filter(Bank.slug == 'tkpay').first()
        if not self.bank:
            self.bank = Bank(name='Tkpay', slug='tkpay', logo_url='/logos/tkpay.png', is_active=True)
            self.db.add(self.bank)
            self.db.commit()
            
        self.card = self.db.query(Card).filter(Card.slug == 'tkpay-cuzdan').first()
        if not self.card:
             self.card = Card(bank_id=self.bank.id, name='Tkpay Cüzdan', slug='tkpay-cuzdan', is_active=True, card_type='debit')
             self.db.add(self.card)
             self.db.commit()
        
        self.card_id = self.card.id

        # Check if direct connection works, fallback to TR proxy if needed
        self.proxy = None
        print("   🔍 Checking direct connection to tkpay.com...")
        try:
            r = requests.get(self.BASE_URL, timeout=4, headers=self.session.headers)
            if r.status_code == 200:
                print("   🌐 Direct connection to tkpay.com is successful. No proxy needed.")
            else:
                self.proxy = self._find_working_tr_proxy()
        except Exception:
            self.proxy = self._find_working_tr_proxy()

        if self.proxy:
            self.session.proxies = {
                "http": self.proxy,
                "https": self.proxy
            }

    def _find_working_tr_proxy(self) -> Optional[str]:
        print("   🔍 Direct connection to tkpay.com failed or timed out. Fetching free Turkey proxy list...")
        try:
            url = "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text&country=tr"
            resp = requests.get(url, timeout=10)
            proxies = [p.strip() for p in resp.text.split('\n') if p.strip()]
            print(f"   📋 Found {len(proxies)} Turkey proxies to test.")
            for proxy in proxies[:15]:
                try:
                    proxies_dict = {'http': proxy, 'https': proxy}
                    test_resp = requests.get(self.BASE_URL, proxies=proxies_dict, timeout=5, headers=self.session.headers)
                    if test_resp.status_code == 200:
                        print(f"   ✅ Found working TR proxy: {proxy}")
                        return proxy
                except Exception:
                    pass
        except Exception as e:
            print(f"   ⚠️ Failed to get/test Turkey proxies: {e}")
        return None

    def _load_cache(self):
        for s in self.db.query(Sector).all():
            self.sector_cache[s.slug] = s
            self.sector_cache[s.name.lower()] = s

    def _get_sector(self, slug: str) -> Optional[Sector]:
        if not slug:
            return self.sector_cache.get("diger")
        return self.sector_cache.get(slug.lower()) or self.sector_cache.get("diger")

    def _fetch_campaign_list(self) -> List[Dict[str, str]]:
        print(f"📄 Fetching Tkpay campaigns using Playwright for dynamic rendering...")
        campaigns = []
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                launch_args: Dict[str, Any] = {
                    "headless": True,
                    "channel": "chrome",
                    "args": ["--no-sandbox", "--disable-setuid-sandbox"]
                }
                if self.proxy:
                    launch_args["proxy"] = {"server": self.proxy}
                browser = p.chromium.launch(**launch_args)
                page = browser.new_page(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                page.goto(self.BASE_URL, timeout=45000, wait_until="domcontentloaded")
                
                # Wait for React to render the campaigns
                time.sleep(5)
                
                print("   🔄 Scrolling and loading all campaigns...")
                # Scroll to trigger lazy loading and click Load More button if any
                for _ in range(15):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)
                    try:
                        btns = page.query_selector_all("button")
                        for btn in btns:
                            text = btn.inner_text()
                            if text and 'Daha' in text:
                                btn.click()
                                time.sleep(1.5)
                    except Exception:
                        pass
                
                time.sleep(2)
                
                links = page.query_selector_all("a")
                seen = set()
                for link in links:
                    href = link.get_attribute("href")
                    if href:
                        href = href.strip()
                    if href and ('kampanya' in href.lower() or 'campaign' in href.lower()) and href != "/tr/all-campaigns":
                        full_url = urljoin("https://tkpay.com", href)
                        if full_url not in seen:
                            seen.add(full_url)
                            
                            # Try to get the image from the card container (sibling img of overlay link)
                            img_url = None
                            try:
                                card_container = link.evaluate_handle("el => el.closest('.relative') || el.parentElement")
                                if card_container:
                                    img = card_container.as_element().query_selector("img")
                                    if img:
                                        img_url = img.get_attribute("src")
                            except Exception:
                                pass
                                
                            if not img_url:
                                # Fallback to standard check
                                try:
                                    img = link.query_selector("img")
                                    img_url = img.get_attribute("src") if img else None
                                except Exception:
                                    pass

                            if img_url:
                                img_url = urljoin("https://tkpay.com", img_url)
                                
                            campaigns.append({
                                'url': full_url,
                                'img_url': img_url
                            })
                
                browser.close()
                print(f"   ✅ Total found via Playwright: {len(campaigns)} items.")
        except Exception as e:
            print(f"   ⚠️ Playwright failed, falling back to Requests: {e}")
            try:
                response = self.session.get(self.BASE_URL, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                links = soup.find_all('a')
                
                seen = set()
                for a in links:
                    href = a.get('href', '')
                    if href:
                        href = href.strip()
                    if href and ('kampanya' in href.lower() or 'campaign' in href.lower()) and href != "/tr/all-campaigns" and len(href) > 5:
                        full_url = urljoin("https://tkpay.com", href)
                        
                        img_url = None
                        # Try to find img in the card container
                        card_div = a.find_parent('div', class_=lambda c: c and 'relative' in c)
                        if card_div:
                            img = card_div.find('img')
                            if img:
                                img_url = img.get('src')
                        if not img_url:
                            img = a.find('img')
                            img_url = img.get('src') if img else None
                            
                        if img_url:
                            img_url = urljoin("https://tkpay.com", img_url)
                        
                        if full_url not in seen:
                            seen.add(full_url)
                            campaigns.append({
                                'url': full_url,
                                'img_url': img_url
                            })
                            
                print(f"   ✅ Total found via fallback: {len(campaigns)} items.")
            except Exception as e2:
                print(f"   ⚠️ Error fetching list: {e2}")
        return campaigns

    def _process_campaign(self, campaign_data, force: bool = False):
        import codecs
        import re
        import json

        url = campaign_data['url'].strip()
        list_img_url = campaign_data.get('img_url')

        print(f"🔍 Processing (AI Enabled): {url}")
        
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                print(f"   ⚠️ Page returned status code {response.status_code}. Skipping.")
                return "error"
                
            html_content = response.content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            h1 = soup.find('h1')
            title = h1.text.strip() if h1 else "Kampanya"

            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content") if og_title_el else None
            
            main = soup.find('main')
            if not main:
                main = soup.body

            content_blocks = []
            if main:
                for element in main.find_all(['p', 'li']):
                    text = element.text.strip()
                    if len(text) > 15:
                        content_blocks.append(text)
                        
            raw_html = "\n".join(content_blocks)
            
            detail_img = None
            for img in soup.select('img'):
                src = img.get('src', '')
                if '/api/image/' in src or any(x in src.lower() for x in ['kampanya', 'banner', 'upload', 'campaign']):
                    detail_img = urljoin("https://tkpay.com", src)
                    break

            # --- NEXT.JS RSC PAYLOAD EXTRACTION ---
            json_img = None
            json_end_date = None
            
            pushes = re.findall(b'self\\.__next_f\\.push\\(\\[\\s*\\d+\\s*,\\s*"(.*?)"\\s*\\]\\)', html_content)
            if not pushes:
                pushes = re.findall(b"self\\.__next_f\\.push\\(\\[\\s*\\d+\\s*,\\s*'(.*?)'\\s*\\]\\)", html_content)

            full_payload_bytes = b""
            for push in pushes:
                try:
                    decoded_bytes, _ = codecs.escape_decode(push)
                    full_payload_bytes += decoded_bytes
                except Exception:
                    pass

            full_payload = full_payload_bytes.decode('utf-8', errors='ignore')

            query_match = re.search(r'"queries"\s*:\s*(\[.*?\])\s*\}', full_payload)
            rsc_campaign_data = None
            if query_match:
                try:
                    queries_json = json.loads(query_match.group(1))
                    for query in queries_json:
                        if "state" in query and "data" in query["state"]:
                            rsc_campaign_data = query["state"]["data"]
                            break
                except Exception:
                    pass

            if rsc_campaign_data:
                # 1. Parse slots
                slots = {}
                current_id = None
                for line in full_payload.split('\n'):
                    match = re.match(r'^(\d+):(.*)', line)
                    if match:
                        current_id = match.group(1)
                        slots[current_id] = match.group(2)
                    elif current_id is not None:
                        slots[current_id] += '\n' + line

                # 2. Clean slot prefixes, slice to length, unescape and truncate if HTML
                clean_slots = {}
                for k, v in slots.items():
                    match_prefix = re.match(r'^T([0-9a-fA-F]+),(.*)', v, re.DOTALL)
                    if match_prefix:
                        length_hex = match_prefix.group(1)
                        length = int(length_hex, 16)
                        content = match_prefix.group(2)
                        
                        # Slice raw escaped string first
                        sliced = content[:length]
                        
                        # Unescape unicode sequences
                        def unescape_unicode(m):
                            try:
                                return chr(int(m.group(1), 16))
                            except Exception:
                                return m.group(0)
                        
                        decoded = re.sub(r'\\u([0-9a-fA-F]{4})', unescape_unicode, sliced)
                        
                        # Truncate at closing HTML tags if any (Next.js stream boundary protection)
                        for tag in ['</p>', '</ul>', '</div>', '</td>', '</span>', '</ol>']:
                            idx = decoded.rfind(tag)
                            if idx != -1:
                                decoded = decoded[:idx + len(tag)]
                                break
                        clean_slots[k] = decoded
                    else:
                        clean_slots[k] = v

                # 3. Resolve function
                def resolve_all(val, clean_slots):
                    if isinstance(val, str):
                        if val.startswith("$") and val[1:].isdigit():
                            ref_id = val[1:]
                            if ref_id in clean_slots:
                                return resolve_all(clean_slots[ref_id], clean_slots)
                        return val
                    elif isinstance(val, dict):
                        return {k: resolve_all(v, clean_slots) for k, v in val.items()}
                    elif isinstance(val, list):
                        return [resolve_all(v, clean_slots) for v in val]
                    return val

                rsc_campaign_data = resolve_all(rsc_campaign_data, clean_slots)

                title = rsc_campaign_data.get("name", title)
                desc = rsc_campaign_data.get("description", "")
                
                # Clean rules HTML
                rules_html = rsc_campaign_data.get("rules", "")
                rules_cleaned = re.sub(r'<br\s*/?>', '\n', rules_html)
                rules_cleaned = re.sub(r'</?(?:p|ul|li|div|span|strong|em)\s*>', '', rules_cleaned)
                rules_cleaned = re.sub(r'\s*\n\s*', '\n', rules_cleaned).strip()
                raw_html = rules_cleaned
                
                json_end_date = rsc_campaign_data.get("endDate")
                json_img = rsc_campaign_data.get("webDetailImagePath") or rsc_campaign_data.get("sdkDetailImagePath")
                if json_img and not json_img.startswith("http"):
                    json_img = urljoin("https://tkpay.com", json_img)
            else:
                desc = title
                rules_html = ""

            final_image = json_img or list_img_url or detail_img

            ai_data = parse_api_campaign(
                title=title,
                short_description=desc,
                content_html=rules_html if rsc_campaign_data else raw_html,
                bank_name="Tkpay",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title,
                force=force
            )
            
            if not ai_data:
                print("   ❌ AI Parsing failed.")
                return "error"

            title = ai_data.get("title", title)
            desc = ai_data.get("description", desc)
            
            sector_slug = ai_data.get("sector")
            sector = self._get_sector(sector_slug)
            
            slug = get_unique_slug(
                title=title,
                db_session=self.db,
                campaign_model=Campaign,
                tracking_url=url,
                card_name="Tkpay Cüzdan",
                bank_name="Tkpay"
            )

            conds = ai_data.get("conditions", [])
            if isinstance(conds, list):
                conds = [str(c).strip() for c in conds if c]
            elif isinstance(conds, str):
                conds = [c.strip() for c in conds.split("\n") if c.strip()]
            
            part_method = ai_data.get("participation")
            final_conditions = "\n".join(conds) if conds else raw_html

            cards_raw = ai_data.get("cards", [])
            if isinstance(cards_raw, str):
                cards_raw = [c.strip() for c in cards_raw.split(",") if c.strip()]

            vf = None
            vu = None
            
            if json_end_date:
                try:
                    vu = datetime.strptime(json_end_date[:19], "%Y-%m-%dT%H:%M:%S")
                    if json_end_date.endswith("Z"):
                        vu = vu + timedelta(hours=3)
                except Exception as de:
                    print("Date parsing error:", de)
                    
            if ai_data.get("start_date"):
                try: vf = datetime.strptime(ai_data.get("start_date"), "%Y-%m-%d")
                except: pass
            if ai_data.get("end_date") and not vu:
                try: vu = datetime.strptime(ai_data.get("end_date"), "%Y-%m-%d")
                except: pass
            
            if not vf:
                vf = datetime.now(timezone.utc).replace(tzinfo=None)

            campaign = Campaign(
                card_id=self.card_id,
                sector_id=sector.id if sector else None,
                slug=slug,
                title=title,
                description=desc,
                ai_marketing_text=ai_data.get("ai_marketing_text"),
                reward_text=ai_data.get("reward_text"),
                reward_value=ai_data.get("reward_value"),
                reward_type=ai_data.get("reward_type"),
                conditions=final_conditions,
                eligible_cards=", ".join(cards_raw) if cards_raw else "Tkpay Cüzdan",
                participation=part_method,
                image_url=final_image,
                start_date=vf,
                end_date=vu,
                clean_text=ai_data.get("_clean_text"),
                is_active=True,
                tracking_url=url,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
            )
            
            campaign, op_status = upsert_campaign(self.db, campaign)
            self.db.commit()
            
            if op_status == "revived":
                print(f"   ♻️  Revived: {campaign.title}")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title}")
            
            self.db.refresh(campaign)

            brand_ids = get_or_create_brands_list(
                db_session=self.db,
                brand_names=ai_data.get("brands", []),
                brand_cache=getattr(self, 'brand_cache', {}),
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
            return op_status
            
        except Exception as e:
            print(f"   ❌ Error processing {url}: {e}")
            if self.db: self.db.rollback()
            traceback.print_exc()
            return "error"

    def run(self, limit: Optional[int] = None, force: bool = False):
        print("🚀 Starting Tkpay Scraper...")
        
        if os.getenv("TEST_MODE") == "1" and not limit:
            print("🧪 TEST_MODE active: Limiting to 1 campaign.")
            limit = 1
            
        campaigns = self._fetch_campaign_list()
        
        if limit:
            campaigns = campaigns[:limit]
        
        total_found = len(campaigns)
        success_count = 0
        total_revived = 0
        skipped_count = 0
        failed_count = 0
        error_details = []

        for i, camp in enumerate(campaigns):
            url = camp.get('url')
            if not url:
                continue
                
            print(f"[{i+1}/{total_found}] Processing: {url}")
            
            try:
                # Early check
                if not force and should_skip_campaign(self.db, url, card_id=self.card_id):
                    print(f"   ⏭️ Skipped (Already exists or blocked)")
                    skipped_count += 1
                    continue
                    
                # Force re-parse if campaign is passive
                current_force = force
                existing = self.db.query(Campaign).filter(Campaign.tracking_url == url, Campaign.card_id == self.card_id).first()
                if existing and not existing.is_active:
                    current_force = True
                    
                res = self._process_campaign(camp, force=current_force)
                if res in ["saved", "updated"]: success_count += 1
                elif res == "revived": total_revived += 1
                elif res == "skipped": skipped_count += 1
                else: 
                    failed_count += 1
                    error_details.append({"url": url, "error": f"Process returned {res}"})
            except Exception as e:
                failed_count += 1
                error_details.append({"url": url, "error": str(e)})
            
            time.sleep(1)
            
        print(f"✅ Özet: {total_found} bulundu, {success_count} eklendi, {total_revived} canlandı, {skipped_count} atlandı, {failed_count} hata aldı.")
        
        status = "SUCCESS"
        if failed_count > 0:
             status = "PARTIAL" if (success_count > 0 or skipped_count > 0) else "FAILED"
             
        try:
            log_scraper_execution(
                 db=self.db,
                 scraper_name="tkpay",
                 status=status,
                 total_found=total_found,
                 total_saved=success_count,
                 total_skipped=skipped_count,
                 total_failed=failed_count,
                 total_revived=total_revived,
                 error_details={"errors": error_details} if error_details else None
            )
        except Exception as le:
             print(f"⚠️ Could not save scraper log: {le}")
             
        print("🏁 Finished.")

if __name__ == "__main__":
    try:
        scraper = TkpayScraper()
        scraper.run()
    finally:
        if hasattr(scraper, 'db') and scraper.db:
            scraper.db.close()
