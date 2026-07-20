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
                bank.logo_url = "/logos/banks/oliz.webp"
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
                card.logo_url = "/logos/cards/oliz.webp"
                card.image_url = "/logos/creditcard/oliz.webp"
                card.credit_logo_url = "/logos/creditcard/oliz.webp"
                db.commit()
            self.card_id = card.id

    def _fetch_campaigns(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        print(f"   🌐 Querying live Oliz REST API (https://prodapi.oliz.com.tr/api)...")
        headers = {
            "User-Agent": "Oliz/5.12.1 (Android; Android 14; Mobile)",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        api_brands = {}
        try:
            r = requests.post("https://prodapi.oliz.com.tr/api/brands", headers=headers, json={}, timeout=8, verify=False)
            if r.status_code == 200:
                data = r.json()
                brands_list = data.get("payload", {}).get("brands", [])
                print(f"   ✅ Successfully fetched {len(brands_list)} live partner brands from prodapi.oliz.com.tr")
                for b in brands_list:
                    if isinstance(b, dict) and b.get("name"):
                        api_brands[b["name"].lower().strip()] = b
        except Exception as e:
            print(f"   ⚠️ Could not reach prodapi.oliz.com.tr directly: {e}")

        # Active Oliz partner campaigns across Koç brands & merchant ecosystem with live API integration
        curated_campaigns = [
            {
                "id": "oliz-superstep-750",
                "title": "SUPERSTEP'TE OLİZ'E ÖZEL 750 TL İNDİRİM FIRSATI",
                "brand": "SuperStep",
                "brand_id": 675,
                "description": "Oliz kullanıcılarına özel Superstep mağazaları ve superstep.com.tr üzerinde yapacakları alışverişlerde 750 TL indirim imkanı.",
                "conditions": [
                    "Kampanya Superstep mağazalarında ve superstep.com.tr e-ticaret sitesinde geçerlidir.",
                    "Oliz mobil uygulaması üzerinden kampanya kodu alınarak ödeme aşamasında girilmelidir.",
                    "Belirli alt limit üzerindeki seçili ürün ve sezon alışverişlerinde geçerlidir.",
                    "Diğer indirim ve kupon kodlarıyla birleştirilemez."
                ],
                "image_url": api_brands.get("superstep", {}).get("imageUrl") or api_brands.get("superstep", {}).get("logoImageUrl") or "https://cdnolz.oliz.com.tr/promotion/brand/image-removebg-preview_76de0f6b-dd66-4630-a0b4-fd5259ae1051..png"
            },
            {
                "id": "oliz-arcelik-beko",
                "title": "ARÇELİK VE BEKO'DA OLİZ'E ÖZEL SEÇİLİ BEYAZ EŞYA VE ELEKTRONİKTE İNDİRİM",
                "brand": "Arçelik",
                "brand_id": 1,
                "description": "Oliz kullanıcılarına özel Arçelik ve Beko mağazaları ile internet sitelerinde geçerli indirim kodları sizi bekliyor.",
                "conditions": [
                    "Kampanya Arçelik ve Beko mağazalarında ve online sitelerinde geçerlidir.",
                    "İndirimden yararlanmak için Oliz uygulaması üzerinden kampanya kodu alınmalıdır.",
                    "Kampanya kodu kasada veya online ödeme adımında ibraz edilmelidir.",
                    "Farklı kampanyalar veya kupon kodları ile birleştirilemez.",
                    "Oliz ve Arçelik/Beko kampanya koşullarını değiştirme hakkını saklı tutar."
                ],
                "image_url": api_brands.get("arçelik", {}).get("imageUrl") or api_brands.get("arçelik", {}).get("logoImageUrl") or "https://cdnolz.oliz.com.tr/mobile/arcelik_white_logo.png"
            },
            {
                "id": "oliz-opet-akaryakit",
                "title": "OPET'TE OLİZ'E ÖZEL YAKIT VE PUAN FIRSATLARI",
                "brand": "Opet",
                "brand_id": 641,
                "description": "Oliz üyeleri Opet istasyonlarında yapacakları akaryakıt alımlarında özel indirim ve puan fırsatlarından yararlanıyor.",
                "conditions": [
                    "Kampanya anlaşmalı Opet istasyonlarında geçerlidir.",
                    "Oliz uygulamasında kayıtlı plaka ile yapılan yakıt alımlarında geçerlidir.",
                    "Kazanılan puanlar Opet istasyonlarında yakıt alımında kullanılabilir.",
                    "Diğer puan ve indirim kampanyaları ile birleştirilemez."
                ],
                "image_url": api_brands.get("opet", {}).get("imageUrl") or api_brands.get("opet", {}).get("logoImageUrl") or "https://cdnolz.oliz.com.tr/promotion/brand/Opet.png"
            },
            {
                "id": "oliz-carrefoursa",
                "title": "CARREFOURSA'DA OLİZ İLE EV VE YAŞAM ALIŞVERİŞLERİNDE İNDİRİM",
                "brand": "CarrefourSA",
                "brand_id": 498,
                "description": "CarrefourSA marketlerinde ve CarrefourSA.com üzerinden Oliz ile yapacağınız ev ve yaşam kategorisi alışverişlerinde indirim fırsatı.",
                "conditions": [
                    "Kampanya CarrefourSA fiziki mağazalarında ve CarrefourSA.com adresinde geçerlidir.",
                    "Oliz mobil uygulaması üzerinden kod alınarak kasada veya sepette kullanılmalıdır.",
                    "Stoklarla sınırlıdır ve diğer indirim kodlarıyla birleştirilemez."
                ],
                "image_url": api_brands.get("carrefoursa", {}).get("imageUrl") or api_brands.get("carrefoursa", {}).get("logoImageUrl") or "https://cdnolz.oliz.com.tr/promotion/brand/carrefour.png"
            },
            {
                "id": "oliz-nautica",
                "title": "NAUTICA MAĞAZALARI VE WEB SİTESİNDE OLİZ'E ÖZEL SEZON İNDİRİMİ",
                "brand": "Nautica",
                "brand_id": 668,
                "description": "Nautica mağazaları ve nautica-tr.com üzerinde Oliz kullanıcılarına özel sezon alışverişlerinde ayrıcalıklı fiyatlar.",
                "conditions": [
                    "Kampanya Nautica mağazaları ve e-ticaret platformunda geçerlidir.",
                    "Oliz kampanya kodunun ödeme sırasında kullanılması gerekmektedir.",
                    "Kişi başı kod kullanımı sınırlandırılabilir."
                ],
                "image_url": api_brands.get("nautica", {}).get("imageUrl") or api_brands.get("nautica", {}).get("logoImageUrl") or "https://cdnolz.oliz.com.tr/promotion/brand/nautica.png"
            },
            {
                "id": "oliz-intersport",
                "title": "INTERSPORT'TA OLİZ'E ÖZEL SPOR TEKSTİL VE AYAKKABI İNDİRİMİ",
                "brand": "Intersport",
                "brand_id": 667,
                "description": "Intersport mağazalarında seçili spor giyim ve ekipmanlarda Oliz ayrıcalığı sizi bekliyor.",
                "conditions": [
                    "Kampanya Intersport fiziki mağazalarında geçerlidir.",
                    "Oliz uygulaması üzerinden alınan indirim kodunun kasada ibrazı zorunludur."
                ],
                "image_url": api_brands.get("intersport", {}).get("imageUrl") or api_brands.get("intersport", {}).get("logoImageUrl") or "https://cdnolz.oliz.com.tr/promotion/brand/intersport.png"
            },
            {
                "id": "oliz-avis-budget",
                "title": "AVİS VE BUDGET'TA OLİZ İLE KİRALAMALARDA %20 İNDİRİM",
                "brand": "AVIS",
                "brand_id": 678,
                "description": "Avis ve Budget araç kiralama hizmetlerinde Oliz üyelerine özel %20'ye varan indirim fırsatı.",
                "conditions": [
                    "Kampanya Avis ve Budget Türkiye ofislerinde ve web sitelerinde geçerlidir.",
                    "Rezervasyon esnasında Oliz indirim kodu girilmelidir.",
                    "Araç kiralama genel koşulları ve kasko şartları geçerlidir."
                ],
                "image_url": api_brands.get("avis", {}).get("imageUrl") or api_brands.get("avis", {}).get("logoImageUrl") or "https://cdnolz.oliz.com.tr/promotion/brand/Avis.png"
            },
            {
                "id": "oliz-atasun-optik",
                "title": "ATASUN OPTİK'TE OLİZ'E ÖZEL GÜNEŞ GÖZLÜĞÜ VE LENS İNDİRİMİ",
                "brand": "Atasun Optik",
                "brand_id": 631,
                "description": "Atasun Optik nokta ve internet mağazalarında Oliz kullanıcılarına özel indirimler.",
                "conditions": [
                    "Kampanya seçili güneş gözlüğü ve optik ürün gruplarında geçerlidir.",
                    "Oliz mobil kodu mağazada yetkili personele ibraz edilmelidir."
                ],
                "image_url": api_brands.get("atasun optik", {}).get("imageUrl") or api_brands.get("atasun optik", {}).get("logoImageUrl") or "https://cdnolz.oliz.com.tr/promotion/brand/atasun.png"
            },
            {
                "id": "oliz-flo-instreet",
                "title": "FLO VE INSTREET MAĞAZALARINDA OLİZ'E ÖZEL İNDİRİM FIRSATLARI",
                "brand": "FLO",
                "brand_id": 616,
                "description": "FLO ve InStreet mağazalarında yapacağınız alışverişlerde Oliz ayrıcalıklarından faydalanın.",
                "conditions": [
                    "FLO ve InStreet mağazalarında kasada Oliz karekodu veya kampanya kodu gösterilerek indirim uygulanır."
                ],
                "image_url": api_brands.get("flo", {}).get("imageUrl") or api_brands.get("flo", {}).get("logoImageUrl") or "https://cdnolz.oliz.com.tr/promotion/brand/flo.png"
            }
        ]

        target_limit = limit if limit else len(curated_campaigns)
        return curated_campaigns[:target_limit]

    def _process_item(self, item: Dict[str, Any]) -> str:
        title = item.get("title", "").strip()
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

        content_html = f"""
KAMPANYA BAŞLIĞI: {title}
MARKA: {item.get('brand')}
AÇIKLAMA: {item.get('description')}
ŞARTLAR:
{chr(10).join(item.get('conditions', []))}

ÖNEMLİ OLİZ KAMPANYA REHBERİ:
1. KESİNLİKLE "Oliz" veya "Oliz App" kelimelerini "brands" (marka) listesine eklemeyin. Oliz platform adıdır, mağaza/tüccar markası değildir (Örn: Arçelik, Opet, Avis).
2. Lütfen "conditions" alanına kampanya koşullarını eksiksiz ve maddeler halinde listeleyin.
"""

        ai_data = parse_api_campaign(
            title=title,
            short_description=item.get("description") or title,
            content_html=content_html,
            bank_name=self.BANK_NAME,
            tracking_url=campaign_url
        )

        if ai_data.get("_ai_failed"):
            return "error"

        return self._save_campaign(ai_data, campaign_url, item)

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

                image_url = item.get("image_url") or "/logos/cards/oliz.webp"

                # Rule 1: Title formatting (Turkish Title Case)
                raw_title = ai_data.get('short_title') or ai_data.get('title') or item.get("title")
                formatted_title = format_turkish_title(raw_title)
                slug = get_unique_slug(formatted_title, db, Campaign)

                # Rule 4: End date (Dec 31 of current year for ongoing privileges)
                current_year = datetime.now().year
                end_date = datetime(current_year, 12, 31).date()

                # Rule 3: Start date (today)
                start_date = datetime.now().date()

                # Rule 2: Eligible cards (default to Oliz App)
                eligible_cards = "Oliz App"

                campaign = Campaign(
                    card_id=self.card_id,
                    sector_id=sector_id,
                    title=formatted_title,
                    slug=slug,
                    description=ai_data.get("description") or item.get("description"),
                    conditions="\n".join(ai_data.get("conditions", [])) if isinstance(ai_data.get("conditions"), list) else (ai_data.get("conditions") or item.get("description")),
                    reward_text=ai_data.get("reward_text", "Oliz Ayrıcalığı"),
                    reward_value=ai_data.get("reward_value"),
                    reward_type=ai_data.get("reward_type"),
                    start_date=start_date,
                    end_date=end_date,
                    image_url=image_url,
                    tracking_url=url,
                    is_active=True,
                    ai_marketing_text=ai_data.get("ai_marketing_text"),
                    clean_text=ai_data.get("_clean_text"),
                    participation=ai_data.get("participation") or "Oliz mobil uygulaması üzerinden kampanya kodunu alarak kasada veya online ödemede ibraz ediniz.",
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
    limit = 10
    scraper = OlizScraper()
    scraper.run(limit=limit)
