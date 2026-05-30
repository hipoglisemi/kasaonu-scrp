"""
Kirli clean_text'e sahip Crystal/Adios/Play kampanyalarını
yeniden scrape eden script. Sadece detail page'i Playwright ile çeker,
text_cleaner ile temizler, ai_parser_golden ile parse eder.
"""
import sys, os, time

# Add project root to python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from playwright.sync_api import sync_playwright
from src.database import get_db
from src.models import Campaign
from src.services.text_cleaner import clean_campaign_text
from src.services.ai_parser_golden import AIParserGolden

# Yeniden scrape edilecek kampanyalar: id → url
DIRTY_CAMPAIGNS = {
    9171:  "https://www.yapikrediplay.com.tr/kampanyalar/yapi-kredi-play-ile-world-cinezone-sinema-bufelerinde-yapacagin-yeme-icme-harcamalarinda-15-2026",
    9181:  "https://www.yapikrediplay.com.tr/kampanyalar/toplamda-15000-tlye-varan-worldpuan-odullu-vadaa-sans-hafta-ici-her-aksam-2000de",
    8682:  "https://www.adioscard.com.tr/kampanyalar/adios-premium-ile-uslada-gerceklesecek-workshoplarda-10-indirim",
    8607:  "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-raffles-istanbulda-15-indirim-and-spada-20-indirim-firsati",
    14913: "https://www.adioscard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-yurt-disi-restoran-ve-kafe-odemelerinde-15-indirim-2025",
    8866:  "https://www.crystalcard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-raffles-istanbulda-15-indirim-and-spada-20-indirim-ayricaligi",
    8955:  "https://www.crystalcard.com.tr/kampanyalar/crystal-ile-uslada-gerceklesecek-workshoplarda-20-indirim-ayricaligi",
    8907:  "https://www.crystalcard.com.tr/kampanyalar/crystal-ile-les-bungalowsta-konaklama-harcamalarinda-5-indirim-ayricaligi",
    8938:  "https://www.crystalcard.com.tr/kampanyalar/crystal-ile-swissotel-uludagda-konaklama-harcamalarinda-10-indirim-ayricaligi",
    14951: "https://www.crystalcard.com.tr/kampanyalar/silver-logolu-mastercardiniza-ozel-yurt-disi-restoran-ve-kafe-odemelerinde-15-indirim-2025",
}

# Banka adı tespiti (URL'den)
def get_bank_name(url):
    if "crystalcard" in url:
        return "yapı kredi"
    elif "adioscard" in url:
        return "yapı kredi"
    elif "yapikrediplay" in url:
        return "yapı kredi"
    return "yapı kredi"

def scrape_detail_page(playwright, url):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
        html = page.content()
        return html
    except Exception as e:
        print(f"  Sayfa yüklenemedi: {e}")
        return None
    finally:
        browser.close()

def main():
    db = next(get_db())
    parser = AIParserGolden()
    updated = 0
    failed = 0

    with sync_playwright() as playwright:
        for camp_id, url in DIRTY_CAMPAIGNS.items():
            c = db.query(Campaign).filter(Campaign.id == camp_id).first()
            if not c:
                print(f"#{camp_id} DB'de bulunamadı — atlanıyor")
                continue

            print(f"\n{'='*60}")
            print(f"#{camp_id} | {c.title[:55]}")
            print(f"  URL: {url}")

            html = scrape_detail_page(playwright, url)
            if not html:
                print(f"  ❌ HTML alınamadı")
                failed += 1
                continue

            # GoldenParser: HTML → clean_text + eligible_cards
            bank_name = "Yapı Kredi"
            try:
                result = parser.parse_campaign(
                    raw_html=html,
                    bank_name=bank_name,
                    title=c.title or "",
                )
                new_clean_text = result.get("clean_text") or clean_campaign_text(html)
                new_eligible = result.get("eligible_cards", "")

                # Kirlilik kontrolü
                dirt_markers = ["crystal nedir", "adios nedir", "play kredi kartı başvuru",
                                "crystal ek kart", "ara crystal dünyası", "yapı kredi concierge"]
                still_dirty = [m for m in dirt_markers if m in new_clean_text.lower()]

                if still_dirty:
                    print(f"  ⚠️  Hâlâ kirli: {still_dirty[0]!r}")
                else:
                    print(f"  ✅ Temiz metin ({len(new_clean_text)} karakter)")

                print(f"  Metin önizleme: {new_clean_text[:250]}")
                print(f"\n  Eski eligible_cards: {c.eligible_cards}")
                print(f"  Yeni eligible_cards: {new_eligible}")

                c.clean_text = new_clean_text
                c.eligible_cards = new_eligible
                updated += 1

            except Exception as e:
                print(f"  ❌ Parse hatası: {e}")
                failed += 1

            time.sleep(1.5)

    db.commit()
    print(f"\n{'='*60}")
    print(f"✅ Tamamlandı: {updated} güncellendi, {failed} başarısız")

if __name__ == "__main__":
    main()
