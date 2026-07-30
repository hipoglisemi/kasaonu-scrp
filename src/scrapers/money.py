import sys
import os

# Setup project root path for src.* imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import re
import time
import requests
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from src.database import get_db_session
from src.models import Bank, Card, Sector, Campaign, CampaignBrand, Brand
from src.services.ai_parser import AIParser
from src.utils.logger_utils import log_scraper_execution
from src.services.brand_normalizer import cleanup_brands
from src.utils.slug_generator import generate_slug, get_unique_slug
from src.utils.cache_manager import clear_cache
from src.utils.scraper_utils import is_url_blocked, upsert_campaign, update_dates_in_text


MONTHS = {
    'ocak': 1, 'şubat': 2, 'subat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'mayis': 5,
    'haziran': 6, 'temmuz': 7, 'agustos': 8, 'ağustos': 8, 'eylül': 9, 'eylul': 9,
    'ekim': 10, 'kasım': 11, 'kasim': 11, 'aralık': 12, 'aralik': 12
}


def parse_tr_date_range(text: str) -> Tuple[Optional[datetime.date], Optional[datetime.date]]:
    """Parse Turkish date strings like '1 Temmuz-31 Ağustos 2026' into start and end dates."""
    if not text:
        return None, None
    text_clean = text.lower().strip()

    # Pattern: 1 temmuz-31 ağustos 2026 or 1 temmuz - 31 ağustos 2026
    m = re.search(r'(\d{1,2})\s*([a-zğüşıöc]+)\s*[-–—]\s*(\d{1,2})\s*([a-zğüşıöc]+)\s*(\d{4})', text_clean)
    if m:
        d1, m1_str, d2, m2_str, yr = m.groups()
        m1 = MONTHS.get(m1_str)
        m2 = MONTHS.get(m2_str)
        if m1 and m2:
            try:
                s_date = datetime(int(yr), m1, int(d1)).date()
                e_date = datetime(int(yr), m2, int(d2)).date()
                return s_date, e_date
            except Exception:
                pass

    # Single date pattern or end date pattern (e.g. '31 Ağustos 2026')
    m_end = re.search(r'(\d{1,2})\s*([a-zğüşıöc]+)\s*(\d{4})', text_clean)
    if m_end:
        d, m_str, yr = m_end.groups()
        m_num = MONTHS.get(m_str)
        if m_num:
            try:
                e_date = datetime(int(yr), m_num, int(d)).date()
                return None, e_date
            except Exception:
                pass

    return None, None


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
        c0 = "İ" if char0 == "i" else ("I" if char0 == "ı" else char0.upper())

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


class MoneyScraper:
    """
    Scraper for Money Kart (Migros Money Marka Ayrıcalıkları) campaigns.
    """

    BASE_URL = "https://www.money.com.tr"
    LIST_URL = "https://www.money.com.tr/marka-ayricaliklari"
    BANK_NAME = "Money Kart"
    CARD_NAME = "Money Kart"
    CARD_SLUG = "money-kart"

    def __init__(self):
        self.bank_id = None
        self.card_id = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
        })

        with get_db_session() as db:
            bank = db.query(Bank).filter((Bank.slug == "money-kart") | (Bank.name.ilike("%money%"))).first()
            if not bank:
                print(f"   🏦 Creating Bank: {self.BANK_NAME}")
                bank = Bank(name=self.BANK_NAME, slug="money-kart", logo_url="/logos/banks/money-kart.webp", is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
            else:
                bank.logo_url = "/logos/banks/money-kart.webp"  # type: ignore
                db.commit()
            self.bank_id = bank.id

            card = db.query(Card).filter(Card.slug == self.CARD_SLUG, Card.bank_id == self.bank_id).first()
            if not card:
                print(f"   💳 Creating Card: {self.CARD_NAME}")
                card = Card(name=self.CARD_NAME, slug=self.CARD_SLUG, bank_id=self.bank_id, card_type="loyalty", is_active=True)
                db.add(card)
                db.commit()
                db.refresh(card)
            self.card_id = card.id

        self.ai_parser = AIParser()

    def _get_or_create_brand(self, db, brand_name: str) -> Optional[Brand]:
        """Fetch or create brand record in DB using current session."""
        if not brand_name or len(brand_name.strip()) < 2:
            return None
        name_clean = brand_name.strip()
        slug_clean = generate_slug(name_clean)

        brand = db.query(Brand).filter((Brand.name.ilike(name_clean)) | (Brand.slug == slug_clean)).first()
        if not brand:
            try:
                brand = Brand(name=name_clean, slug=slug_clean)
                db.add(brand)
                db.flush()
            except Exception:
                brand = db.query(Brand).filter((Brand.name.ilike(name_clean)) | (Brand.slug == slug_clean)).first()
        return brand

    def run(self, limit: Optional[int] = None, force: bool = False):
        start_time = time.time()
        print(f"🚀 Starting Money Scraper ({self.LIST_URL})...")

        try:
            resp = self.session.get(self.LIST_URL, timeout=15)
            if resp.status_code != 200:
                print(f"❌ Failed to fetch listing page: HTTP {resp.status_code}")
                return
            html = resp.text
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return

        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("#special-campaigns-list .item")
        print(f"✅ Found {len(items)} campaign cards on listing page.")

        campaigns_to_process = []
        seen_urls = set()

        for item in items:
            date_el = item.select_one(".date")
            date_str = date_el.text.strip() if date_el else ""

            link_el = item.select_one("a[href]")
            if not link_el:
                continue

            href = link_el["href"]
            if "#" in href or "javascript" in href:
                continue

            detail_url = urljoin(self.BASE_URL, href)
            if detail_url in seen_urls:
                continue
            seen_urls.add(detail_url)

            img_el = item.select_one("img")
            img_url = img_el["src"] if img_el and img_el.has_attr("src") else ""

            title_el = item.select_one(".bottom p")
            title = title_el.text.strip() if title_el else ""

            campaigns_to_process.append({
                "url": detail_url,
                "image_url": img_url,
                "title": title,
                "date_str": date_str
            })

        if limit:
            print(f"⚡ Capping process to {limit} campaigns.")
            campaigns_to_process = campaigns_to_process[:limit]

        total_found = len(campaigns_to_process)
        total_saved = 0
        total_updated = 0
        total_revived = 0
        total_skipped = 0
        total_failed = 0

        for i, item in enumerate(campaigns_to_process):
            url = item["url"]
            list_img_url = item["image_url"]
            list_title = item["title"]
            date_str = item["date_str"]

            print(f"\n[{i+1}/{total_found}] Processing: {url}")

            # Check if campaign exists and is active/approved
            with get_db_session() as db:
                existing = db.query(Campaign).filter(Campaign.tracking_url == url, Campaign.card_id == self.card_id).first()
                if not force and existing and existing.is_active and existing.is_approved:
                    print(f"   ⏭️  Skipped (Already exists and active)")
                    total_skipped += 1
                    continue

            # Fetch detail page HTML
            try:
                d_resp = self.session.get(url, timeout=15)
                if d_resp.status_code != 200:
                    print(f"   ⚠️ Detail page HTTP {d_resp.status_code}. Skipping.")
                    total_failed += 1
                    continue
                d_soup = BeautifulSoup(d_resp.text, "html.parser")
            except Exception as e:
                print(f"   ⚠️ Detail fetch error: {e}")
                total_failed += 1
                continue

            # Clean HTML container
            container = d_soup.select_one(".inner-content") or d_soup.select_one("main") or d_soup
            for tag in container.select('script, style, header, footer, nav, .share, .social, a[href*="facebook"], a[href*="whatsapp"], a[href*="linkedin"], a[href*="twitter"]'):
                tag.decompose()

            raw_text = container.text
            clean_lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
            clean_text = f"Kampanya Tarihleri: {date_str}\n\n" + "\n".join(clean_lines)

            # AI Parsing
            print("   🤖 Parsing campaign details with AI...")
            parsed = self.ai_parser.parse_campaign_data(
                raw_text=clean_text,
                title=list_title or None,
                bank_name=self.BANK_NAME,
                card_name=self.CARD_NAME,
                tracking_url=url
            )

            if not parsed:
                print("   ❌ AI parsing failed.")
                total_failed += 1
                continue

            # Title
            final_title = format_turkish_title(parsed.get("title") or list_title or "Money Kart Kampanyası")

            # Dates (AI parsed -> listing date_str fallback)
            s_date, e_date = parse_tr_date_range(date_str)
            ai_s_date = parsed.get("start_date")
            ai_e_date = parsed.get("end_date")

            final_start_date = None
            if ai_s_date:
                try: final_start_date = datetime.strptime(ai_s_date, "%Y-%m-%d").date()
                except Exception: pass
            if not final_start_date:
                final_start_date = s_date

            final_end_date = None
            if ai_e_date:
                try: final_end_date = datetime.strptime(ai_e_date, "%Y-%m-%d").date()
                except Exception: pass
            if not final_end_date:
                final_end_date = e_date

            # Sector lookup
            sector_name = parsed.get("sector", "diger")
            with get_db_session() as db:
                sec_obj = db.query(Sector).filter((Sector.slug == sector_name) | (Sector.name.ilike(sector_name))).first()
                sector_id = sec_obj.id if sec_obj else 1

            # Prepare Campaign object
            new_campaign = Campaign(
                title=final_title,
                slug=generate_slug(final_title),
                description=parsed.get("description", ""),
                reward_text=parsed.get("reward_text", ""),
                reward_value=parsed.get("reward_value"),
                reward_type=parsed.get("reward_type"),
                conditions="\n".join(parsed.get("conditions", [])) if isinstance(parsed.get("conditions"), list) else parsed.get("conditions", ""),
                participation=parsed.get("participation", ""),
                eligible_cards=parsed.get("eligible_cards", "Money Kart"),
                start_date=final_start_date,
                end_date=final_end_date,
                image_url=list_img_url,
                tracking_url=url,
                card_id=self.card_id,
                sector_id=sector_id,
                is_active=True,
                clean_text=clean_text
            )

            # Database Upsert
            with get_db_session() as db:
                updated_camp, op_status = upsert_campaign(db, new_campaign)
                
                if op_status in ("saved", "updated", "revived"):
                    cid = getattr(updated_camp, "id", None)
                    brands_list = parsed.get("brands", [])
                    if cid and isinstance(brands_list, list) and brands_list:
                        clean_b = cleanup_brands(brands_list)
                        from src.services.brand_matcher import get_or_create_brands_list
                        brand_ids = get_or_create_brands_list(
                            db_session=db,
                            brand_names=clean_b,
                            brand_cache={},
                            sector_id=sector_id
                        )
                        for bid in brand_ids:
                            try:
                                link = db.query(CampaignBrand).filter(
                                    CampaignBrand.campaign_id == cid,
                                    CampaignBrand.brand_id == bid
                                ).first()
                                if not link:
                                    db.execute(
                                        CampaignBrand.__table__.insert().values(
                                            campaign_id=cid,
                                            brand_id=bid
                                        )
                                    )
                                    db.commit()
                            except Exception as e:
                                db.rollback()
                                print(f"   ⚠️ CampaignBrand link failed: {e}")

                if op_status == "saved":
                    print(f"   ✅ Saved: {final_title[:45]}...")
                    total_saved += 1
                elif op_status == "updated":
                    print(f"   🔄 Updated: {final_title[:45]}...")
                    total_updated += 1
                elif op_status == "revived":
                    print(f"   ♻️  Revived: {final_title[:45]}...")
                    total_revived += 1
                else:
                    total_skipped += 1

        duration = time.time() - start_time
        print(f"\n============================================================")
        print(f"✅ Money Scraper Finished in {duration:.1f}s")
        print(f"   📊 Found: {total_found} | Saved: {total_saved} | Updated: {total_updated} | Revived: {total_revived} | Skipped: {total_skipped} | Failed: {total_failed}")
        print(f"============================================================")

        clear_cache()
        status = "SUCCESS" if total_failed == 0 else ("PARTIAL" if total_saved > 0 else "FAILED")
        with get_db_session() as db:
            log_scraper_execution(
                db=db,
                scraper_name="money-kart",
                status=status,
                total_found=total_found,
                total_saved=total_saved,
                total_skipped=total_skipped,
                total_failed=total_failed,
                total_revived=total_revived
            )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Money Kart Scraper")
    parser.add_argument("--limit", type=int, help="Limit number of campaigns to scrape")
    parser.add_argument("--force", action="store_true", help="Force scrape existing active campaigns")
    args = parser.parse_args()

    scraper = MoneyScraper()
    scraper.run(limit=args.limit, force=args.force)
