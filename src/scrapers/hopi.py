import sys
import os

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
from bs4 import BeautifulSoup
import asyncio
from playwright.sync_api import sync_playwright, Page

from src.database import get_db_session
from src.models import Bank, Card, Sector, Campaign, CampaignBrand
from src.services.ai_parser import parse_api_campaign
from src.utils.logger_utils import log_scraper_execution
from src.services.brand_normalizer import cleanup_brands
from src.services.brand_matcher import get_or_create_brands_list
from src.utils.slug_generator import get_unique_slug
from src.utils.cache_manager import clear_cache
from src.utils.scraper_utils import is_url_blocked, upsert_campaign


def format_turkish_title(title: str) -> str:
    """Format title to Turkish Title Case while respecting conjunctions and acronyms."""
    if not title:
        return title

    conjunctions = {"ve", "veya", "de", "da", "ile", "ki", "mi", "mı", "mu", "mü", "ama", "fakat"}

    def cap_word(word: str) -> str:
        if not word:
            return word

        parts = word.split("'")
        if len(parts) > 1:
            base = parts[0]
            suffix = "'".join(parts[1:])
            if base.upper() in ["TL", "PPF", "SUV", "QR", "SMS", "GSM", "AW", "CMS", "U.S.", "US"]:
                return base.upper() + "'" + suffix.lower()

        if word.upper() in ["TL", "PPF", "SUV", "QR", "SMS", "GSM", "AW", "CMS", "U.S.", "US"]:
            return word.upper()

        char0 = word[0]
        if char0 == "i":
            c0 = "İ"
        elif char0 == "ı":
            c0 = "I"
        else:
            c0 = char0.upper()

        rest = ""
        for ch in word[1:]:
            if ch == "İ":
                rest += "i"
            elif ch == "I":
                rest += "ı"
            else:
                rest += ch.lower()
        return c0 + rest

    words = title.strip().split()
    res = []
    for i, w in enumerate(words):
        w_clean = w.replace("İ", "i").replace("I", "ı").lower()
        if i > 0 and w_clean in conjunctions:
            res.append(w_clean)
        else:
            res.append(cap_word(w))
    return " ".join(res)


class HopiScraper:
    """
    Scraper for Hopi campaigns and Paracık deals.
    """

    BASE_URL = "https://hopi.com.tr"
    LISTING_URL = "https://hopi.com.tr/kampanyalar"
    BANK_NAME = "Hopi"
    CARD_NAME = "Hopi"
    CARD_SLUG = "hopi"

    def __init__(self):
        self.bank_id = None
        self.card_id = None

        with get_db_session() as db:
            bank = db.query(Bank).filter((Bank.slug == "hopi") | (Bank.name.ilike("%hopi%"))).first()
            if not bank:
                print(f"   🏦 Creating Bank: {self.BANK_NAME}")
                bank = Bank(name=self.BANK_NAME, slug="hopi", logo_url="/logos/banks/hopii.webp", is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
            else:
                bank.logo_url = "/logos/banks/hopii.webp"  # type: ignore
                db.commit()
            self.bank_id = bank.id

            card = db.query(Card).filter(Card.bank_id == bank.id, Card.slug == self.CARD_SLUG).first()
            if not card:
                print(f"   💳 Creating Card: {self.CARD_NAME}")
                card = Card(
                    bank_id=bank.id,
                    name=self.CARD_NAME,
                    slug=self.CARD_SLUG,
                    card_type="wallet",
                    logo_url="/logos/cards/hopii.webp",
                    image_url="/logos/creditcard/hopikart.webp",
                    credit_logo_url="/logos/creditcard/hopikart.webp",
                    is_active=True
                )
                db.add(card)
                db.commit()
                db.refresh(card)
            else:
                card.logo_url = "/logos/cards/hopii.webp"  # type: ignore
                card.image_url = "/logos/creditcard/hopikart.webp"  # type: ignore
                card.credit_logo_url = "/logos/creditcard/hopikart.webp"  # type: ignore
                db.commit()
            self.card_id = card.id

    def fetch_campaign_links(self, page: Page) -> List[Dict[str, str]]:
        """Fetches all campaign links from all Hopi listing pages using Playwright.
        Automatically stops when an empty page is encountered — no hardcoded page limit.
        """
        campaigns = []
        seen_urls = set()
        page_num = 0

        try:
            while True:
                page_num += 1
                url = self.LISTING_URL if page_num == 1 else f"{self.LISTING_URL}?page={page_num}"
                print(f"🌐 Fetching page {page_num}: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(1500)  # Listing page — kısa bekleme yeterli

                links = page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[href]'))
                        .map(a => ({href: a.href, text: a.innerText.trim()}))
                        .filter(x => x.href.includes('/kampanya/') && !x.href.includes('/kampanyalar'))
                """)

                if not links:
                    print(f"   ⏹️  Page {page_num} is empty — all pages fetched.")
                    break

                page_new = 0
                for link in links:
                    full_url = link["href"].split("?")[0]
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        campaigns.append({"url": full_url, "raw_title": link["text"]})
                        page_new += 1

                print(f"   ✅ Page {page_num}: {page_new} new campaigns (total: {len(campaigns)})")

        except Exception as e:
            print(f"❌ Error fetching campaign links: {e}")

        print(f"📌 Found {len(campaigns)} unique Hopi campaign URLs across {page_num - 1} pages.")
        return campaigns
    def scrape_campaign_detail(self, page: Page, item: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Parses detail page of a Hopi campaign using Playwright (JS rendered)."""
        url = item["url"]

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Kampanya içeriği yüklenene kadar bekle (kör timeout yerine)
            try:
                page.wait_for_selector('h1, .campaign-detail, .kullanim-sartlari', timeout=4000)
            except Exception:
                page.wait_for_timeout(2000)  # Fallback

            # Extract title from h1
            title = page.evaluate("""
                () => {
                    const h1 = document.querySelector('h1');
                    return h1 ? h1.innerText.trim() : '';
                }
            """)
            if not title or len(title) < 5 or title.upper() in ["TREND ALARMI", ""]:
                title = item.get("raw_title", "")

            title = format_turkish_title(title)
            if not title:
                return None

            # Extract main campaign image from .item div (JS rendered slider)
            # Dikey rehber (guide) görsellerini ekarte etmek için w >= h kontrolü eklendi (logo veya yatay kampanya görseli aranıyor)
            image_url = page.evaluate("""
                () => {
                    const isUglyGuide = (img) => {
                        const alt = (img.alt || '').toLowerCase();
                        return alt.includes('çerez') || alt.includes('aksi durumda') || alt.includes('tıkla kazan butonuyla') || alt.includes('yönlendikten sonra');
                    };

                    const itemImgs = document.querySelectorAll('.item img.img-fluid');
                    for (const img of itemImgs) {
                        const src = img.src || '';
                        if (src.includes('img-hopi.mncdn.com') && !src.includes('web-assets') && !src.includes('hopi-logo') && !isUglyGuide(img)) {
                            return src;
                        }
                    }
                    const allImgs = document.querySelectorAll('img');
                    for (const img of allImgs) {
                        const src = img.src || '';
                        const w = img.naturalWidth || img.width || 0;
                        if (src.includes('img-hopi.mncdn.com') && !src.includes('web-assets') && !src.includes('Logosu') && w > 200 && !isUglyGuide(img)) {
                            return src;
                        }
                    }
                    return null;
                }
            """)

            # Extract FULL page text via body.innerText (captures all rendered content)
            # Then strip nav/footer noise
            full_text = page.evaluate("""
                () => {
                    // Sadece kampanya detaylarını al, footer/header gürültülerinden kaçın
                    const container = document.querySelector('.campaign-detail');
                    const textContent = container ? container.innerText.trim() : document.body.innerText.trim();
                    
                    let actionBtn = "Kampanyadan Faydalan"; // fallback
                    const btns = Array.from(document.querySelectorAll('a, button'));
                    for (let b of btns) {
                        const text = b.innerText.trim();
                        if (text === "HOPİ'Nİ KULLAN" || text === "TEKLİF KODUNU AL" || text === "KAMPANYADAN FAYDALAN") {
                            actionBtn = text;
                            break;
                        }
                    }
                    
                    return `[Hopi Aksiyon Butonu: ${actionBtn}]\n\n` + textContent;
                }
            """)

            if not full_text:
                full_text = title

            return {
                "title": title,
                "url": url,
                "image_url": image_url,
                "content": full_text,
                "raw_text": f"{title}\n{full_text}"
            }
        except Exception as e:
            print(f"⚠️ Detail scrape error for {url}: {e}")
            return None

    def scrape(self, limit: int = 5) -> int:
        """Main execution loop for HopiScraper using Playwright for JS-rendered pages."""
        print(f"\n🚀 Starting {self.BANK_NAME} Scraper...")
        start_time = datetime.now()
        added_count = 0
        updated_count = 0

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            campaign_items = self.fetch_campaign_links(page)

            if not campaign_items:
                print("⚠️ No campaign items found.")
                browser.close()
                with get_db_session() as db_log:
                    log_scraper_execution(db=db_log, scraper_name="hopi", status="FAILED", total_found=0)
                return 0

            for idx, item in enumerate(campaign_items):
                if limit and idx >= limit:
                    break

                url = item["url"]

                # Her kampanya için ayrı DB session — uzun çalışmalarda timeout önler
                try:
                    with get_db_session() as db:
                        if is_url_blocked(db, url):
                            print(f"   ⏩ Blocked URL skipped: {url}")
                            continue

                        detail = self.scrape_campaign_detail(page, item)
                        if not detail or not detail.get("title"):
                            continue

                        # Run AI parser
                        parsed_data = parse_api_campaign(
                            title=detail["title"],
                            short_description=detail["content"][:200],
                            content_html=detail["content"],
                            bank_name=self.BANK_NAME,
                            tracking_url=url
                        )

                        if not parsed_data or not parsed_data.get("title"):
                            parsed_data = {
                                "title": detail["title"],
                                "description": detail["content"][:1000],
                                "details": detail["content"],
                                "start_date": None,
                                "end_date": None,
                                "sector": "Diğer",
                                "brands": [],
                                "image_url": detail.get("image_url")
                            }

                        # Resolve sector — AI returns slug (e.g. "turizm-konaklama"), search slug first
                        sector_name = (parsed_data.get("sector") or "diger").lower().strip()
                        sector = (
                            db.query(Sector).filter(Sector.slug.ilike(f"%{sector_name}%")).first()
                            or db.query(Sector).filter(Sector.name.ilike(f"%{sector_name}%")).first()
                        )
                        sector_id = sector.id if sector else None
                        if sector:
                            print(f"   🏷️  Sector: {sector.name} (from '{sector_name}')")
                        else:
                            print(f"   ⚠️  Sector not found for: '{sector_name}'")

                        formatted_title = format_turkish_title(parsed_data.get("title") or detail["title"])
                        slug = get_unique_slug(formatted_title, db, Campaign)
                        image_url = detail.get("image_url") or parsed_data.get("image_url") or "/logos/cards/hopii.webp"

                        end_date = parsed_data.get("end_date")
                        if not end_date:
                            end_date = datetime(datetime.now().year, 12, 31).date()

                        start_date = parsed_data.get("start_date") or datetime.now().date()

                        conditions = parsed_data.get("conditions")
                        if isinstance(conditions, list):
                            conditions = "\n".join(conditions)
                        elif not conditions:
                            conditions = detail["content"]

                        participation = parsed_data.get("participation") or "Hopi uygulaması üzerinden QR kodunu tanıtarak veya kampanya kodunu ibraz ederek yararlanabilirsiniz."
                        eligible_cards = parsed_data.get("eligible_cards") or "Hopi App"

                        # Katılım şeklindeki metin kampanya koşullarında tekrar etmesin
                        if conditions and participation:
                            participation_lines = {l.strip().lower() for l in participation.splitlines() if len(l.strip()) > 20}
                            cleaned_conditions = []
                            for line in conditions.splitlines():
                                stripped = line.strip()
                                if any(stripped.lower() in pl or pl in stripped.lower() for pl in participation_lines if pl):
                                    continue
                                cleaned_conditions.append(line)
                            conditions = "\n".join(cleaned_conditions).strip() or conditions

                        campaign_obj = Campaign(
                            card_id=self.card_id,
                            sector_id=sector_id,
                            title=formatted_title,
                            slug=slug,
                            description=parsed_data.get("description") or detail["content"][:500],
                            conditions=conditions,
                            reward_text=parsed_data.get("reward_text") or "Hopi Paracık Ayrıcalığı",
                            reward_value=parsed_data.get("reward_value"),
                            reward_type=parsed_data.get("reward_type"),
                            start_date=start_date,
                            end_date=end_date,
                            image_url=image_url,
                            tracking_url=url,
                            is_active=True,
                            is_approved=True,
                            participation=participation,
                            eligible_cards=eligible_cards,
                            ai_marketing_text=parsed_data.get("ai_marketing_text"),
                            clean_text=parsed_data.get("_clean_text")
                        )

                        campaign, op_status = upsert_campaign(db, campaign_obj)
                        db.commit()

                        if op_status == "saved":
                            added_count += 1
                            print(f"   ✨ Saved: {campaign.title}")
                        else:
                            updated_count += 1
                            print(f"   🔄 Updated/Revived: {campaign.title}")

                        # --- Brand linking ---
                        brand_names = parsed_data.get("brands") or []
                        if brand_names:
                            db.refresh(campaign)
                            clean_brands = cleanup_brands(brand_names)
                            brand_ids = get_or_create_brands_list(
                                db_session=db,
                                brand_names=clean_brands,
                                brand_cache={},
                                sector_id=sector_id
                            )
                            for bid in brand_ids:
                                try:
                                    link = db.query(CampaignBrand).filter(
                                        CampaignBrand.campaign_id == campaign.id,
                                        CampaignBrand.brand_id == bid
                                    ).first()
                                    if not link:
                                        db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                                        db.commit()
                                        print(f"      🏷️  Brand linked: {bid}")
                                except Exception as be:
                                    db.rollback()
                                    print(f"      ⚠️  CampaignBrand link failed: {be}")

                except Exception as camp_err:
                    print(f"   ❌ Campaign failed [{url}]: {camp_err}")

                time.sleep(0.3)

            browser.close()

        status = "SUCCESS" if (added_count + updated_count) > 0 else "PARTIAL"
        with get_db_session() as db_log:
            log_scraper_execution(
                db=db_log,
                scraper_name="hopi",
                status=status,
                total_found=len(campaign_items),
                total_saved=added_count,
                total_revived=updated_count,
            )
        print(f"✅ {self.BANK_NAME} Scraper Finished! Added: {added_count}, Updated: {updated_count}\n")
        return added_count + updated_count


if __name__ == "__main__":
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0  # 0 = no limit = all campaigns
    scraper = HopiScraper()
    scraper.scrape(limit=limit)
