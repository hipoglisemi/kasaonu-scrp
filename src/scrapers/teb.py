import os
import re  # type: ignore # pyre-ignore[21]
import sys
import time  # type: ignore # pyre-ignore[21]
import json  # type: ignore # pyre-ignore[21]
import requests  # type: ignore # pyre-ignore[21]
from typing import Optional, List  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from dotenv import load_dotenv  # type: ignore # pyre-ignore[21]

# Path setup - reach project root (parent of src)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import create_engine, text  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]
from src.services.ai_parser_golden import parse_api_campaign  # type: ignore # pyre-ignore[21]
from src.services.brand_normalizer import cleanup_brands  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked, upsert_campaign  # type: ignore # pyre-ignore[21]
from src.models import Campaign, Sector, Brand, CampaignBrand  # type: ignore
from sqlalchemy.orm import Session, sessionmaker  # type: ignore

load_dotenv()

# --- CONFIG ---
DATABASE_URL = os.getenv("DATABASE_URL")
# PostgreSQL fix for modern SQLAlchemy
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

BASE_URL = "https://www.teb.com.tr"
API_URL = "https://www.teb.com.tr/teb/asmx/TebPublicServiceProxy.asmx/GetFirsatlarWeb"

BANK_NAME = "TEB"
BANK_SLUG = "teb"
BANK_LOGO = "https://www.teb.com.tr/Content/images/teb-logo.png"

# Card definitions — mapped from webCategory field
CARD_DEFINITIONS = {
    "kredi karti": {"name": "TEB Kredi Kartı", "slug": "teb-kredi-karti"},
    "banka karti": {"name": "TEB Banka Kartı", "slug": "teb-banka-karti"},
    "cepteteb":    {"name": "CEPTETEB",         "slug": "cepteteb"},
    "visa":        {"name": "TEB VISA",          "slug": "teb-visa"},
    "default":     {"name": "TEB Genel",         "slug": "teb-genel"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json; charset=utf-8",
    "Referer": "https://www.teb.com.tr/sizin-icin/kampanyalar/",
}


def slugify(text: str) -> str:
    text = text.lower()
    tr_map = str.maketrans("çğıöşüâîûÇĞİÖŞÜÂÎÛ", "cgiosuaiucgiosuaiu")
    text = text.translate(tr_map)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text  # type: ignore # pyre-ignore[7]


def html_to_text(html_content: str) -> str:
    if not html_content:
        return ""  # type: ignore # pyre-ignore[7]
    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup(["script", "style"]):  # type: ignore # pyre-ignore[16,6]
        tag.decompose()
    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines() if line.strip()]
    return "\n".join(lines)  # type: ignore # pyre-ignore[7]


def parse_teb_date(date_str: str) -> Optional[str]:  # type: ignore # pyre-ignore[16,6]
    """Convert TEB date format '2026-02-01T00:00:00.000+0300' to 'YYYY-MM-DD'."""
    if not date_str:
        return None  # type: ignore # pyre-ignore[7]
    try:
        return date_str[:10]  # Just take YYYY-MM-DD  # type: ignore # pyre-ignore[16,7,6]
    except Exception:
        return None  # type: ignore # pyre-ignore[7]


def resolve_card_from_category(web_category: str) -> dict:
    """Map webCategory string to card definition."""
    if not web_category:
        return CARD_DEFINITIONS["default"]  # type: ignore # pyre-ignore[7]
    cat_lower = web_category.lower()
    if "cepteteb" in cat_lower:
        return CARD_DEFINITIONS["cepteteb"]  # type: ignore # pyre-ignore[7]
    if "visa" in cat_lower:
        return CARD_DEFINITIONS["visa"]  # type: ignore # pyre-ignore[7]
    if "kredi" in cat_lower:
        return CARD_DEFINITIONS["kredi karti"]  # type: ignore # pyre-ignore[7]
    if "banka" in cat_lower:
        return CARD_DEFINITIONS["banka karti"]  # type: ignore # pyre-ignore[7]
    return CARD_DEFINITIONS["default"]  # type: ignore # pyre-ignore[7]


class TEBScraper:
    def __init__(self):
        self.engine = create_engine(DATABASE_URL)
        self.ai_parser = AIParser() if GEMINI_API_KEY else None
        self.bank_id = None
        self._card_cache = {}  # slug -> card_id

    def _fetch_campaigns(self) -> list:
        """Fetch all campaigns from TEB API in a single POST request."""
        print("   🌐 Fetching campaigns from TEB API...")
        try:
            response = requests.post(API_URL, headers=HEADERS, json={}, timeout=30)
            response.raise_for_status()
            outer = response.json()
            items = json.loads(outer["d"])
            print(f"   ✅ API returned {len(items)} campaigns")
            return items  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"   ❌ API fetch failed: {e}")
            return []  # type: ignore # pyre-ignore[7]

    def _get_or_create_bank(self):
        """Find or create TEB bank."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT id FROM banks WHERE slug = :slug"),
                    {"slug": BANK_SLUG}
                ).fetchone()
                if result:
                    self.bank_id = result[0]
                else:
                    print(f"   🏦 Creating Bank: {BANK_NAME}")
                    result = conn.execute(text("""
                        INSERT INTO banks (name, slug, logo_url, is_active, created_at)
                        VALUES (:name, :slug, :logo, true, NOW())
                        RETURNING id
                    """), {"name": BANK_NAME, "slug": BANK_SLUG, "logo": BANK_LOGO}).fetchone()
                    self.bank_id = result[0]
                    conn.commit()  # type: ignore # pyre-ignore[16]
                print(f"   ✅ Bank ID: {self.bank_id}")
        except Exception as e:
            print(f"   ❌ Bank setup failed: {e}")
            raise

    def _get_or_create_card(self, card_def: dict) -> int:
        """Find or create a card, cached by slug."""
        slug = card_def["slug"]
        if slug in self._card_cache:
            return self._card_cache[slug]  # type: ignore # pyre-ignore[7]
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT id FROM cards WHERE slug = :slug"),
                    {"slug": slug}
                ).fetchone()
                if result:
                    card_id = result[0]
                else:
                    print(f"   💳 Creating Card: {card_def['name']}")  # type: ignore # pyre-ignore[16,6]
                    result = conn.execute(text("""
                        INSERT INTO cards (name, slug, bank_id, card_type, is_active, created_at)
                        VALUES (:name, :slug, :bank_id, 'credit', true, NOW())
                        RETURNING id
                    """), {"name": card_def["name"], "slug": slug, "bank_id": self.bank_id}).fetchone()  # type: ignore # pyre-ignore[16,6]
                    card_id = result[0]
                    conn.commit()  # type: ignore # pyre-ignore[16]
                self._card_cache[slug] = card_id
                return card_id  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"   ❌ Card setup failed: {e}")
            raise

    def _resolve_sector_by_name(self, sector_name: str) -> Optional[int]:
        """Find sector ID by slug."""
        if not sector_name:
            return None
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT id FROM sectors WHERE slug = :slug LIMIT 1"),
                    {"slug": sector_name}
                ).fetchone()
                return result[0] if result else None
        except Exception:
            return None

    def _save_to_db(self, data: dict, brand_names: Optional[List[str]] = None):
        """Save or update campaign in DB using ORM and upsert_campaign."""
        SessionLocal = sessionmaker(bind=self.engine)
        db = SessionLocal()
        try:
            # 1. Blocklist check
            if is_url_blocked(db, data.get("tracking_url")):
                print(f"   🚫 Skipped (Safety: Blocklisted): {data.get('title')}")
                return "skipped"

            # 2. Prepare Campaign Object
            campaign = Campaign(
                card_id=data.get("card_id"),
                sector_id=data.get("sector_id"),
                slug=data.get("slug"),
                title=data.get("title"),
                description=data.get("description"),
                ai_marketing_text=data.get("ai_marketing_text"),
                reward_text=data.get("reward_text"),
                reward_value=data.get("reward_value"),
                reward_type=data.get("reward_type"),
                conditions=data.get("conditions"),
                eligible_cards=data.get("eligible_cards"),
                participation=data.get("participation"),
                image_url=data.get("image_url"),
                tracking_url=data.get("tracking_url"),
                clean_text=data.get("clean_text"),
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
                is_active=True
            )

            # 3. Use upsert_campaign for revival and quality control
            campaign, op_status = upsert_campaign(db, campaign)
            db.commit()

            if op_status == "revived":
                print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
            elif op_status == "saved":
                 print(f"   ✅ Saved: {campaign.title[:50]}...")
            
            db.refresh(campaign)

            # 4. Handle Brands
            if brand_names:
                from src.services.brand_matcher import get_or_create_brands_list
                brand_ids = get_or_create_brands_list(db, brand_names, {}, data.get("sector_id"))
                for bid in brand_ids:
                    existing_link = db.query(CampaignBrand).filter(
                        CampaignBrand.campaign_id == campaign.id,
                        CampaignBrand.brand_id == bid
                    ).first()
                    if not existing_link:
                        db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                db.commit()

            return op_status
        except Exception as e:
            db.rollback()
            print(f"   ❌ DB Error: {e}")
            return "error"
        finally:
            db.close()

    def _process_item(self, item: dict, card_id: int, card_name: str):
        """Process a single campaign item from the API."""
        title = (item.get("title") or "").strip()
        if not title:
            print("   ⚠️  Skipping: No title.")
            return "skipped"

        tracking_url = item.get("weblink") or ""
        if not tracking_url:
            title_preview = str(title or '')[:40]  # type: ignore
            print(f"   ⚠️  Skipping: No weblink for '{title_preview}'")
            return "skipped"

        # Database Pre-check (Skip Logic)
        try:
            with self.engine.connect() as conn:
                existing = conn.execute(
                    text("SELECT id, is_active FROM campaigns WHERE tracking_url = :url"),
                    {"url": tracking_url}
                ).fetchone()
                if existing and existing[1]:  # existing[1] is is_active
                    print(f"   ⏭️ Skipped (Already exists and active): {title}")
                    return "skipped"
                
                # Blocklist check
                from src.database import get_db_session as _get_db_session  # type: ignore
                with _get_db_session() as db:
                     if is_url_blocked(db, tracking_url):
                          print(f"   🚫 Skipped (Blocklisted): {title}")
                          return "skipped"
        except Exception as e:
            print(f"   ⚠️ DB Pre-check error: {e}")

        # Image: prefer rollup (larger detail image), fallback to page image
        image_url = (
            item.get("publishingRollupImageUrl") or
            item.get("publishingPageImageUrl") or
            None
        )

        # Dates come directly from API — no AI needed
        start_date = parse_teb_date(str(item.get("startDate")))
        end_date = parse_teb_date(str(item.get("endDate")))

        # Content for AI parsing
        content_html = item.get("content") or ""
        content_text = html_to_text(content_html)

        # Enrich content with campaignCode for AI participation parsing
        campaign_code = item.get("campaignCode") or ""
        if campaign_code and campaign_code not in content_text:
            content_text = f"Kampanya Kodu: {campaign_code}\n" + content_text

        # Sector hint from API
        api_sector = (item.get("sectors") or "").replace(";", "").strip()

        # AI Parsing — pass raw HTML directly for centralized BS4 cleaning
        ai_data = {}
        if self.ai_parser and content_html:
            try:
                print(f"      🧠 AI parsing ({len(content_html)} chars HTML)...")
                ai_data = parse_api_campaign(
                    title=title,
                    short_description=None,
                    content_html=content_html,
                    bank_name=BANK_NAME,
                    scraper_sector=api_sector or None,
                    tracking_url=tracking_url,
                    og_title=None
                ) or {}
            except Exception as e:
                print(f"      ⚠️  AI Error: {e}")
                ai_data = {}

        # Build conditions
        conditions_lines: List[str] = []
        participation = ai_data.get("participation") or ""
        if participation:

            pass  # participation field written separately to DB
        # eligible_cards: ai_parser listesi döndürür ama guard ekle
        cards_raw = ai_data.get("cards") or []
        if isinstance(cards_raw, str):
            cards_raw = [c.strip() for c in cards_raw.split(",") if c.strip()]
        eligible_cards_list: List[str] = cards_raw
        
        # conditions listesi
        conds_raw = ai_data.get("conditions") or []
        if isinstance(conds_raw, str):
            conds_raw = [c.strip() for c in conds_raw.split("\n") if c.strip()]
        conditions_lines.extend(conds_raw)

        eligible_cards_str = ", ".join(eligible_cards_list) if eligible_cards_list else None
        if eligible_cards_str and len(eligible_cards_str) > 255:
            eligible_cards_str = eligible_cards_str[:255]  # type: ignore # pyre-ignore[16,6]

        # Slug: use weblink path segment + timestamp for uniqueness
        link_slug = slugify(tracking_url.rstrip("/").split("/")[-1] or title)
        slug = f"{link_slug}-{int(time.time())}" if not link_slug else link_slug

        # Sector: prefer AI result, fallback to API hint
        sector_name = ai_data.get("sector") or api_sector
        sector_id = self._resolve_sector_by_name(sector_name)

        campaign_data = {
            "title": ai_data.get("title") or title,
            "description": ai_data.get("description") or "",
            "image_url": image_url,
            "tracking_url": tracking_url,
            "slug": slug,
            # Dates from API directly (more reliable than AI)
            "start_date": start_date,
            "end_date": end_date,
            "is_active": True,
            "sector_id": sector_id,
            "card_id": card_id,
            "participation": ai_data.get("participation"),
            "conditions": "\n".join(conditions_lines) if conditions_lines else None,
            "eligible_cards": eligible_cards_str,
            "reward_text": ai_data.get("reward_text"),
            "reward_value": ai_data.get("reward_value"),
            "reward_type": ai_data.get("reward_type"),
            "clean_text": ai_data.get("_clean_text"),
            "ai_marketing_text": ai_data.get("ai_marketing_text") or ai_data.get("description") or "",
        }

        return self._save_to_db(campaign_data, ai_data.get("brands", []))  # type: ignore # pyre-ignore[7]

    def run(self, limit: int = 1000, card_filter: str = "all"):
        """
        Main entry point.
        card_filter: 'kredi' | 'banka' | 'cepteteb' | 'visa' | 'all'
        """
        print("🚀 Starting TEB Scraper (API Mode)...")
        print(f"   🌐 API: {API_URL}")

        self._get_or_create_bank()

        items = self._fetch_campaigns()
        if not items:
            print("   ❌ No campaigns found. Exiting.")
            return

        # Filter by card type if requested
        if card_filter != "all":
            before_filter_count = len(items)
            items = [
                item_data for item_data in items
                if card_filter.lower() in (item_data.get("webCategory") or "").lower()
            ]
            print(f"   🔍 Filtered to {len(items)} campaigns (from {before_filter_count}) by '{card_filter}'")

        items = items[:limit]  # type: ignore # pyre-ignore[16,6]
        print(f"\n   🎯 Processing {len(items)} campaigns...\n")

        success = revived = skipped = failed = 0
        error_details = []

        for idx, item in enumerate(items):
            title = item.get("title", "?")[:60]  # type: ignore # pyre-ignore[16,6]
            print(f"[{idx+1}/{len(items)}] {title}")

            # Determine card from webCategory
            web_category = item.get("webCategory") or ""
            card_def = resolve_card_from_category(web_category)
            try:
                card_id = self._get_or_create_card(card_def)
            except Exception as e:
                print(f"   ❌ Card error: {e}")
                failed += 1  # type: ignore # pyre-ignore[58]
                error_details.append({"url": item.get("weblink", "unknown"), "error": f"Card error: {str(e)}"})
                continue

            try:
                # Same issue as QNB: _process_item actually needs to return the result of _save_to_db, but it is already doing that.
                res = self._process_item(item, card_id, card_def["name"])
                if res == "saved":
                    success += 1  # type: ignore # pyre-ignore[58]
                elif res == "revived":
                    revived += 1
                elif res == "skipped":
                    skipped += 1  # type: ignore # pyre-ignore[58]
                else:
                    failed += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": item.get("weblink", "unknown"), "error": f"Process returned {res}"})
            except Exception as e:
                print(f"   ❌ Failed: {e}")
                failed += 1  # type: ignore # pyre-ignore[58]
                error_details.append({"url": item.get("weblink", "unknown"), "error": str(e)})

            time.sleep(0.5)

        print("\n🏁 TEB Scraper Finished.")
        print(f"✅ Özet: {len(items)} bulundu, {success} eklendi, {revived} canlandı, {skipped} atlandı, {failed} hata aldı.")
        
        status = "SUCCESS"
        if failed > 0:  # type: ignore # pyre-ignore[58]
            status = "PARTIAL" if (success > 0 or skipped > 0) else "FAILED"  # type: ignore # pyre-ignore[58]
             
        try:
            from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
            from sqlalchemy.orm import sessionmaker  # type: ignore # pyre-ignore[21]
            SessionLocal = sessionmaker(bind=self.engine)
            with SessionLocal() as db:
                log_scraper_execution(
                    db=db,
                    scraper_name="teb",
                    status=status,
                    total_found=len(items),
                    total_saved=success,
                    total_skipped=skipped,
                    total_failed=failed,
                    total_revived=revived,
                    error_details={"errors": error_details} if error_details else None
                )
        except Exception as le:
            print(f"⚠️ Could not save scraper log: {le}")


if __name__ == "__main__":
    import argparse  # type: ignore # pyre-ignore[21]

    parser = argparse.ArgumentParser(description="TEB Scraper")
    parser.add_argument("--limit", type=int, default=1000, help="Max campaigns to process")
    parser.add_argument(
        "--card-filter", type=str, default="all",
        help="Filter by card type: kredi | banka | cepteteb | visa | all"
    )
    args = parser.parse_args()

    scraper = TEBScraper()
    scraper.run(limit=args.limit, card_filter=args.card_filter)
