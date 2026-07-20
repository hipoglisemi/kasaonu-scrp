import sys
import os

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.database import get_db_session
from src.models import Bank, Card, Sector, Campaign, CampaignBrand
from src.services.ai_parser import parse_api_campaign
from src.utils.logger_utils import log_scraper_execution
from src.services.brand_normalizer import cleanup_brands
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


class OlizScraper:
    """
    Scraper for Oliz (Koç Topluluğu) campaigns and member privileges.
    """

    BASE_URL = "https://www.oliz.com.tr"
    BANK_NAME = "Oliz"
    CARD_NAME = "Oliz"
    CARD_SLUG = "oliz"

    def __init__(self):
        self.bank_id = None
        self.card_id = None

        with get_db_session() as db:
            bank = db.query(Bank).filter((Bank.slug == "oliz") | (Bank.name.ilike("%oliz%"))).first()
            if not bank:
                print(f"   🏦 Creating Bank: {self.BANK_NAME}")
                bank = Bank(name=self.BANK_NAME, slug="oliz", logo_url="/logos/banks/oliz.webp", is_active=True)
                db.add(bank)
                db.commit()
                db.refresh(bank)
            else:
                bank.logo_url = "/logos/banks/oliz.webp"  # type: ignore
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
                    logo_url="/logos/cards/oliz.webp",
                    image_url="/logos/creditcard/oliz.webp",
                    credit_logo_url="/logos/creditcard/oliz.webp",
                    is_active=True
                )
                db.add(card)
                db.commit()
                db.refresh(card)
            else:
                card.logo_url = "/logos/cards/oliz.webp"  # type: ignore
                card.image_url = "/logos/creditcard/oliz.webp"  # type: ignore
                card.credit_logo_url = "/logos/creditcard/oliz.webp"  # type: ignore
                db.commit()
            self.card_id = card.id

    def _fetch_campaigns(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        print(f"   🌐 Querying live Oliz REST API (https://prodapi.oliz.com.tr/api/member/promotions)...")
        headers = {
            "user-agent": "Dart/3.12 (dart:io)",
            "guest-token": "ac4f475e-73a6-4598-a7c8-154833f74b3d",
            "platform": "1",
            "content-type": "application/json",
            "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9uYW1lIjoiMDAwMDAwMDAtMDAwMC0wMDAwLTA4ZGQtZTIzYWI5ZTIwZTFjIiwianRpIjoiNWQyZTliNjQtNGZjOS00MWNlLWJkZTAtNDEwNjI1MjU1ZWJhIiwiaHR0cDovL3NjaGVtYXMueG1sc29hcC5vcmcvd3MvMjAwNS8wNS9pZGVudGl0eS9jbGFpbXMvZW1haWxhZGRyZXNzIjoiNTU0MTgxODQwNEBhcmNlbGlrcGx1cy5jb20iLCJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9tb2JpbGVwaG9uZSI6IjU1NDE4MTg0MDQiLCJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9naXZlbm5hbWUiOiJPxJ91eiIsImh0dHA6Ly9zY2hlbWFzLnhtbHNvYXAub3JnL3dzLzIwMDUvMDUvaWRlbnRpdHkvY2xhaW1zL3N1cm5hbWUiOiJLQVJBRVZMxLAiLCJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9hdXRoZW50aWNhdGlvbiI6IjIwMjUtMDgtMjNUMTE6NDY6NTYuMDM0MjYyNSIsImh0dHA6Ly9zY2hlbWFzLm1pY3Jvc29mdC5jb20vd3MvMjAwOC8wNi9pZGVudGl0eS9jbGFpbXMvcm9sZSI6Ik1lbWJlciBSb2xlIiwiZXhwIjoxNzg0NTg4NjIwLCJpc3MiOiJodHRwOi8vYXV0aGVudGljYXRpb24iLCJhdWQiOiJodHRwOi8vYXV0aGVudGljYXRpb24ifQ.TdS8Jw_6QF-0F7MK792K0R_6BYKEJfSAos79RbsjlIg"
        }
        self.api_headers = headers

        try:
            r = requests.post("https://prodapi.oliz.com.tr/api/member/promotions", headers=headers, json={"keyword":"","brandIds":[],"categoryIds":[]}, timeout=15, verify=False)
            if r.status_code == 200:
                data = r.json()
                campaigns = data.get("payload", {}).get("campaigns", [])
                print(f"   ✅ Successfully fetched {len(campaigns)} live campaigns from Oliz API.")
                if limit:
                    return campaigns[:limit]
                return campaigns
            else:
                print(f"   ❌ Failed to fetch campaigns. Status: {r.status_code}. Response: {r.text[:200]}")
                return []
        except Exception as e:
            print(f"   ⚠️ Exception while querying Oliz API: {e}")
            return []

    def _process_item(self, item: Dict[str, Any]) -> str:
        title = item.get("name", "").strip()
        if not title:
            return "skipped"

        c_id = item.get("id")
        campaign_url = f"{self.BASE_URL}/oliz_avantajlari#{c_id}"

        with get_db_session() as db:
            if is_url_blocked(db, campaign_url):
                print(f"   🚫 Skipped (Blocklisted): {title}")
                return "skipped"

            existing = db.query(Campaign).filter(Campaign.tracking_url == campaign_url).first()
            if existing and existing.is_active and existing.is_approved:
                print(f"   ⏭️ Skipped (Already exists and active): {title}")
                return "skipped"

        # Fetch Detailed Promotion Information
        detailed_item = dict(item)
        try:
            r = requests.post(f"https://prodapi.oliz.com.tr/api/member/get-promotion/{c_id}", headers=self.api_headers, json={}, timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json()
                promo_details = data.get("payload", {}).get("promotion", {})
                if promo_details:
                    detailed_item.update(promo_details)
        except Exception as e:
            print(f"   ⚠️ Could not fetch details for {c_id}: {e}")

        # Construct Rich Text for AI
        desc = detailed_item.get("description", "")
        conditions = detailed_item.get("participationConditions", "")
        how_to_use = detailed_item.get("howToUse", "")
        how_to_use_store = detailed_item.get("howToUseStore", "")
        how_to_use_web = detailed_item.get("howToUseWeb", "")
        
        full_conditions = "\n".join(filter(None, [conditions, how_to_use, how_to_use_store, how_to_use_web]))
        
        content_html = f"""
KAMPANYA BAŞLIĞI: {title}
AÇIKLAMA: {desc}
ŞARTLAR:
{full_conditions}

ÖNEMLİ OLİZ KAMPANYA REHBERİ:
1. KESİNLİKLE "Oliz" veya "Oliz App" kelimelerini "brands" (marka) listesine eklemeyin. Oliz platform adıdır, mağaza/tüccar markası değildir.
2. Lütfen "conditions" alanına kampanya koşullarını eksiksiz ve maddeler halinde listeleyin.
"""

        ai_data = parse_api_campaign(
            title=title,
            short_description=desc or title,
            content_html=content_html,
            bank_name=self.BANK_NAME,
            tracking_url=campaign_url
        )

        if ai_data.get("_ai_failed"):
            return "error"

        return self._save_campaign(ai_data, campaign_url, detailed_item)

    def _save_campaign(self, ai_data: Dict[str, Any], url: str, item: Dict[str, Any]) -> str:
        try:
            with get_db_session() as db:
                if is_url_blocked(db, url):
                    print(f"   🚫 Skipped (Safety: Blocklisted): {ai_data.get('title') or url}")
                    return "skipped"

                # Filter out Oliz platform name so it is NEVER linked as a merchant brand
                if ai_data.get('brands'):
                    ai_data['brands'] = [
                        b for b in ai_data.get('brands', [])
                        if str(b).strip().lower() not in ['oliz', 'olız', 'oliz app', 'oliz üyeleri']
                    ]

                if item.get('brand') and item['brand'] not in ai_data.get('brands', []):
                    ai_data.setdefault('brands', []).append(item['brand'])

                final_sector_slug = ai_data.get('sector')

                if ai_data.get('brands'):
                    from src.models import PointBlankRule
                    pbe_rules = db.query(PointBlankRule).filter(
                        PointBlankRule.brand_name.in_(ai_data.get('brands')),
                        PointBlankRule.is_verified == True
                    ).all()
                    for rule in pbe_rules:
                        if rule.sector_slug and rule.sector_slug != 'BLACKLIST':
                            final_sector_slug = rule.sector_slug
                            print(f"      [PBE Override] Forced sector to '{final_sector_slug}' due to brand '{rule.brand_name}'")
                            break

                sector = db.query(Sector).filter((Sector.slug == final_sector_slug) | (Sector.name.ilike(final_sector_slug))).first() if final_sector_slug else None
                if not sector:
                    sector = db.query(Sector).filter(Sector.slug == 'diger').first()
                sector_id = sector.id if sector else None

                image_url = item.get("coverImageUrl") or item.get("thumbnailUrl") or "/logos/cards/oliz.webp"

                # Rule 1: Title formatting (Turkish Title Case)
                raw_title = ai_data.get('short_title') or ai_data.get('title') or item.get("name")
                formatted_title = format_turkish_title(raw_title)
                slug = get_unique_slug(formatted_title, db, Campaign)

                if item.get("endDate"):
                    try:
                        # Parse ISO 8601 string (e.g. "2026-08-31T23:59:00+03:00")
                        end_date_str = item["endDate"].split("T")[0]
                        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                    except ValueError:
                        current_year = datetime.now().year
                        end_date = datetime(current_year, 12, 31).date()
                else:
                    current_year = datetime.now().year
                    end_date = datetime(current_year, 12, 31).date()

                # Rule 3: Start date (today)
                start_date = datetime.now().date()

                # Rule 2: Eligible cards (default to Oliz App)
                eligible_cards = "Oliz App"

                participation = ai_data.get("participation") or "Oliz mobil uygulaması üzerinden kampanya kodunu alarak kasada veya online ödemede ibraz ediniz."
                reward_text = ai_data.get("reward_text") or "Oliz Ayrıcalığı"
                reward_value = ai_data.get("reward_value")
                reward_type = ai_data.get("reward_type")
                conditions = ai_data.get("conditions") if isinstance(ai_data.get("conditions"), str) else "\n".join(ai_data.get("conditions", []))

                campaign = Campaign(
                    card_id=self.card_id,
                    sector_id=sector_id,
                    title=formatted_title,
                    slug=slug,
                    description=item.get("description") or ai_data.get("description") or "",
                    conditions=conditions,
                    reward_text=reward_text,
                    reward_value=reward_value,
                    reward_type=reward_type,
                    start_date=start_date,
                    end_date=end_date,
                    image_url=image_url,
                    tracking_url=url,
                    is_active=True,
                    ai_marketing_text=ai_data.get("ai_marketing_text"),
                    clean_text=ai_data.get("_clean_text"),
                    participation=participation,
                    eligible_cards=eligible_cards
                )

                campaign, op_status = upsert_campaign(db, campaign)
                db.commit()

                if op_status == "revived":
                    print(f"   ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
                elif op_status == "saved":
                    print(f"   ✅ Saved: {campaign.title[:50]}...")

                db.refresh(campaign)

                if ai_data.get('brands'):
                    clean_brands = cleanup_brands(ai_data.get('brands'))
                    from src.services.brand_matcher import get_or_create_brands_list
                    brand_ids = get_or_create_brands_list(
                        db_session=db,
                        brand_names=ai_data.get("brands", []),
                        brand_cache=getattr(self, 'brand_cache', {}),
                        sector_id=sector.id if sector else None
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
                        except Exception as e:
                            db.rollback()
                            print(f"   ⚠️ CampaignBrand link failed: {e}")
            return op_status
        except Exception as e:
            print(f"      ❌ DB Save Error: {e}")
            return "error"

    def run(self, limit: Optional[int] = None):
        print(f"🚀 Starting Oliz Scraper...")
        items = self._fetch_campaigns(limit=limit)

        success: int = 0
        revived: int = 0
        skipped: int = 0
        failed: int = 0
        error_details: List[Dict[str, Any]] = []

        for item in items:
            try:
                res = self._process_item(item)
                if res == "saved":
                    success += 1
                elif res == "revived":
                    revived += 1
                elif res == "skipped":
                    skipped += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                error_details.append({"url": str(item.get("id")), "error": str(e)})

        status = "SUCCESS" if failed == 0 else ("PARTIAL" if success > 0 else "FAILED")
        with get_db_session() as db:
            log_scraper_execution(
                db=db,
                scraper_name="oliz",
                status=status,
                total_found=len(items),
                total_saved=success,
                total_skipped=skipped,
                total_failed=failed,
                total_revived=revived,
                error_details={"errors": error_details} if error_details else None
            )

        clear_cache('campaigns:*')


if __name__ == "__main__":
    limit = None
    scraper = OlizScraper()
    scraper.run(limit=limit)
