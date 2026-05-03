



import asyncio  # type: ignore # pyre-ignore[21]
import random  # type: ignore # pyre-ignore[21]
import time  # type: ignore # pyre-ignore[21]
import os
import re  # type: ignore # pyre-ignore[21]
import uuid  # type: ignore # pyre-ignore[21]
import sys
import requests  # type: ignore # pyre-ignore[21]
from typing import List, Dict, Any, Optional  # type: ignore # pyre-ignore[21]
from datetime import datetime  # type: ignore # pyre-ignore[21]
from decimal import Decimal  # type: ignore # pyre-ignore[21]
from urllib.parse import urljoin  # type: ignore # pyre-ignore[21]
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from playwright.sync_api import sync_playwright # type: ignore

# Path setup to ensure imports work correctly
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session  # type: ignore # pyre-ignore[21]
from src.models import Bank, Card, Sector, Brand, Campaign, CampaignBrand  # type: ignore # pyre-ignore[21]
from src.services.ai_parser import AIParser  # type: ignore # pyre-ignore[21]
from src.services.ai_parser_golden import parse_api_campaign  # type: ignore # pyre-ignore[21]
from src.utils.scraper_utils import is_url_blocked  # type: ignore # pyre-ignore[21]
from src.services.brand_matcher import get_or_create_brands_list  # type: ignore # pyre-ignore[21]
from src.utils.logger_utils import log_scraper_execution  # type: ignore # pyre-ignore[21]
from src.utils.slug_generator import generate_slug  # type: ignore # pyre-ignore[21]

class TurkTelekomScraper:
    """
    Türk Telekom Mobil Kampanyaları Scraper
    Uses Requests/BeautifulSoup for high efficiency since content is SSR.
    """
    
    BASE_URL = "https://bireysel.turktelekom.com.tr"
    LISTING_URLS = [
        "https://bireysel.turktelekom.com.tr/bi-dunya-firsat",
        "https://bireysel.turktelekom.com.tr/mobil/kampanyalar",
        "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari",
        "https://www.selfy.com.tr/kampanyalar"
    ]
    
    def __init__(self, max_campaigns: int = 250, headless: bool = True, manual_json: str = None):
        self.max_campaigns = max_campaigns
        self.manual_json_path = manual_json
        # headless param kept for compatibility with other scrapers even if not used here
        self.db: Optional[Session] = None  # type: ignore # pyre-ignore[16,6]
        self.parser = AIParser()
        
        # Cache
        self.bank_cache: Optional[Bank] = None  # type: ignore # pyre-ignore[16,6]
        self.card_cache: Dict[str, Card] = {}  # type: ignore # pyre-ignore[16,6]
        self.sector_cache: Dict[str, Sector] = {}  # type: ignore # pyre-ignore[16,6]
        self.brand_cache: Dict[str, Brand] = {}  # type: ignore # pyre-ignore[16,6]

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def run(self):
        """Hardened sync entry point"""
        try:
            print("🚀 Starting Türk Telekom Scraper (Hardened Final Run)...")
            self.db = get_db_session()
            self._load_cache()
            
            discovery_items = []
            if self.manual_json_path and os.path.exists(self.manual_json_path):
                print(f"   📂 Loading verified discovery data from {self.manual_json_path}...")
                import json
                with open(self.manual_json_path, 'r') as f:
                    discovery_items = json.load(f)
            else:
                discovery_items = self._scrape_list_all()
            
            print(f"   📋 Found {len(discovery_items)} campaigns to process.")
            
            success_count = 0
            total_revived = 0
            skipped_count = 0
            failed_count = 0
            error_details = []
            for i, item in enumerate(discovery_items, 1):
                url = item['url']
                p_title = item.get('title')
                print(f"   [{i}/{len(discovery_items)}] {url}")
                try:
                    res = self._scrape_detail(url, predefined_title=p_title)
                    if res == "saved":
                        success_count += 1
                    elif res == "revived":
                        total_revived += 1
                    elif res == "skipped":
                        skipped_count += 1
                    else:
                        failed_count += 1
                    # Small delay to be polite
                    time.sleep(random.uniform(0.3, 0.8))
                except Exception as e:
                    print(f"      ❌ Error processing {url}: {e}")
                    failed_count += 1
                    error_details.append({"url": url, "error": str(e)})
            
            print(f"\n✅ Scraping complete! Found: {len(discovery_items)}, Saved: {success_count}, Revived: {total_revived}, Skipped: {skipped_count}, Failed: {failed_count}")
            
            # Log execution
            status = "SUCCESS" if failed_count == 0 else ("PARTIAL" if (success_count > 0 or total_revived > 0) else "FAILED")
            log_scraper_execution(
                db=self.db,
                scraper_name="turktelekom",
                status=status,
                total_found=len(discovery_items),
                total_saved=success_count,
                total_skipped=skipped_count,
                total_failed=failed_count,
                total_revived=total_revived,
                error_details={"errors": error_details} if error_details else None
            )

        except Exception as e:
            print(f"❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.db:
                self.db.close()

    def _scrape_list_all(self) -> List[Dict[str, str]]:
        """Unified discovery: Combines AJAX, Playwright and standard scrapers."""
        all_items: List[Dict[str, str]] = []
        seen_urls = set()

        def add_items(new_items):
            for item in new_items:
                url = item['url'].split('?')[0].rstrip('/')
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_items.append(item)

        print("   🔍 Discovering Bi'Dünya Fırsat campaigns (AJAX)...")
        add_items(self._scrape_bi_dunya_ajax())
        
        print("   🔍 Discovering Prime campaigns (AJAX)...")
        add_items(self._scrape_prime_ajax())
        
        print("   🔍 Discovering Selfy campaigns (Dynamic)...")
        add_items(self._scrape_selfy_scrolling_safe())
        
        print("   🔍 Discovering Mobil Kampanyalar (Standard)...")
        add_items(self._scrape_mobil_listing())

        print(f"   📋 Discovery found {len(all_items)} campaigns. Merging with verified list...")
        add_items(self._get_hardcoded_verified_list())
        
        return all_items

    def _get_hardcoded_verified_list(self) -> List[Dict[str, str]]:
        """Returns the 95 verified campaigns as a fallback/safety net."""
        return [
            {"title": "D&R: 1.000 TL ve üzeri alışverişlerde 150 TL indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/dr-kampanyasi"},
            {"title": "Dagi: Tüm İndirimlere Ek %10 İndirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/dagi-kampanyasi2"},
            {"title": "idefix: idefix’te 2000 TL ve üzerine 300 TL indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/idefix"},
            {"title": "LC Waikiki Outlet: 1.500 TL’lik harcamanıza 300 TL indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/lc-waikiki-outlet"},
            {"title": "Şirinler Köyü: biletlerinde %25 indirim*!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/sirinler-koyu-kampanyasi"},
            {"title": "Vialand: Tema Park’ta gişe bilet alımlarında %25 indirim", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/vialand"},
            {"title": "E-cerez.com: E-cerez.com’da %20 indirim!*", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/e-cerezcom"},
            {"title": "Evidea: Evidea’da 2.000TL ve üzeri harcamalara 400 TL indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/evidea"},
            {"title": "Elle: Elle’den Yapacağınız Alışverişlerde Tüm İndirimlere Ek %10 İndirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/elle-kampanyasi"},
            {"title": "CarrefourSA: 1.000 TL ve üzeri alışverişlerde 100 CarrefourSA puan hediye!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/carrefoursa-kampanyasi"},
            {"title": "Bilet.com Otobüs Bileti: Bilet.com’da Otobüs Bileti Alımlarında %10 İndirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/biletcom-otobus-bileti-kampanyasi"},
            {"title": "Bilet.com Uçak Bileti: Bilet.com’da İlk Uçak Bileti Alımına Özel 100 TL İndirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/biletcom-ucak-bileti-kampanyasi"},
            {"title": "Yolcu360 Uçak Bileti: Yolcu360’ta uçak biletlerinde 600 TL’ye varan indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/yolcu360-ucak-bileti-kampanyasi"},
            {"title": "Yemeksepeti: Yemeksepeti’nde 275 TL indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/yemeksepeti"},
            {"title": "Çiçeksepeti: Seçili ürünlerde %15 indirim", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/cicek-sepetinden-rozetli-urunlerde-gecerli-15-indirim"},
            {"title": "Madame Coco: 2.500 TL ve üzeri alışverişlerde 250 TL indirim", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/madame-coco-kampanyasi"},
            {"title": "Dürümle: Tüm ürünlerde geçerli % 15 indirim", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/durumle-kampanyasi"},
            {"title": "Sürat Kargo: Sürat Kargo’da %30 indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/surat-kargo-kampanyasi"},
            {"title": "Koçtaş: Koçtaş’ta %10 indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/koctas-kampanyasi"},
            {"title": "D&R Cafe Kahve: D&R Cafe’lerde 1 kahve hediye!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/dr-cafe-kahve-kampanyasi"},
            {"title": "King: King’de seçili ürünlerde %50 indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/king-kampanyasi"},
            {"title": "Petlebi.com: 1.500 TL ve üzeri alışverişlerde 225 TL indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/petlebi-kampanyasi"},
            {"title": "Brillant Store: Brillant.store’da %40 indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/brillant-store"},
            {"title": "TikTak: 750 TL TikTak puan hediye!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/tiktak-ilk-arac-kiralama-kampanyasi"},
            {"title": "Garenta: %40’a varan indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/garenta-kampanyasi"},
            {"title": "Yolcu360 Araç Kiralama: %50 indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/yolcu360-araç-kiralama-kampanyasi"},
            {"title": "Mudo FTS64: %15 indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/mudo-fts64-kampanyasi"},
            {"title": "Enterprise: %30 indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/enterprise-kampanyasi"},
            {"title": "Aras Kargo: %40 indirim!", "url": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat/aras-kargo-kampanyasi"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/turk-telekom-prime-buyuk-cekilis", "title": "Türk Telekom Prime: Büyük Çekiliş"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/dijital-hediye-ceki-kampanyasi", "title": "Dijital Hediye Çeki: Kampanyası"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/prime-a-ozel-dijital-servisler", "title": "Prime: Özel Dijital Servisler"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/mudo", "title": "MUDO: 500 TL indirim ayrıcalığı"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/ataturk-kultur-merkezi", "title": "Atatürk Kültür Merkezi: %50 indirimli bilet"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/mudo-concept", "title": "MUDO CONCEPT: %5 indirim ayrıcalığı"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/migros", "title": "Migros: 200 Money hediye ayrıcalığı"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/galataport-bogaz-turu", "title": "Galataport Boğaz Turu: Ücretsiz boğaz turu"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/biletix", "title": "Biletix: Her çarşamba %50 indirim"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/hediye-sinema-bileti", "title": "Hediye Sinema Bileti: 1 Alana 1 Hediye"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/setur", "title": "Setur: %7 indirim"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/espressolab", "title": "Espressolab: Kahve Kampanyası"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/kahve-konserleri", "title": "Türk Telekom Prime: Kahve Konserleri"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/kocak-baklava", "title": "Koçak Baklava: %10 İndirim!"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/chakra", "title": "Chakra: %10 İndirim!"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/bitaksi", "title": "Bitaksi: 135 TL indirim ayrıcalığı"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/enterprise", "title": "Enterprise: %40 İndirim"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/taze-cicek", "title": "Taze Çiçek: %15 indirim"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/prime-havabus-kampanyasi", "title": "Havabus: Ücretsiz havalimanı transferi"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/ataturk-kultur-merkezi-2gb-hediye-internet", "title": "Atatürk Kültür Merkezi: 2 GB internet hediye"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/autoclub", "title": "AutoClub: 300 TL indirim ayrıcalığı"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/porty", "title": "Porty: 6 saat Powerbank kiralama"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/dry-center", "title": "Dry Center: Kuru temizlemede %50 indirim"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/biletcom", "title": "Bilet.com: 600 TL’ye varan indirim"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/prime-espressolab-online-kampanyasi", "title": "Espressolab Online: %30 indirim"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/prime-royal-canin-kampanyasi", "title": "Royal Canin: %30 indirim"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/prime-sigortamnet-kampanyasi", "title": "Sigortam.net: 750 TL’ye varan indirim"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/prime-ile-evde-internette-tivibu-go-ayricaligi", "title": "Prime: Tivibu GO hediye!"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/sutis-ciftligi-kampanyasi", "title": "Sütis Çiftliği: %20 indirim"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/prime-evde-internet-youtube-premium-kampanyasi", "title": "YouTube Premium: YouTube Premium ayrıcalığı"},
            {"url": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari/youtube-premium", "title": "YouTube Premium: 3 ay ücretsiz"},
            {"url": "https://www.selfy.com.tr/kampanyalar/yemek-sepeti", "title": "Yemeksepeti: 250 TL hediye!"},
            {"url": "https://www.selfy.com.tr/kampanyalar/sinema-kampanyasi", "title": "SİNEMA: 1 ALANA 1 HEDİYE!"},
            {"url": "https://www.selfy.com.tr/kampanyalar/bynogame", "title": "ByNoGame: 250 TL indirim!"},
            {"url": "https://www.selfy.com.tr/kampanyalar/lcw", "title": "LC Waikiki: 200 TL Hediye Çeki!"},
            {"url": "https://www.selfy.com.tr/kampanyalar/sil-supur", "title": "Sil Süpür: 2.Sil Süpür Hediye!"},
            {"url": "https://www.selfy.com.tr/kampanyalar/bilet-com", "title": "Bilet.com: 150 TL indirim!"},
            {"url": "https://www.selfy.com.tr/kampanyalar/yolcu360", "title": "Yolcu360: 650 TL’ye varan indirim!"},
            {"url": "https://www.selfy.com.tr/kampanyalar/tiktak-indirimi", "title": "TikTak: %30 indirim!"},
            {"url": "https://www.selfy.com.tr/kampanyalar/youtube", "title": "YouTube Premium: 3 AY ÜCRETSİZ!"},
            {"url": "https://www.selfy.com.tr/kampanyalar/porty", "title": "Porty: 2 SAAT ÜCRETSİZ!"},
            {"url": "https://www.selfy.com.tr/kampanyalar/tomer", "title": "Tömer: %40 İndirim"},
            {"url": "https://www.selfy.com.tr/kampanyalar/selfylilere-ozel-dijital-servisler", "title": "Dijital Servisler: Muud ve Tivibu hediye"},
            {"title": "Türk Telekom: 5G'ye Hoş Geldin", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/5gye-hos-geldin-kampanyasi"},
            {"title": "Muud & Tivibu: Mobil Ödeme Avantajı", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/muud-ve-tivibu-goda-mobil-odeme-ile-harca-kullanim-bedeli-odeme"},
            {"title": "Türk Telekom: Ebeveyn Kampanyası", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/ebeveyn-kampanyasi"},
            {"title": "Türk Telekom: Okul Destek Derneği 10 GB", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/okul-destek-dernegi-aylik-hediye-10gb-kampanyasi"},
            {"title": "Türk Telekom: TL Yükleme Kampanyası", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/faturasiz-talimatli-tl-yukleme-kampanyasi"},
            {"title": "YouTube: Premium Hediye", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/youtube-ek-paketlerine-youtube-premium"},
            {"title": "Türk Telekom: Sil Süpür", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/sil-supur-kampanyasi"},
            {"title": "Türk Telekom: 1 GB Kazan", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/hediye-internet-gonder-1-gb-kazan-kampanyasi"},
            {"title": "Türk Telekom: 4.5G 20 GB", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/4-5g-20-gb-kampanyasi"},
            {"title": "Türk Telekom: İlk Ay 20-30 GB", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/turk-telekomda-ilk-ay-20-ve-30-gb-hediye-internet-kampanyasi"},
            {"title": "Türk Telekom: Yanımda", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/yanimda-kampanyasi"},
            {"title": "Türk Telekom: Sponsorum Servisi", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/sponsorum-servisi"},
            {"title": "e-dergi: İnternet Bizden", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/e-dergi-kampanyasi"},
            {"title": "Türk Telekom Prime: 3 Ay YouTube Premium", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/turk-telekom-primela-3-ay-boyunca-ucretsiz-youtube-premium"},
            {"title": "Türk Telekom: SMS Fatura 5 GB", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/e-fatura-ve-sms-fatura-hediye-5gb-kampanyasi"},
            {"title": "AFAD: Ücretsiz Erişim", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/afad-acil-cagri-mobil-uygulamasi-kampanyasi"},
            {"title": "Mobile Legends: %20 İndirim", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/mobile-legends-bang-bang-20-indirim-kampanyasi"},
            {"title": "Türk Telekom: 100 DK Hediye", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/wi-fi-aramalarinda-gecerli-100-dk-hediye-kampanyasi"},
            {"title": "Tivibu GO: 3 Ay Ücretsiz", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/tivibu-go-super-paket-3-ay-ucretsiz"},
            {"title": "Türk Telekom: Sil Süpür (Mevcut)", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/sil-supur-kampanyasi-mevcut"},
            {"title": "YouTube: Premium Hediye (Ek)", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/aylik-youtube-ek-paketi-alanlara-ozel-youtube-premium-kampanyasi"},
            {"title": "Türk Telekom: Hoş Geldin 20 GB", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/hos-geldin-20-gb-kampanyasi"},
            {"title": "Türk Telekom: Hoş Geldin 30 GB", "url": "https://bireysel.turktelekom.com.tr/mobil/kampanyalar/hos-geldin-30-gb-kampanyasi"}
        ]

    def _scrape_bi_dunya_ajax(self) -> List[Dict[str, str]]:
        """Scrape Bi'Dünya using robust AJAX requests"""
        items = []
        api_url = f"{self.BASE_URL}/_layouts/15/TTWebsite/Personal/Ajax.aspx/GetCampaign"
        headers = self.headers.copy()
        headers.update({
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://bireysel.turktelekom.com.tr/bi-dunya-firsat"
        })
        
        for page in range(1, 15):
            try:
                payload = {
                    "tariffType": "", "pageNo": page, "pageSize": 12, "category": "",
                    "searchText": "", "webUrl": "/tt-bi-dunya-firsat",
                    "contentType": "Bi Dünya Fırsat Kampanya", "showNewCustomer": False
                }
                resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
                if resp.status_code != 200: break
                
                d = resp.json().get('d', {})
                html = d.get('Html', '') or d.get('Data', '')
                if not html or "Gösterilecek kayıt bulunamadı" in html: break
                
                soup = BeautifulSoup(html, 'html.parser')
                page_count = 0
                for a in soup.find_all('a', href=True):
                    link = urljoin(self.BASE_URL, a['href'])
                    clean_link = link.split('?')[0].rstrip('/')
                    if any(x['url'].rstrip('/') == clean_link for x in items): continue
                    
                    container = a.find_parent(class_=re.compile(r'card|item|category-item'))
                    if not container: container = a.parent.parent
                    
                    brand = container.find(['h3', 'h4', 'h5', 'strong'])
                    desc = container.select_one('.card-desc, .category-desc, p')
                    
                    b_text = brand.get_text(strip=True) if brand else ""
                    d_text = desc.get_text(strip=True) if desc else ""
                    title = f"{b_text}: {d_text}" if b_text and d_text else (d_text or b_text)
                    
                    items.append({"url": clean_link, "title": title})
                    page_count += 1
                
                print(f"      📄 AJAX Page {page}: Found {page_count} items.")
                if not d.get('HasNextPage'): break
                time.sleep(random.uniform(0.5, 1.0))
            except Exception as e:
                print(f"      ❌ AJAX Page {page} Error: {e}")
                break
        return items

    def _scrape_prime_ajax(self) -> List[Dict[str, str]]:
        """Scrape Prime using robust AJAX requests"""
        items = []
        api_url = f"{self.BASE_URL}/_layouts/15/TTWebsite/Personal/Ajax.aspx/GetCampaign"
        headers = self.headers.copy()
        headers.update({
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://bireysel.turktelekom.com.tr/prime/turk-telekom-prime-ayricaliklari"
        })
        
        for page in range(1, 10):
            try:
                payload = {
                    "tariffType": "", "pageNo": page, "pageSize": 12, "category": "",
                    "searchText": "", "webUrl": "/tt-prime",
                    "contentType": "Prime Kampanya", "showNewCustomer": False
                }
                resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
                if resp.status_code != 200: break
                
                d = resp.json().get('d', {})
                html = d.get('Html', '') or d.get('Data', '')
                if not html or "Gösterilecek kayıt bulunamadı" in html: break
                
                soup = BeautifulSoup(html, 'html.parser')
                page_count = 0
                for a in soup.find_all('a', href=True):
                    link = urljoin(self.BASE_URL, a['href'])
                    clean_link = link.split('?')[0].rstrip('/')
                    if any(x['url'].rstrip('/') == clean_link for x in items): continue
                    
                    container = a.find_parent(class_=re.compile(r'card|item|category-item'))
                    if not container: container = a.parent.parent
                    
                    brand = container.find(['h3', 'h4', 'h5', 'strong'])
                    desc = container.select_one('.card-desc, .category-desc, p')
                    
                    b_text = brand.get_text(strip=True) if brand else ""
                    d_text = desc.get_text(strip=True) if desc else ""
                    title = f"{b_text}: {d_text}" if b_text and d_text else (d_text or b_text)
                    
                    items.append({"url": clean_link, "title": title})
                    page_count += 1
                
                print(f"      📄 Prime Page {page}: Found {page_count} items.")
                if not d.get('HasNextPage'): break
                time.sleep(random.uniform(0.5, 1.0))
            except Exception as e:
                print(f"      ❌ Prime AJAX Page {page} Error: {e}")
                break
        return items

    def _scrape_selfy_scrolling_safe(self) -> List[Dict[str, str]]:
        """Scrape Selfy using improved Playwright session management"""
        items = []
        print("      🔄 Opening Playwright for Selfy...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                context = browser.new_context(user_agent=self.headers["User-Agent"])
                page = context.new_page()
                try:
                    page.goto("https://www.selfy.com.tr/kampanyalar", timeout=60000, wait_until="networkidle")
                    page.wait_for_timeout(3000)
                    
                    for i in range(6): # Extra scrolls
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(2000)
                        print(f"         📜 Scroll {i+1}...")
                    
                    content = page.content()
                    soup = BeautifulSoup(content, 'html.parser')
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if "/kampanyalar/" in href and not href.endswith("/kampanyalar"):
                            url = urljoin("https://www.selfy.com.tr", href)
                            clean_url = url.split('?')[0].rstrip('/')
                            if any(x['url'].rstrip('/') == clean_url for x in items): continue
                            
                            container = a.find_parent(class_=re.compile(r'item|card|campaign'))
                            if not container: container = a.parent.parent
                            
                            brand = container.select_one(".item-title, h3, h4")
                            detail = container.select_one(".campaign-detail, .item-text, p")
                            
                            b_text = brand.get_text(strip=True) if brand else ""
                            d_text = detail.get_text(strip=True) if detail else ""
                            title = f"{b_text}: {d_text}" if b_text and d_text else (d_text or b_text)
                            
                            items.append({"url": clean_url, "title": title})
                    print(f"      ✅ Selfy: Found {len(items)} items.")
                finally:
                    page.close()
                    context.close()
                    browser.close()
        except Exception as e: 
            print(f"      ❌ Selfy Playwright Error: {e}")
        return items

    def _scrape_mobil_listing(self) -> List[Dict[str, str]]:
        """Standard mobile campaigns listing"""
        print("   🌐 Loading Mobil Kampanyalar listing...")
        items = []
        try:
            url = "https://bireysel.turktelekom.com.tr/mobil/kampanyalar"
            resp = requests.get(url, headers=self.headers, timeout=30)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            for a in soup.find_all('a', href=True):
                href = a['href']
                if "/mobil/kampanyalar/" in href and not href.endswith("/kampanyalar") and not "?" in href:
                    full_url = urljoin(self.BASE_URL, href)
                    if not any(x['url'] == full_url for x in items):
                        items.append({"url": full_url, "title": a.get_text(strip=True)})
        except Exception as e:
            print(f"      ❌ Mobil Listing Error: {e}")
        return items

    def _scrape_detail(self, url: str, predefined_title: Optional[str] = None) -> bool:
        """Fetch detail page and extract content from accordions"""
        
        # 1. Duplicate Check & Update
        existing = self.db.query(Campaign).filter(Campaign.tracking_url == url).first()
        if existing and existing.is_active:
            # Update title if it's currently much shorter than combined title
            if predefined_title and len(predefined_title) > len(existing.title) + 2:
                if any(x in url for x in ["bi-dunya", "prime", "selfy"]):
                    print(f"      🆙 Updating existing title: {existing.title} -> {predefined_title}")
                    existing.title = predefined_title
            
            self.db.commit()
            print(f"      ⏭️ Skipping (Already exists & active): {existing.title}")
            return "skipped"

        if is_url_blocked(self.db, url):
            print(f"      🚫 Skipping (Blocklisted): {url}")
            return False

        try:
            # Handle Selfy base URL if needed for requests
            active_headers = self.headers.copy()
            if "selfy.com.tr" in url:
                active_headers["Referer"] = "https://www.selfy.com.tr/"

            response = requests.get(url, headers=active_headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 2. Extract Basic Info
            h1 = soup.find("h1")
            brand_name = h1.get_text(strip=True) if h1 else "Türk Telekom"
            
            # 🏷️ TITLE LOGIC:
            # For Partnerships/Prime, we absolutely AVOID the Brand Name (H1) as the Title.
            # Use Predefined Title from listing page if available (as it has the .card-desc)
            title = predefined_title or ""
            
            if not title or title.lower() == brand_name.lower():
                # Look for the first meaningful paragraph text (Prime/Partnerships style)
                # usually .detail-content p, .campaign-spot, .sub-title
                # Priority 1: H1 (The official campaign title)
                h1 = soup.select_one("h1.campaign-detail-title, .campaign-detail-info h1, h1")
                if h1 and len(h1.get_text(strip=True)) > 5:
                    title = h1.get_text(strip=True)
                else:
                    # Fallback 2: Look for the first meaningful paragraph text
                    spot = soup.select_one(".detail-content p, .campaign-spot, .sub-title, .detail-text-img + p")
                    if spot:
                        spot_text = spot.get_text(strip=True)
                        if len(spot_text) > 5 and len(spot_text) < 250:
                            # Ensure we don't just pick something generic
                            if not any(x in spot_text.lower() for x in ["türk telekom", "prime", "selfy"]) or len(spot_text) > 15:
                                title = spot_text
            
            # Final fallback
            if not title:
                title = brand_name

            # Final blocklist check with title
            if is_url_blocked(self.db, url):
                print(f"      🚫 Skipping (Blocklisted): {title}")
                return "skipped"  # type: ignore # pyre-ignore[7]
            
            # Image extraction
            img_tag = soup.select_one(".detail-text-img img")
            image_url = urljoin(self.BASE_URL, img_tag['src']) if img_tag else None
            
            # 3. Extract Accordion and Static Box Content
            content_parts = []
            participation_text = ""
            
            # 3.1 Check for Static Information Box (Important for Participation)
            # This box often contains "Kampanyadan Faydalanmak İçin" outside accordions
            static_boxes = soup.select(".campaign-detail-box, .campaign-detail-info, .tabs-content")
            for box in static_boxes:
                box_text = box.get_text(separator="\n", strip=True)
                if box_text:
                    # If it looks like participation info, prioritize it
                    lower_box = box_text.lower()
                    if any(x in lower_box for x in ["faydalan", "katılım", "nasıl", "şifre"]):
                        participation_text += f"\n[Önemli Talimat]: {box_text}"
                    else:
                        content_parts.append(f"### Bilgi Notu\n{box_text}")

            # Sometimes the headers and contents are direct children of a container
            headers = soup.select(".accordion-header")
            for header in headers:
                header_text = header.get_text(strip=True)
                # The content is usually the next sibling or a sibling with .accordion-content
                content_div = header.find_next_sibling(class_="accordion-content")
                if not content_div:
                    # Alternative structure check
                    parent = header.parent
                    content_div = parent.find(class_="accordion-content")
                
                if content_div:
                    text = content_div.get_text(separator="\n", strip=True)
                    if text:
                        content_parts.append(f"### {header_text}\n{text}")
                        # Categorize for AI context
                        lower_header = header_text.lower()
                        if any(x in lower_header for x in ["katılım", "nasil", "faydalan", "detay"]):  # type: ignore # pyre-ignore[16,6]
                            participation_text += f"\n[{header_text}]: {text}"  # type: ignore # pyre-ignore[58,16,6]

            # og:title for Header Sniper
            og_title_el = soup.find("meta", property="og:title")
            og_title = og_title_el.get("content", "").strip() if og_title_el else title

            # Full body HTML → parse_api_campaign centralised pipeline
            body_el = soup.find("body")
            raw_html = str(body_el) if body_el else response.text

            # AI Parsing
            print(f"      🧠 Sending to AI Parser...")
            ai_data = parse_api_campaign(
                title=title,
                short_description=None,
                content_html=raw_html,
                bank_name="Türk Telekom",
                scraper_sector=None,
                tracking_url=url,
                og_title=og_title
            ) or {}

            if not ai_data or ai_data.get("_ai_failed"):
                print(f"      ❌ AI parsing failed for {url}")
                return "error"  # type: ignore # pyre-ignore[7]

            # Override/Fixes
            if image_url and (not ai_data.get('image_url') or 'logo' in ai_data.get('image_url', '').lower()):
                ai_data['image_url'] = image_url
            
            # Expired Campaign Guard
            end_date_str = ai_data.get("end_date")
            if end_date_str:
                try:
                    from datetime import timedelta
                    end_dt = datetime.fromisoformat(end_date_str) if 'T' in end_date_str else datetime.strptime(end_date_str[:10], "%Y-%m-%d")
                    if end_dt < datetime.now() - timedelta(days=1):
                        print(f"      🕰️ Skipping (Expired date {end_date_str} < Now): {url}")
                        return False
                except Exception as e:
                    pass

            # Save to DB
            return self._save_campaign(ai_data, url, image_url)

        except Exception as e:
            print(f"      ❌ Detail error: {e}")
            return "error"  # type: ignore # pyre-ignore[7]

    def _save_campaign(self, data: Dict[str, Any], url: str, image_url: Optional[str]):  # type: ignore # pyre-ignore[16,6]
        """Save parsed campaign to DB"""
        try:
            # Bank & Card
            bank = self.bank_cache
            card = self._get_or_create_card("Türk Telekom")
            
            # Sector
            sector = self._get_sector(data.get("sector") or "")
            
            # Brands
            brand_ids = self._get_or_create_brands(data.get("brands", []), sector.id if sector else None)  # type: ignore # pyre-ignore[16]
            
            # Slug - always use generate_slug for consistency
            url_hash = uuid.uuid5(uuid.NAMESPACE_URL, url).hex[:8]  # type: ignore # pyre-ignore[16,6]
            base_slug = generate_slug(data.get("title", ""))
            slug = f"{base_slug}-{url_hash}"
            
            ai_marketing_text = data.get("ai_marketing_text") or data.get("description", "")
            participation_text = data.get("participation", "")
                
            campaign = Campaign(
                card_id=card.id,  # type: ignore # pyre-ignore[16]
                sector_id=sector.id if sector else None,  # type: ignore # pyre-ignore[16]
                title=data.get("title"),
                slug=slug,
                description=data.get("description"),
                conditions=data.get("conditions") if not isinstance(data.get("conditions"), list) else "\n".join(data.get("conditions") or []),  # type: ignore # pyre-ignore[16,6]
                reward_text=data.get("reward_text"),
                reward_value=data.get("reward_value"),
                reward_type=data.get("reward_type"),
                start_date=data.get("start_date"),
                end_date=data.get("end_date"),
                image_url=image_url or "https://bireysel.turktelekom.com.tr/assets/img/tt-logo.png",
                tracking_url=url,
                is_active=True,
                ai_marketing_text=ai_marketing_text,
                participation=participation_text,
                eligible_cards=data.get("eligible_cards") or "Türk Telekom Müşterileri",
                category=data.get("category"),
                badge_color=data.get("badge_color"),
                clean_text=data.get("_clean_text"),
                quality_score=data.get("quality_score", 0)
            )
            
            from src.utils.scraper_utils import upsert_campaign
            campaign, op_status = upsert_campaign(self.db, campaign)
            self.db.commit()

            if op_status == "revived":
                print(f"      ♻️  Revived Passive Campaign: {campaign.title[:50]}...")
            elif op_status == "saved":
                 print(f"      ✅ Saved: {campaign.title[:50]}...")
            
            self.db.refresh(campaign)

            for bid in brand_ids:
                existing_link = self.db.query(CampaignBrand).filter_by(campaign_id=campaign.id, brand_id=bid).first()  # type: ignore # pyre-ignore[16]
                if not existing_link:
                    cb = CampaignBrand(campaign_id=campaign.id, brand_id=bid)  # type: ignore # pyre-ignore[16]
                    self.db.add(cb)  # type: ignore # pyre-ignore[16]
            
            self.db.commit()  # type: ignore # pyre-ignore[16]
            return op_status
        except Exception as e:
            self.db.rollback()  # type: ignore # pyre-ignore[16]
            print(f"      ❌ DB Save Error for {url}: {e}")
            return "error"

    # --- HELPERS ---
    def _load_cache(self):
        bank = self.db.query(Bank).filter(Bank.slug == "turk-telekom").first()  # type: ignore # pyre-ignore[16]
        if not bank:
            bank = Bank(name="Türk Telekom", slug="turk-telekom", is_active=True, logo_url="https://upload.wikimedia.org/wikipedia/tr/a/a2/T%C3%BCrk_Telekom_Logo.png")
            self.db.add(bank)  # type: ignore # pyre-ignore[16]
            self.db.commit()  # type: ignore # pyre-ignore[16]
        self.bank_cache = bank
        for c in self.db.query(Card).filter(Card.bank_id == bank.id).all():  # type: ignore # pyre-ignore[16]
            self.card_cache[c.name.lower()] = c
        for s in self.db.query(Sector).all():  # type: ignore # pyre-ignore[16]
            self.sector_cache[s.slug] = s
            self.sector_cache[s.name.lower()] = s
        for b in self.db.query(Brand).filter(Brand.is_active == True).limit(500).all():  # type: ignore # pyre-ignore[16]
            self.brand_cache[b.name.lower()] = b

    def _get_or_create_card(self, name: str) -> Card:
        key = name.lower()
        if key in self.card_cache: return self.card_cache[key]  # type: ignore # pyre-ignore[16,6]
        card = Card(bank_id=self.bank_cache.id, name=name, slug=name.lower().replace(" ", "-"), is_active=True)  # type: ignore # pyre-ignore[16]
        self.db.add(card)  # type: ignore # pyre-ignore[16]
        self.db.flush()  # type: ignore # pyre-ignore[16]
        self.card_cache[key] = card
        return card  # type: ignore # pyre-ignore[7]

    def _get_sector(self, slug: str) -> Optional[Sector]:  # type: ignore # pyre-ignore[16,6]
        if not slug: return None
        return self.sector_cache.get(slug.lower()) or self.sector_cache.get("diğer")  # type: ignore # pyre-ignore[7]

    def _get_or_create_brands(self, names: List[str], sector_id: Optional[int]) -> List[uuid.UUID]:  # type: ignore # pyre-ignore[16,6]
        return get_or_create_brands_list(self.db, names, self.brand_cache, sector_id)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual-json", help="Path to manual discovery JSON file")
    args = parser.parse_args()
    
    scraper = TurkTelekomScraper(manual_json=args.manual_json)
    scraper.run()
