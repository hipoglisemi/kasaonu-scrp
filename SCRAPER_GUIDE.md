# Kartavantaj Scraper Development Guide

Bu kılavuz, sisteme yeni bir banka veya marka scraper'ı (kazıyıcı) eklerken dikkat edilmesi gereken kodlama standartlarını, kural belirlemelerini ve merkezi servis kullanımını açıklar. Kartavantaj sisteminin hızla ölçeklenebilmesi ve veri kirliliğinin (`duplicate` veriler, hatalı kategoriler vb.) önüne geçilebilmesi için tüm yeni scraper'ların bu kılavuzdaki adımlara **kesinlikle uyması** gerekmektedir.

## 1. Temel Mimarisi ve Setup

Her scraper `src/scrapers/base.py` (veya ilgili temel modül) üzerinde yer alan temel sınıflardan veya standart fonksiyonlardan türetilmelidir.

### 1.1 Ortak Bağımlılıklar
- Veritabanı işlemleri için `get_db_session` kullanılmalıdır.
- AI tabanlı ayrıştırma işlemleri için **SADECE** `src.services.ai_parser` kullanılmalıdır. Kendi iç yapınızda ayrı bir prompt yazmayınız.
- Marka (Brand) oluşturma işlemleri için **SADECE** `src.services.brand_matcher` kullanılmalıdır.

## 2. API Öncelikli (API-First) Yaklaşım

Banka kampanyalarını çekerken her zaman önce `API` endpoint'lerini (Gizli JSON dönen ağ istekleri) inceleyin. Sadece ve sadece API yoksa veya eksik veri dönüyorsa `Playwright` veya `Selenium` gibi ağır render gerektiren HTML kazıma yöntemlerine başvurun. API kullanmak, kazıma işlemini 10 kat daha hızlandırır ve yapay zeka maliyetlerini düşürür.

Bkz: `dunyakatilim.py` API yaklaşımı örneği.

## 3. Marka Eşleştirme Sistemi (Zorunlu)

Veritabanında aynı markanın ("Amazon", "Amazon TR", "Amazon.com.tr") birden fazla kez oluşturulmasını önlemek için, markalar her zaman merkezi `brand_matcher` servisi üzerinden kaydedilmelidir.

**❌ YANLIŞ KULLANIM (Eski Yöntem):**
Scraper içinde kendi `_get_or_create_brand` fonksiyonunu yazıp doğrudan veritabanına sorgu atmak.
```python
# KÖTÜ ÖRNEK - YAPMAYIN!
def _get_or_create_brand(self, db, name):
    brand = db.query(Brand).filter(Brand.name == name).first()
    if not brand:
        brand = Brand(name=name, slug=slugify(name))
        db.add(brand)
        db.commit()
    return brand
```

**✅ DOĞRU KULLANIM (Mevcut Standart):**
Merkezi servisi içe aktararak kullanmak. Bu sayede `slug` normalizasyonu ve "Fuzzy (Bulanık) Mantık" araması otomatik yapılır.

```python
# Eğer metinden tek bir marka dönecekse:
from src.services.brand_matcher import get_or_create_brand

# Eğer AI size bir marka listesi dönüyorsa:
from src.services.brand_matcher import get_or_create_brands_list

class BenimBankamScraper:
    def process_campaign(self, ai_data, db):
        # ...
        # AI'dan dönen markaları direkt olarak matcher'a gönderin.
        # Sector ID'yi vermek isabet oranını artırır.
        sector_id = campaign.sector_id 
        brand_ids = get_or_create_brands_list(
            db_session=db,
            brand_names=ai_data.get("brands", []),
            brand_cache=self.brand_cache, # Performans için class seviyesinde tuttuğunuz önbellek sözlüğü
            sector_id=sector_id
        )
        # dönen brand_ids listesi ile CampaignBrand ilişkisini kurun.
        # ...
```

## 4. AI Parser Entegrasyonu

Yeni bir banka eklerken, o bankanın kampanya sayfası yapısı farklı olacağı için AI'ın onu nasıl ayrıştıracağını şaşırmaması gerekir.

### 4.1 Banka Kuralı (BANK_RULES) Eklemek
`src/services/ai_parser.py` dosyasına girerek en üstteki `BANK_RULES` sözlüğüne (dictionary) yeni bankanız için spesifik talimatlar ekleyin.

```python
BANK_RULES = {
    # Eski kurallar...
    "benim bankam": "- Bu banka SMS katılma işlemine her zaman 'KAZAN yaz 1234'e gönder' der. Eğer SMS kodu sadece 1234 görünüyorsa kelimenin KAZAN olduğunu varsay.\n- Uygun kartlar listesinde asla 'Business Kartlar' kelimesini dahil etme vs."
}
```

### 4.2 Parse Fonksiyonu
Veriyi ayrıştırmak için:
```python
from src.services.ai_parser import parse_api_campaign

ai_data = parse_api_campaign(
    title=raw_title,
    short_description=raw_short_desc,
    content_html=raw_html_content,
    bank_name="Benim Bankam", # AI'ın BANK_RULES içindeki promptu tetiklemesi için
    scraper_sector=orjinal_sektor_ismi, # AI'ın kendi 18 kategorisine eşleştirebilmesi için ipucu
    tracking_url=campaign_url
)

if ai_data.get("_ai_failed"):
    # Hata yönetimi. Kaydetme veya logla.
```

## 6. Admin Panel - Test Scraper İş Akışı (Önemli!)

Admin panelinde yer alan **Test Scraper** menüsü, scraper'ların sunucuda (server-side) çalıştırılmasını ve test edilmesini sağlayan özel bir entegrasyondur. Bu menüyü ve entegrasyonu kodlarken veya yeni bir scraper bağlarken şu `Workflow (İş Akışı)` adımlarına dikkat edilmelidir:

### 6.1 DB Kontrolü (Öncelik)
Bir URL veya kampanya scrape edilmeden önce **mutlaka** veritabanı (DB) kontrolü yapılmalıdır. Eğer o kampanyanın URL'si (`tracking_url` veya benzersiz belirteci) zaten veritabanında aktif olarak varsa, scraper gereksiz yere hedef siteye ve Gemini AI'a istek **atmamalıdır**.

### 6.2 Blocklist (Kara Liste) Kontrolü
Veritabanı kontrolünden sonra, hedef URL'nin sistemin "Blocklist" tablosunda olup olmadığı kontrol edilmelidir. Kasten engellenmiş, hatalı, veya çekilmesi istenmeyen bir URL ise, scraper işlemi daha başlamadan, API isteği veya Playwright motoru hiç tetiklenmeden `return` (veya `continue`) ile atlanmalıdır.

### 6.3 API İsteği ve AI Ayrıştırması
Eğer kampanya DB'de yoksa ve Blocklist'te de değilse ancak o zaman kampanya sayfasına istek atılmalı (HTML indirme) ve `src.services.ai_parser` kullanılarak veriler anlamlandırılmalıdır.

**Admin Panel Çalışma Prensibi:**
Test Scraper menüsü tetiklendiğinde sistem genellikle `--limit 5` veya benzeri test parametreleriyle scraper'ı sınırlandırır. Bu sayede sonsuz döngü veya aşırı limit dolumunun önüne geçilir. Scraper'ınızın bu `--limit` veya `test_mode` parametrelerini doğru okuyup, hedeflediği sayıyı geçmeden durduğundan emin olun.

Özetle, yeni scraper'lar temiz, modüler ve AI/Marka merkezi servislerine tam bağlı olarak çalışmalıdır. Açıkta kalan bir özel mantık ("custom logic") bırakmayın.

