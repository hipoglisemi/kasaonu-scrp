import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import get_db_session
from sqlalchemy import text

gspara_seo = """# GSPara Kredi Kartı ve Banka Kartı Kampanyaları & Avantajları Rehberi

**GSPara**, Galatasaray taraftarlarına ve masrafsız dijital finans ayrıcalıklarından yararlanmak isteyen kullanıcılara özel olarak **QNB** altyapısı ile sunulan yenilikçi bir dijital bankacılık ve kart platformudur. GSPara Kredi Kartı ve GSPara Banka Kartı sahipleri, hem günlük finansal harcamalarında kazançlı çıkar hem de Galatasaray spor kulübünün sunduğu özel tribün ve camia avantajlarına doğrudan erişim sağlar.

## GSPara Kredi Kartı Öne Çıkan Avantajları

* **Öncelikli Maç Bileti Alım Hakkı:** Galatasaray'ın RAMS Park stadyumundaki ev sahibi olduğu derbiler ve lig maçlarında GSPara kart sahiplerine özel öncelikli bilet satın alma fırsatı tanımlanır.
* **GSStore Harcamalarında ParaPuan & GSPlus Ödülleri:** Resmi GSStore mağazaları ile gsstore.org üzerinden yapılan tüm taraftar ürünü alımlarında yüksek oranlı ParaPuan kazanılır ve GSPlus sistemi üzerinden özel kulüp hediyeleri toplanır.
* **%0 Faizli Taksitli Avans ve Hoş Geldin Kredisi:** Yeni GSPara müşterilerine özel faizsiz masrafsız nakit avans ve avantajlı taksitli nakit ihtiyaç çözümleri sunulur.
* **Tamamen Ücretsiz FAST, EFT ve Havale:** Günün 24 saati gerçekleşen tüm para transferlerinde herhangi bir işlem ücreti veya transfer masrafı ödenmez.
* **Yıllık Kart Aidatı Yok:** GSPara Kredi Kartı ilk yıl aidatsız olarak sunulur ve avantajlarla dolu kullanım olanağı sağlar.
* **İlk Alışverişe Özel 750 TL ParaPuan:** Kart açılışını takip eden ilk harcamada anında kullanılabilir ParaPuan hediye edilir.

## GSPara Başvurusu ve Kullanım Kolaylıkları

GSPara hesabı ve kart başvurusu tamamıyla dijital olarak cep telefonu üzerinden birkaç dakika içinde tamamlanır. Kurye bekleme derdi olmadan dijital kart anında online alışverişlere açılır ve temassız ödeme, mobil cüzdan entegrasyonu ile hemen kullanılabilir.

## Sıkça Sorulan Sorular

**GSPara hangi bankanın altyapısını kullanır?**  
GSPara, QNB Bank A.Ş. güvencesi ve finansal altyapısı ile hizmet veren lisanslı bir dijital bankacılık platformudur.

**Maç biletlerinde öncelik hakkı nasıl kullanılır?**  
Galatasaray bilet satışları duyurulduğunda GSPara kart sahipleri Passolig sistemine kart bilgilerini tanımlayarak genel satış öncesinde bilet alabilirler.

**GSPara kart ücretli midir?**  
GSPara Kredi Kartı ve Banka Kartı ilk yıl ücretsizdir ve EFT/FAST işlemlerinden hiçbir işlem ücreti alınmaz."""

fenerpara_seo = """# Fenerpara Kredi Kartı ve Banka Kartı Kampanyaları & Avantajları Rehberi

**Fenerpara**, Fenerbahçe taraftarlarına ve avantajlı dijital finans müşterilerine özel olarak **QNB** altyapısı ile sunulan sarı-lacivert konseptli finansal kart ve dijital bankacılık platformudur. Fenerpara Kredi Kartı ve Fenerpara Banka Kartı kullanıcıları, taraftarlara özel tribün avantajlarından dijital platform ödeme iadelerine kadar pek çok fırsattan yararlanır.

## Fenerpara Kredi Kartı Öne Çıkan Avantajları

* **Öncelikli Maç Bileti Satış Fırsatı:** Fenerbahçe'nin Ülker Stadyumu'nda oynayacağı maç biletlerinde Fenerpara kart sahiplerine duyurulan tarih ve saatten itibaren 24 saatlik öncelikli bilet alma hakkı verilir.
* **Dijital Platformlarda %50 İade:** Netflix, Spotify, YouTube Premium ve seçili dijital platform ödemelerinde her ay %50 nakit ve ParaPuan iadesi kazanılır.
* **E-Ticaret Devlerinde Peşin Fiyatına Taksit:** Trendyol, Hepsiburada ve Amazon alımlarında peşin fiyatına 3 taksit yapma imkanı sağlanır.
* **Sarı Lacivert Bankacılık ile %0 Faizli Kredi:** Yeni Fenerpara müşterilerine özel %0 faizli nakit avans ve bütçe dostu kredi imkanları sunulur.
* **7/24 Masrafsız Bankacılık:** Tüm EFT, FAST ve Havale işlemlerinde hiçbir masraf veya komisyon ödenmez.
* **İlk Harcamaya Özel 750 TL ParaPuan:** Fenerpara Kredi Kartı ile yapılan ilk alışverişe özel 750 TL tutarında ParaPuan hediye edilir.
* **İlk Yıl Kart Ücreti Yok:** Yıllık kart aidatı ödemeden avantajlarla dolu kullanım imkanı sunulur.

## Fenerpara Başvurusu ve Kullanım Kolaylıkları

Fenerpara hesabı ve kart başvurusu mobil uygulama üzerinden dakikalar içinde gerçekleştirilir. Dijital kart anında aktif hale gelerek internet alışverişlerinde ve temassız ödemelerde güvenle kullanılabilir.

## Sıkça Sorulan Sorular

**Fenerpara hangi bankanın altyapısını kullanmaktadır?**  
Fenerpara, QNB Bank A.Ş. altyapısını ve güvencesini kullanan dijital bir bankacılık hizmetidir.

**Öncelikli bilet hakkı kaç saat geçerlidir?**  
Fenerbahçe tarafından açıklanan tarihten itibaren 24 saat boyunca bilet alma önceliği Fenerpara kart sahiplerine aittir.

**Fenerpara kart aidatı var mıdır?**  
Fenerpara kart ilk yıl aidatsızdır ve para transferlerinde işlem ücreti alınmaz."""

def main():
    print(f"GSPara text character count: {len(gspara_seo)} chars")
    print(f"Fenerpara text character count: {len(fenerpara_seo)} chars")

    with get_db_session() as db:
        # GSPara (card_id = 192)
        db.execute(text("""
            INSERT INTO card_details (card_id, seo_summary, who_is_it_for, annual_fee, card_type, created_at, updated_at)
            VALUES (192, :g_seo, :g_who, 'Ücretsiz (İlk Yıl)', 'credit', NOW(), NOW())
            ON CONFLICT (card_id) DO UPDATE SET
                seo_summary = EXCLUDED.seo_summary,
                who_is_it_for = EXCLUDED.who_is_it_for,
                updated_at = NOW()
        """), {
            "g_seo": gspara_seo,
            "g_who": "Galatasaray taraftarları, maç biletlerinde öncelik arayanlar ve masrafsız dijital bankacılık kullanıcıları.",
        })

        # Fenerpara (card_id = 193)
        db.execute(text("""
            INSERT INTO card_details (card_id, seo_summary, who_is_it_for, annual_fee, card_type, created_at, updated_at)
            VALUES (193, :f_seo, :f_who, 'Ücretsiz (İlk Yıl)', 'credit', NOW(), NOW())
            ON CONFLICT (card_id) DO UPDATE SET
                seo_summary = EXCLUDED.seo_summary,
                who_is_it_for = EXCLUDED.who_is_it_for,
                updated_at = NOW()
        """), {
            "f_seo": fenerpara_seo,
            "f_who": "Fenerbahçe taraftarları, maç biletlerinde öncelik arayanlar, dijital platform aboneleri ve e-ticaret kullanıcıları.",
        })

        db.commit()
        print("Updated CardDetail SEO texts successfully!")

if __name__ == "__main__":
    main()
