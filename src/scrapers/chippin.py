


import os
import re  # type: ignore # pyre-ignore[21]
import sys
import time  # type: ignore # pyre-ignore[21]
import json  # type: ignore # pyre-ignore[21]
import requests  # type: ignore # pyre-ignore[21]
import urllib3  # type: ignore # pyre-ignore[21]
import random  # type: ignore # pyre-ignore[21]
from datetime import datetime, timezone  # type: ignore # pyre-ignore[21]
from typing import Optional, List, Dict, Any  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup  # type: ignore # pyre-ignore[21]
from dotenv import load_dotenv  # type: ignore # pyre-ignore[21]

# Path setup - reach project root (parent of src)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import create_engine, text  # type: ignore # pyre-ignore[21]
from sqlalchemy.orm import Session, sessionmaker  # type: ignore # pyre-ignore[21]
from src.database import get_db_session, SessionLocal  # type: ignore # pyre-ignore[21]
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked, upsert_campaign  # type: ignore # pyre-ignore[21]
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
from src.services.brand_normalizer import normalize_brand_name, cleanup_brands  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]
from src.services.ai_parser_golden import parse_api_campaign  # type: ignore # pyre-ignore[21]

load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIG ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")
# SQLAlchemy 2.x requires 'postgresql://' not 'postgres://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

BANK_NAME = "Chippin"
BANK_SLUG = "chippin"
BANK_LOGO = "https://www.chippin.com/assets/img/logo.png"

# Card definitions
CARD_DEFINITIONS = {
    "chippin": {
        "name": "Chippin", 
        "slug": "chippin",
        "domain": "https://www.chippin.com"
    }
}

def slugify(text: str) -> str:
    if not text:
        return ""
    # Turkish character mapping (before lowercasing to catch İ and I correctly)
    tr_map = str.maketrans(
        "ÇĞİÖŞÜâîûÂÎÛçğıöşü",
        "cgiosuaiuaiucgiosu"
    )
    text = text.translate(tr_map)
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text  # type: ignore # pyre-ignore[7]

def html_to_text(html_content: str) -> str:
    if not html_content:
        return ""  # type: ignore # pyre-ignore[7]
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    return text  # type: ignore # pyre-ignore[7]

def filter_conditions(conditions: List[str]) -> List[str]:  # type: ignore # pyre-ignore[16,6]
    """Removes legal disclaimers and standard texts."""
    blacklist = [
        "değişiklik yapma hakkı", 
        "saklı tutar", 
        "yazım hataları", 
        "sorumlu tutulamaz", 
        "sorumluluk kabul edilmez",
        "banka kampanya şartlarını",
        "durdurma hakkına sahiptir"
    ]
    
    clean = []
    for c in conditions:
        c_lower = c.lower()
        if any(b in c_lower for b in blacklist):
            continue
        clean.append(c)
    return clean  # type: ignore # pyre-ignore[7]

class ChippinScraper:
    def __init__(self):
        self.engine = create_engine(DATABASE_URL)
        self.ai_parser = AIParser() if GEMINI_API_KEY else None
        self.bank_id = None
        self._card_cache = {}

    def _get_or_create_bank(self):
        try:
            with self.engine.begin() as conn:
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
                print(f"   ✅ Bank ID: {self.bank_id}")
        except Exception as e:
            print(f"   ❌ Bank setup failed: {e}")
            raise

    def _get_or_create_card(self, card_def: dict) -> int:
        slug = card_def["slug"]
        if slug in self._card_cache:
            return self._card_cache[slug]  # type: ignore # pyre-ignore[7]
        try:
            with self.engine.begin() as conn:
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
                self._card_cache[slug] = card_id
                return card_id  # type: ignore # pyre-ignore[7]
        except Exception as e:
            print(f"   ❌ Card setup failed: {e}")
            raise

    def _resolve_sector_by_name(self, sector_name: str) -> Optional[int]:  # type: ignore # pyre-ignore[16,6]
        """Find sector ID by slug. (AI parser returns a sector slug like 'market-gida')"""
        if not sector_name:
            return None  # type: ignore # pyre-ignore[7]
        try:
            with self.engine.connect() as conn:
                # Search by slug since AI is strictly instructed to return valid slugs
                result = conn.execute(
                    text("SELECT id FROM sectors WHERE slug = :slug LIMIT 1"),
                    {"slug": sector_name}
                ).fetchone()
                return result[0] if result else None  # type: ignore # pyre-ignore[7]
        except Exception:
            return None  # type: ignore # pyre-ignore[7]

    def run(self, limit: int = 1000):
        print("🚀 Starting Chippin Scraper (Requests + JSON)...")
        campaigns_to_process = []
        self._get_or_create_bank()
        
        card_key = "chippin"
        card_def = CARD_DEFINITIONS[card_key]
        card_id = self._get_or_create_card(card_def)
        
        url = "https://www.chippin.com/kampanyalar"
        print(f"   🌐 Fetching: {url}")
        
        total_saved = 0
        total_revived = 0
        total_skipped = 0
        total_failed = 0
        error_details = []
        
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        }
        
        try:
            response = requests.get(url, headers=headers, verify=False, timeout=20)
            if response.status_code != 200:
                print(f"   ❌ HTTP Error: {response.status_code}")
                return

            # Extract JSON
            soup = BeautifulSoup(response.text, "html.parser")
            script = soup.find("script", {"id": "__NEXT_DATA__"})
            if not script:
                 print("   ❌ __NEXT_DATA__ not found!")
                 return

            data = json.loads(script.string)
            campaigns = data.get("props", {}).get("pageProps", {}).get("campaigns", [])
            
            print(f"   ✅ Found {len(campaigns)} campaigns in JSON.")
            
            campaigns_to_process = campaigns[:limit]  # type: ignore # pyre-ignore[16,6]
            
            for idx, c in enumerate(campaigns_to_process):
                title = c.get("webName")
                if not title: continue
                
                print(f"[{idx+1}/{len(campaigns_to_process)}] {title[:50]}...")  # type: ignore # pyre-ignore[16,6]
                
                # Image Handling — gerçek görseli JSON'dan çek
                CHIPPIN_CDN = "https://cdn.chippin.com"
                CHIPPIN_BASE = "https://www.chippin.com"
                image_url = None
                
                # 1. JSON alanlarını dene (olası key isimleri)
                for img_key in ["imageUrl", "image", "webImage", "campaignImage", "photo", "coverImage", "imgUrl", "img", "bannerImage", "banner"]:
                    raw_img = c.get(img_key)
                    if raw_img and isinstance(raw_img, str) and not raw_img.startswith("data:") and "logo" not in raw_img.lower():
                        if raw_img.startswith("http"):
                            image_url = raw_img
                        elif raw_img.startswith("/"):
                            image_url = f"{CHIPPIN_BASE}{raw_img}"
                        else:
                            image_url = f"{CHIPPIN_CDN}/{raw_img}"
                        break
                
                # 2. Detay sayfasından çek (JSON'da yoksa)
                if not image_url:
                    cid_for_img = c.get("id")
                    if cid_for_img:
                        detail_url = f"https://www.chippin.com/kampanyalar/{cid_for_img}"
                        try:
                            det_r = requests.get(detail_url, headers=headers, verify=False, timeout=10)
                            if det_r.status_code == 200:
                                det_soup = BeautifulSoup(det_r.text, "html.parser")
                                det_script = det_soup.find("script", {"id": "__NEXT_DATA__"})
                                if det_script:
                                    det_data = json.loads(det_script.string)
                                    campaign_detail = det_data.get("props", {}).get("pageProps", {}).get("campaign", {})
                                    for img_key in ["imageUrl", "image", "webImage", "campaignImage", "photo", "coverImage"]:
                                        raw_img = campaign_detail.get(img_key)
                                        if raw_img and isinstance(raw_img, str) and "logo" not in raw_img.lower():
                                            image_url = raw_img if raw_img.startswith("http") else f"{CHIPPIN_BASE}{raw_img}"
                                            break
                                if not image_url:
                                    for img in det_soup.find_all("img"):
                                        src = img.get("data-src") or img.get("src") or ""
                                        if src and not src.startswith("data:") and "logo" not in src.lower() and "icon" not in src.lower():
                                            image_url = src if src.startswith("http") else f"{CHIPPIN_BASE}{src}"
                                            break
                        except Exception as img_err:
                            print(f"      ⚠️ Görsel detay fetch hatası: {img_err}")


                # Slug & URL Handling
                cid = c.get("id")
                if not cid: continue
                tracking_url = f"https://www.chippin.com/kampanyalar/{cid}"

                # Database Ops - EARLIER CHECK TO SAVE AI CALLS
                SessionLocal = sessionmaker(bind=self.engine)
                try:
                    db = SessionLocal()
                    try:
                        existing = db.query(Campaign).filter(Campaign.tracking_url == tracking_url).first()
                        if existing and existing.is_active and existing.is_approved:
                            # Check if image needs update
                            existing_img = existing.image_url
                            is_placeholder = (
                                not existing_img
                                or existing_img.startswith("/placeholders/")
                                or "logo" in existing_img.lower()
                            )
                            if is_placeholder and image_url:
                                existing.image_url = image_url
                                existing.updated_at = datetime.now(timezone.utc)
                                db.commit()
                                print(f"   🔄 Görsel güncellendi: {title[:40]}")
                            
                            print(f"   ⏭️ Skipped (Already exists and active): {title[:40]}")
                            total_skipped += 1
                            continue
                    finally:
                        db.close()
                except Exception as e:
                    print(f"   ❌ DB Pre-check Error: {e}")

                # Use get_unique_slug
                from src.utils.slug_generator import get_unique_slug
                # We need a temporary session for slug generation before Campaign instantiation
                with SessionLocal() as temp_db:
                    slug = get_unique_slug(
                        title=title,
                        db_session=temp_db,
                        campaign_model=Campaign,
                        tracking_url=tracking_url,
                        card_name="Chippin",
                        bank_name="Chippin"
                    )

                content_raw = c.get("webDescription") or ""
                content_text = html_to_text(content_raw)
                
                # AI Parsing — pass raw HTML from API JSON directly
                ai_data = {}
                parser = self.ai_parser
                if parser and content_raw:
                    try:
                        ai_data = parse_api_campaign(
                            title=title,
                            short_description=None,
                            content_html=content_raw,
                            bank_name=BANK_NAME,
                            scraper_sector=None,
                            tracking_url=tracking_url,
                            og_title=None
                        ) or {}
                    except Exception as e:
                        print(f"      ⚠️  AI Error: {e}")

                # Combine Conditions
                conditions_lines = []
                participation = ai_data.get("participation")
                # participation is written to DB via the participation field separately
                    
                eligible_cards = ai_data.get("cards")
                if eligible_cards:
                    eligible_str = ", ".join(eligible_cards)
                else:
                    # Kullanıcı İsteği: Chippin için kart listesi yoksa 'Tüm Kartlar' yazılsın.
                    eligible_str = "Tüm Kartlar"

                if eligible_str and len(eligible_str) > 255: 
                    eligible_str = eligible_str[:255]  # type: ignore # pyre-ignore[16,6]
                    
                conditions_lines.extend(ai_data.get("conditions", []))
                conditions_lines = filter_conditions(conditions_lines)

                # Reward Handling
                reward_value_raw = ai_data.get("reward_value") or (str(c.get("rebateAmount") or c.get("rebatePercent")) if (c.get("rebateAmount") or c.get("rebatePercent")) else "0")
                reward_val = 0.0
                try:
                    if reward_value_raw:
                        if isinstance(reward_value_raw, str):
                            num_match = re.search(r'[\d\.,]+', reward_value_raw.replace('.', '').replace(',', '.'))
                            reward_val = float(num_match.group()) if num_match else 0.0
                        else:
                            reward_val = float(reward_value_raw)
                except:
                    reward_val = 0.0

                # Database Ops - Insertion with ORM
                try:
                    db = SessionLocal()
                    try:
                        campaign = Campaign(
                            card_id=card_id,
                            sector_id=self._resolve_sector_by_name(str(ai_data.get("sector") or "Diğer")) or self._resolve_sector_by_name("Diğer"),
                            slug=slug,
                            title=ai_data.get("title") or title,
                            description=ai_data.get("description") or "",
                            ai_marketing_text=ai_data.get("ai_marketing_text"),
                            reward_text=ai_data.get("reward_text"),
                            reward_value=reward_val,
                            reward_type=ai_data.get("reward_type"),
                            conditions="\n".join(conditions_lines) if conditions_lines else None,
                            eligible_cards=eligible_str,
                            participation=ai_data.get("participation"),
                            image_url=image_url,
                            start_date=ai_data.get("start_date") or c.get("campaignStartDate"),
                            end_date=ai_data.get("end_date") or c.get("campaignEndDate"),
                            is_active=True,
                            tracking_url=tracking_url,
                            updated_at=datetime.now(timezone.utc),
                            clean_text=ai_data.get('_clean_text') or ai_data.get('clean_text')
                        )

                        # Use centralized upsert_campaign for revival and quality control
                        campaign, op_status = upsert_campaign(db, campaign)
                        db.commit()

                        if op_status == "revived":
                            print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
                            total_revived += 1
                        elif op_status == "saved":
                             print(f"   ✅ Saved: {campaign.title[:50]}...")
                             total_saved += 1
                        
                        db.refresh(campaign)

                        # Brands
                        if ai_data.get("brands"):
                            from src.services.brand_matcher import get_or_create_brands_list
                            brand_ids = get_or_create_brands_list(db, ai_data["brands"], {}, campaign.sector_id)
                            for bid in brand_ids:
                                link_check = db.query(CampaignBrand).filter_by(campaign_id=campaign.id, brand_id=bid).first()
                                if not link_check:
                                    db.add(CampaignBrand(campaign_id=campaign.id, brand_id=bid))
                            db.commit()
                    finally:
                        db.close()
                except Exception as e:
                    print(f"   ❌ DB Error: {e}")
                    total_failed += 1  # type: ignore # pyre-ignore[58]
                    error_details.append({"url": tracking_url, "error": f"DB Error: {str(e)}"})

        except Exception as e:
            print(f"   ❌ Error: {e}")
            total_failed += 1  # type: ignore # pyre-ignore[58]
            error_details.append({"url": url, "error": str(e)})
            
        print(f"✅ Özet: {len(campaigns_to_process)} bulundu, {total_saved} eklendi, {total_revived} canlandırıldı, {total_skipped} atlandı, {total_failed} hata aldı.")

        status = "SUCCESS"
        if total_failed > 0:  # type: ignore # pyre-ignore[58]
             status = "PARTIAL" if (total_saved > 0 or total_skipped > 0 or total_revived > 0) else "FAILED"  # type: ignore # pyre-ignore[58]

        try:
             with SessionLocal() as log_session:
                   log_scraper_execution(
                       db=log_session,
                       scraper_name="chippin",
                       status=status,
                       total_found=len(campaigns_to_process),
                       total_saved=total_saved,
                       total_skipped=total_skipped,
                       total_failed=total_failed,
                       total_revived=total_revived,
                       error_details={"errors": error_details} if error_details else None
                   )
        except Exception as log_e:
             print(f"⚠️ Could not save scraper log: {log_e}")

if __name__ == "__main__":
    import argparse  # type: ignore # pyre-ignore[21]
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    scraper = ChippinScraper()
    scraper.run(limit=args.limit)
