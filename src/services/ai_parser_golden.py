"""
AI Parser Service - GOLDEN STANDARD V3 🏆
Model-independent parser with Python-enforced business logic.
Prompt = short & literal extraction only.
Guards = Python post-processing (Card, Brand, Sector, Date).
"""
import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from src.database import SessionLocal  # type: ignore
from src.models import Brand, CampaignBrand, Sector  # type: ignore
from .text_cleaner import clean_campaign_text  # type: ignore
from .point_blank_matcher import get_point_blank_matcher, _STATIC_BRAND_EXCLUSIONS  # type: ignore
from .card_validator import CardValidator # type: ignore
from .negation_filter import NEGATION_KEYWORDS  # type: ignore

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BANK TERMINOLOGY DICTIONARY (Post-Processing, NOT in prompt)
#  Used to VALIDATE AI output, not to instruct the AI.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BANK_CARD_KEYWORDS = {
    "akbank": ["axess", "wings", "free", "akbank kart", "bank’o card axess", "bank'o card", "ticari kartlar", "ticari", "ek kartlar", "sanal kartlar"],
    "işbankası": ["maximum", "maximiles", "privia"],
    "yapı kredi": ["worldcard", "world", "play", "adios", "crystal", "bireysel kredi kartları", "banka kartları", "tlcard", "vakıfbank worldcard", "albaraka worldcard", "anadolubank worldcard", "opet worldcard", "vakıfbank", "albaraka", "anadolubank"],
    "ziraat": ["bankkart", "bankkart başak", "bankkart genç", "bankkart prestij", "bankkart business"],
    "vakıfbank": ["worldcard", "world", "express card"],
    "halkbank": ["paraf", "parafly", "paraf business", "parafree", "paraf esnaf", "paraf kobi", "eczacı paraf", "eczacı paraf kobi", "halkcard", "paraf genç", "paraf gençiz", "sanal kartlar", "ek kartlar"],
    "denizbank": ["denizbonus", "net kart", "denizbank bonus"],
    "qnb": ["qnb card", "qnb troy"],
    "teb": ["teb bonus", "cepteteb"],
    "kuveyt türk": ["sağlam kart"],
    "türkiye finans": ["happy card", "âlâ kart", "happy zero"],
    "enpara": ["enpara.com kredi kartı", "enpara kredi kartı"],
    "hsbc": ["hsbc premier"],
    "şekerbank": ["şekerbank bonus", "şekerbank diamond"],
    "burgan": ["on kredi kartı", "on banka kartı"],
    "albaraka": ["albaraka worldcard"],
    "türk telekom": ["türk telekom müşterileri", "prime", "selfy"],
    "turkcell": ["turkcell müşterileri", "paycell kart"],
    "vodafone": ["vodafone müşterileri", "vodafone kullanıcıları", "vodafone red", "vodafone freezone"],
    "chippin": ["chippin"],
    "param": ["paramkart"],
    "paycell": ["paycell kart", "faturana yansıt", "mobil ödeme"],
    "tami": ["tami kart"],
    "uption": ["uption kart"],
    "masterpass": ["masterpass"],
    "opet": ["opet kart", "opet mobil", "opet müşterileri"],
    "nays": ["nays kart", "nays kullanıcıları"],
    "dünya katılım": ["dünya katılım kartı", "dünya katılım banka kartı", "dünya katılım kredi kartı", "dkart", "dkart debit", "dünya katılım paraf", "dünya katılım troy"],
}

BANK_APP_NAMES = {
    "akbank": "Jüzdan",
    "işbankası": "İşCep / Maximum Mobil",
    "yapı kredi": "World Mobil",
    "garanti": "BonusFlaş",
    "ziraat": "Bankkart Mobil",
    "vakıfbank": "Cepte Kazan / VakıfBank Mobil",
    "halkbank": "Paraf Mobil / Halkbank Mobil",
    "denizbank": "MobilDeniz / DenizKartım",
    "qnb": "QNB Mobil",
    "teb": "TEB Mobil / CEPTETEB",
    "kuveyt türk": "Kuveyt Türk Mobil",
    "türkiye finans": "Mobil Şube",
    "türk telekom": "Türk Telekom Online İşlemler",
    "turkcell": "Turkcell Pasaj / Paycell",
    "vodafone": "Vodafone Yanımda",
}

BANK_SMS_NUMBERS = {
    "akbank": "4566",
    "işbankası": "4402",
    "yapı kredi": "4454",
    "halkbank": "3404",
    "denizbank": "3280",
    "ziraat": "4757",
    "kuveyt türk": "2044",
    "türkiye finans": "2442",
    "teb": "5350",
    "şekerbank": "1953",
    "hsbc": "4477",
    "türk telekom": "6262",
}

# Self-tagging prevention: bank names that should NEVER appear in brands
BANK_SELF_NAMES = {
    "akbank": ["akbank", "axess", "wings", "free", "chip-para"],
    "işbankası": ["iş bankası", "türkiye iş bankası", "işbank", "maximum", "maximiles"],
    "yapı kredi": ["yapı kredi", "world", "worldcard"],
    "garanti": ["garanti", "garanti bbva", "bonus", "bonusflaş", "miles&smiles", "shop&fly"],
    "ziraat": ["ziraat", "ziraat bankası", "bankkart"],
    "vakıfbank": ["vakıfbank", "vakıf bank"],
    "halkbank": ["halkbank", "halk bankası", "paraf"],
    "denizbank": ["denizbank", "deniz bank"],
    "qnb": ["qnb", "qnb finansbank", "finansbank"],
    "teb": ["teb", "türk ekonomi bankası"],
    "american express": ["american express card", "american express gold card", "american express platinum card", "metal the platinum card", "centurion card", "centurion"],
    "kuveyt türk": ["kuveyt türk"],
    "türkiye finans": ["türkiye finans"],
    "türk telekom": ["türk telekom", "turk telekom", "tivibu", "selfy", "prime"],
    "turkcell": ["turkcell"],
    "vodafone": ["vodafone", "vodafone red"],
    "enpara": ["enpara"],
    "hsbc": ["hsbc"],
    "şekerbank": ["şekerbank", "şeker bank"],
    "burgan": ["burgan", "burgan bank"],
    "albaraka": ["albaraka"],
    "opet": ["opet", "opet kart", "yakıt puan", "opet kampanyası", "opet mobil"],
    "nays": ["nays", "nays kart"],
    "dünya katılım": ["dünya katılım", "dunya katilim", "dunya katılım", "dünya katilim"],
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AUTHORITATIVE SECTOR SLUGS (from DB)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALID_SECTOR_SLUGS = [
    "kitap-kirtasiye-ofis", "fatura-telekomunikasyon", "diger",
    "hizmet-bireysel-gelisim", "giyim-aksesuar", "restoran-kafe",
    "e-ticaret", "ulasim", "egitim", "sigorta", "turizm-konaklama",
    "finans-yatirim", "market-gida", "elektronik", "akaryakit",
    "mobilya-dekorasyon", "kozmetik-saglik", "dijital-platform",
    "otomotiv", "vergi-kamu", "mucevherat-optik-saat", "kultur-sanat-spor",
    "anne-bebek-oyuncak", "evcil-hayvan-petshop",
]

# Legacy slug → correct slug mapping
SECTOR_SLUG_FIXES = {
    "kultur-sanat": "kultur-sanat-spor",
    "kuyum-optik-ve-saat": "mucevherat-optik-saat",
}

# Condition boilerplate patterns to remove
CONDITION_BOILERPLATE = [
    "kampanyayı durdurma hakkı", "yasal mevzuat",
    "tüm hakları saklıdır", "bddk kuralları", "yasal düzenleme",
    "kampanya koşullarına uygun olmayan", "harcama itirazı durumunda",
    "ödüller nakde çevrilemez", "zamanaşımına uğrayan",
    "kullanılmayan puanlar geri alınacaktır",
]

# Passthrough card terms (generic categories that are always valid)
CARD_PASSTHROUGH_TERMS = {
    "tüm kartlar", "tüm kredi kartları", "tüm banka kartları", "tüm müşteriler",
    "sanal ve ek kartlar", "sanal kartlar", "ek kartlar", "asıl ve ek kartlar", "asıl kartlar",
    "türk telekom müşterileri", "vodafone müşterileri", "turkcell müşterileri",
    "bireysel müşteriler", "faturalı müşteriler", "ticari kartlar", "paracard",
    "centurion card", "centurion", "metal the platinum card",
}

# Point/reward system names that are NOT cards (AI often confuses these)
CARD_EXCLUSION_TERMS = {
    "worldpuan", "maxipuan", "chip-para", "chippuan", "chip puan",
    "parafpara", "paraf para", "bonus puan", "bonuspuan",
    "mil", "miles", "nakitpuan", "nakit puan",
    "altın puan", "altınpuan", "parapuan",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class AIParserGolden:
    """
    Golden Standard V3 Parser.
    
    Architecture:
    1. text_cleaner → Clean raw HTML
    2. PBE → Pre-scan for known brands (DB-verified)
    3. Short Prompt → AI extracts literal data
    4. Python Guards → Validate & enrich AI output
       - Card Guard (core word + sniper)
       - Brand Guard (title/illusion/negative)
       - Sector Guard (slug normalization)
       - Date Guard (today/month-end fallback)
       - Condition Guard (boilerplate removal, max 8)
       - Bank Terminology Guard (app/SMS validation)
    """

    def __init__(self, model_client=None):
        self.model_client = model_client
        self.db = SessionLocal()
        self.matcher = get_point_blank_matcher(self.db)
        self.card_validator = CardValidator(BANK_CARD_KEYWORDS)
        self.valid_sectors = VALID_SECTOR_SLUGS

    # ── TURKISH HELPERS ──────────────────────────────────────────────
    @staticmethod
    def _tr_lower(text: str) -> str:
        if not text:
            return ""
        tr_map = {ord('I'): 'ı', ord('İ'): 'i', ord('Ş'): 'ş', ord('Ğ'): 'ğ',
                  ord('Ç'): 'ç', ord('Ö'): 'ö', ord('Ü'): 'ü'}
        return text.translate(tr_map).lower()

    @staticmethod
    def _normalize(s: str) -> str:
        """Normalize spaces, ampersands and Turkish characters for comparison."""
        s = s.lower().replace("\xa0", " ").replace("&", " & ").replace("  ", " ")
        s = s.replace('ı', 'i').replace('ş', 's').replace('ğ', 'g')
        s = s.replace('ü', 'u').replace('ö', 'o').replace('ç', 'c')
        # Handle common bank typos
        s = s.replace('worlcard', 'worldcard')
        return s.strip()

    # ── SAFE TYPE CONVERTERS ─────────────────────────────────────────
    @staticmethod
    def _safe_date(value) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', value):
            return value
        return None

    @staticmethod
    def _safe_decimal(value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_clean_list(val) -> list:
        if not val:
            return []
        bullet_pattern = re.compile(r'^[\s\-_•*\\.]+ *')
        if isinstance(val, list):
            cleaned = []
            for x in val:
                if x and str(x).strip():
                    item = bullet_pattern.sub('', str(x).strip()).strip()
                    if item:
                        cleaned.append(item)
            return cleaned
        cleaned = str(val).strip()
        if cleaned:
            cleaned = bullet_pattern.sub('', cleaned).strip()
        return [cleaned] if cleaned else []

    @staticmethod
    def _to_clean_string(val, separator: str = "\n") -> str:
        if not val:
            return ""
        if isinstance(val, list):
            items = [str(x).strip() for x in val if x]
            return separator.join(items) if len(items) > 1 else (items[0] if items else "")
        return str(val).strip()

    # ── PROMPT (SHORT & MODEL-INDEPENDENT) ───────────────────────────
    def _get_golden_prompt(self, cleaned_text: str, bank_name: str = "", pb_matches: list = None, title: str = "", og_title: str = None) -> str:
        current_date = datetime.now().strftime("%Y-%m-%d")
        bank_info = f" ({bank_name})" if bank_name else ""

        # 1. PBE INSTRUCTIONS
        pb_hint = ""
        if pb_matches:
            brand_names = [m["brand"] for m in pb_matches if m.get("brand")]
            pb_hint = f"""
🔒 POINT-BLANK (POTANSİYEL MARKA ADAYLARI):
- METİNDE GEÇEN MARKALAR: {', '.join(brand_names)}

1. 🧠 ANALİZ ET: Yukarıdaki markalar gerçek bir kampanya ORTAĞI mı (örn: Trendyol, Migros) yoksa sadece alt yapı/katılım kanalı mı (örn: Tivibu, Online İşlemler)?
2. 🛡️ FİLTRELE: Sadece gerçek partnerleri 'brands' listesine ekle. Bankanın veya kurumun kendi servislerini partner olarak YAZMA.
   - Kampanya SMS adımlarında gecen GSM operatörlerini (Türk Telekom, Turkcell, Vodafone) ASLA marka olarak secme.
3. 🚨 **AMAZON AYRIMI (KRİTİK)**: Metin genel bir alışveriş veya kargo kampanyasıysa sektörü 'e-ticaret' seç. SADECE 'Amazon Prime' üyeliği, aboneliği veya Prime Video/Müzik ödemesi ise 'dijital-platform' seç.
4. 🚨 **SEKTÖR HİYERARŞİSİ (ÇOK KRİTİK)**:
   - Eğer kampanya belirli bir dikey sektöre (Giyim, Elektronik, Kitap, Kozmetik, Akaryakıt, Turizm vb.) ait uzman bir markada ise (örn: Altınyıldız, Teknosa, İdefix, Gratis, ETS Tur), işlem web sitesinden/mobil uygulamadan yapılsa dahi sektörü o **DİKEY SEKTÖR** (Giyim, Elektronik vb.) olarak belirle.
   - 'e-ticaret' sektörü SADECE çok kategorili "Pazar Yerleri" (Marketplace) içindir: Trendyol, Hepsiburada, Amazon (Shopping), Pazarama, Çiçeksepeti, n11.
   - Bir marka hem dikey bir uzmanlığa sahipse hem de internetten satılıyorsa, dikey uzmanlık (Giyim, Elektronik vb.) HER ZAMAN kazanır.
5. ⛔ NEGATİF BAĞLAM (HARİÇTİR): Metinde bu markaların 10-60 kelime yakınında 'hariçtir', 'dahil değildir', 'kapsam dışıdır' yazıyorsa (Örn: Bim, Şok, A101 hariç), O MARKALARI KESİNLİKLE 'brands' LİSTESİNE ALMA.
6. 🛡️ **SIFIR ÇIKARIM (ZERO INFERENCE)**: Kendi iç bilgini kullanarak marka TAHMİN ETME. Eğer marka ismi başlıkta veya metinde karakter karakter yazmıyorsa, o marka senin için yoktur. Marka adı uydurmak KESİNLİKLE YASAKTIR.

"""

        # GENERIC_TITLE_WORDS: kelime çıkarımı için sabit set (regex yok)
        GENERIC_TITLE_WORDS = {
            "kampanya", "kampanyası", "fırsat", "fırsatlar", "fırsatı",
            "ayrıcalık", "ayrıcalıklar", "ayrıcalıkları", "özel",
            "detay", "detaylar", "duyuru", "duyurusu", "bilgilendirme",
            "akaryakıt", "standartları"
        }
        title_instruction = ""

        # Öncelik 1: og_title — H1 veya meta tag'den gelen başlık her zaman güvenilir
        if og_title and og_title.strip():
            title_instruction = f'🔒 BAŞLIK KİLİDİ (H1/META): "{og_title.strip()}"'
        elif title and title.strip() and title.strip() != "Başlık Yok":
            title_instruction = f'🔒 BAŞLIK KİLİDİ: "{title.strip()}"'

        # 3. BANK SPECIFIC RULES
        bank_instructions = ""
        if bank_name:
            try:
                from .bank_rules import BANK_RULES
                bank_name_lower = bank_name.lower()
                for bank_key, rules in BANK_RULES.items():
                    if bank_key in bank_name_lower:
                        bank_instructions = rules
                        break
            except Exception as e:
                logger.error(f"Failed to load bank rules: {e}")

        return f"""
Sen uzman bir kampanya veri analistisin. Aşağıdaki metni analiz et ve KESİN JSON formatında çıktı ver.
Bugünün tarihi: {current_date}
Kampanya Sahibi Banka/Kurum: {bank_name}

{bank_instructions}
{title_instruction}
{pb_hint}

⭐ ALTIN STANDART KURALLARI ⭐

1. **MARKA GÜVENLİĞİ**:
   - 🛡️ SADECE metinde açıkça partner/ortağı olarak geçen markayı al.
   - ⛔ UYGULAMA YASAĞI: Kampanyanın kendisi dijital market harcamalarına yönelik DEĞİLSE (sadece "uygulamamızı App Store/Google Play'den indirin" yazıyorsa), 'App Store', 'Google Play', 'Apple' gibi kelimeleri ASLA marka yapma. Ancak kampanya özel olarak "App Store Harcamalarına İndirim" ise bunları ekleyebilirsin.
   - ⛔ UYDURMA YASAĞI: Kampanya sahibi bankayı{bank_info}, kart programlarını (World, Bonus, Axess, vb.) veya cüzdan uygulamasını (Juzdan vb.) ASLA marka olarak yazma.
   - ⛔ PUBLIC/GOVERNMENT TRAP: "SGK", "GİB", "Gelir İdaresi", "Duty Free", "Belediye", "Vergi" gibi devlet veya genel şemsiye kurumları marka DEĞİLDİR. ASLA ekleme.
   - 🛡️ Sayfanın altındaki "İlginizi çekebilen diğer kampanyalar" yan markalarını ASLA ekleme.

2. **SEKTÖR**: Aşağıdaki slug listesinden birini seç:
   {self.valid_sectors}
   - Markanın dikey uzmanlığı (Giyim, Elektronik) HER ZAMAN satış kanalından (e-ticaret) önce gelir.
   - 'e-ticaret' SADECE çok kategorili pazar yerleri (Trendyol, Hepsiburada, Amazon) içindir.
   - 🚨 ÖDEME YÖNTEMİ VS ÜRÜN AYRIMI (ÇOK ÖNEMLİ): Eğer metinde "Faturana Yansıt", "Hopi", "Masterpass" geçiyorsa, sektörü 'fatura-telekom' veya 'finans-yatirim' SEÇME. Ödeme yöntemi kampanya sektörünü değiştirmez. Harcamanın YAPILDIĞI YERE odaklan.

3. **KARTLAR ve KATILIM**: 
   - 🚨 **ÖDÜL ÖNCELİKLENDİRME (KRİTİK)**: Metinde birden fazla ödül varsa (örn: hem Mil Puan hem Taksit), BAŞLIKTAKİ ödülü ana ödül olarak kabul et. `reward_text`, `reward_value`, `reward_type` ve `cards` alanlarını SADECE BU ANA ÖDÜL için doldur. İkinci ödülü (taksit vb.) ve onun şartlarını 'conditions' kısmında belirt.
   - 🚨 **KART SEÇİMİ (KRİTİK)**: Eğer metinde bir kart grubu ana ödül için "dahil değildir" (excluded) olarak belirtilmişse, ancak metnin başka bir yerinde (örn: taksit kampanyası için) "dahildir" deniyorsa, o kartı `cards` listesine EKLEME. `cards` listesi sadece ana ödül için TAM YETKİLİ kartları içermelidir.
   - Metinde geçen kart isimlerini metindeki ORİJİNAL SIRASINI BOZMADAN aynen listele (marka içi sıralama).
   - 🚨 PARTNER BANKALAR (CRITICAL): Eğer metinde "Anadolu Bank", "Albaraka", "Vakıfbank" veya "Worldcard lisanslı bankalar" geçiyorsa, MUTLAKA 'cards' alanına KURTARARAK ekle.
   - ⛔ YASAK: Eğer metinde geçerli kart/müşteri adı (örn: 'Opet Kart', 'Türk Telekom müşterileri') geçmiyorsa ASLA uydurarak ekleme. Yoksa boş bırak `[-]`.

4. **TARİHLER**: 
    - Tüm tarihleri 'YYYY-MM-DD' formatında ver.
    - 🚨 YIL KURALI: Eğer yıl belirtilmemişse:
      * Bugünün tarihi: {current_date}
      * Kampanya ayı < Bugünün ayı → Sonraki yıl olarak al.
      * Kampanya ayı >= Bugünün ayı → İçinde bulunduğumuz yıl olarak al.
    - Sadece bitiş tarihi varsa, başlangıç tarihi olarak bugünü ({current_date}) al.
    - 🚨 BULUNAMAYAN TARİH KURALI: Eğer metinde başlangıç veya bitiş tarihi AÇIKÇA BELİRTİLMEMİŞSE (veya süresiz vb. ise), o alanı KESİNLİKLE null olarak bırak. Asla bugünün tarihini tahmini olarak yazma. Uydurma tarih üretmek veya mevcut günün tarihini ezbere eklemek YASAKTIR.

5. **KOŞULLAR**: 
    - En fazla 10 madde.
    - 🚨 İKİNCİL ÖDÜLLER: Ana ödülden farklı olan taksit, ek fayda vb. durumları ve onlara özel geçerli kartları burada belirt (Örn: "Peşin fiyatına 6 taksit fırsatından Axess kartlar da yararlanabilir").
    - 🚨 GEÇERLİ OLDUĞU YERLER (ZORUNLU): Kampanyanın dahil olduğu/geçerli olduğu mağaza, marka, platform veya web siteleri metinde geçiyorsa, bunu EKSİKSİZ VE KESİN OLARAK maddelerden biri yap (Örn: "Kampanya sadece www.ornek.com ve X mağazalarında geçerlidir").
    - 🚨 İSTİSNALAR VE HARİÇ OLANLAR (KRİTİK): Kampanya kapsamında **geçerli OLMAYAN** markalar, ürün grupları, mağazalar veya kart tipleri metinde belirtilmişse (Örn: "Tütün harcamaları dahil değildir", "X mağazaları hariçtir", "Ticari kartlar geçerli değildir"), bunları MUTLAKA 'conditions' listesine madde olarak ekle. Kullanıcı neyin kapsam dışı olduğunu bilmeli.
    - 🚨 MAĞAZA/POS KURALI: Eğer 'sadece X Bankası POS cihazlarından geçen işlemler' gibi fiziksel/altyapı şartları varsa, bunu DİREKT OLARAK maddelerden biri yap.
    - 🚨 ULTRA KRİTİK - YASAK: Tarih, Geçerli Kartlar ve Katılım adımlarını 'conditions' içerisine KESİNLİKLE YAZMA (Tepede zaten var). Sadece harcama alt sınırı, POS şartları, ödül limitleri gibi işlemsel koşulları özetle.
    - 🚨 JURIDICAL BOILERPLATE REMOVAL (ULTRA STRICT): Aşağıdaki jenerik hukuki metinleri KESİNLİKLE SİL, ASLA MADDE OLARAK YAZMA:
      * "Taksit sayısı ürün gruplarına göre yasal mevzuat çerçevesinde belirlenir."
      * "Bireysel kredi kartlarıyla.. BDDK kuralları gereği..."
      * "Yasal mevzuat gereği azami taksit sayısı..."
      * "Kampanya farklı kampanyalarla birleştirilemez."
    - Sıkıcı hukuki detayları silebilirsin, odak sadece müşteri kazancı.

6. **PAZARLAMA**: 2-3 cümle, emojili, enerjik. Somut rakamları belirt. Metin SEO dostu olmalı; kampanyanın avantajını kullanıcıya coşkulu bir dille sun.

JSON FORMATI:
{{
  "title": "Metnin en üstündeki doğal ve spesifik başlığı bul. Aksi kanıtlanmadıkça 'Opet Kampanyası' gibi sonradan atanmış jenerik/sıkıcı başlık isimlerini GÖRMEZDEN GEL, sadece asıl içeriği yansıtan resmî başlığı (Örn: Çek Kazan Superfresh Fırsatı) kullan.",
  "description": "2 cümlelik samimi özet",
  "ai_marketing_text": "2-3 cümlelik enerjik, emojili pazarlama metni. Somut rakamları belirt. Metin SEO dostu olmalı.",
  "reward_value": 0.0,
  "reward_type": "puan/indirim/taksit/mil",
  "reward_text": "Kısa ve Çarpıcı. Peşin fiyatına gibi detayları yazma. Örn: '150 TL Yakıt Puan' veya '%20 İndirim'",
  "min_spend": 0.0,
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "sector": "sektor-slug",
  "brands": ["Marka1", "Marka2"], // ⛔ NEGATION TRAP: Metinde 'hariçtir','dahil değildir', 'geçerli değildir', 'kapsam dışıdır' gibi kelimelerin 10-15 kelime yakınında geçen markaları (Örn: Migros, Şok, A101 hariç) KESİNLİKLE LİSTEYE EKLEME.
  "cards": ["Ana ödül için (başlıktaki ödül) %100 geçerli olan kart isimlerini metindeki orijinal sırasıyla listele. Örn: 'Garanti Bonus', 'Ek kartlar'. Eğer bir kart ana ödül için hariç tutulmuşsa buraya EKLEME."],
  "participation": "Kampanyadan nasıl faydalanılacağını net bir dille özetle. Şirket/uygulama mağazası isimlerini at, doğrudan eylemi yaz. Açıkça 'Katıl' butonu/SMS'i YOKSA BİLE, kampanyadan yararlanmak için yapılması gereken ödeme sırası işlemlerini (örn: 'Ödemenizi ilgili banka POS cihazından yapın', 'İnternet sitesinde taksit seçeneğini işaretleyin', 'Kasada şifreyi söyleyin') BURAYA YAZ. Örn: 'İşCep'ten Katıl butonuna tıklayın.', 'Kasada kampanyadan yararlanmak istediğinizi belirtin.', 'Ödemeyi bankamız POS'undan yapın.', 'Faturanızı uygulamadan okutun.' Eğer metinde hiçbir ön katılım şartı (SMS/Buton) veya eylem cümlesi geçmiyorsa, eksi (-) yazmak YERİNE: 'Otomatik Katılım' yaz.",
  "conditions": ["Önemli Şart 1", "İkincil ödül (örn: taksit) varsa ve farklı kartlar için geçerliyse mutlaka belirt.", "Önemli Şart 2"]
}}

ANALİZ EDİLECEK METİN:
{cleaned_text}
"""

    # ── MAIN PARSE FLOW ──────────────────────────────────────────────
    def parse_campaign(self, raw_html: str, bank_name: str = "", title: str = "", og_title: str = None, structured_cards_text: str = None, scraper_sector: str = None) -> Dict[str, Any]:
        """Golden Standard V3 parse flow."""
        # 1. Clean text (og_title/title enables header trimming for SPA sites)
        cleaned_text = clean_campaign_text(raw_html, og_title=og_title, title=title)

        # 2. PBE Pre-scan (find known brands before AI call)
        pb_brands = []
        pb_matches = []
        try:
            db = SessionLocal()
            matcher = get_point_blank_matcher(db)
            exclude_list = [bank_name] if bank_name else []
            pb_matches = matcher.match_campaign(title or "", cleaned_text, exclude_terms=exclude_list)
            
            # 🛡️ HOST PROTECTION (Sector Priority)
            # If we have multiple matches and one of them is a "Host" (Shell, Opet, Chippin, etc.),
            # and another is a "Guest" (Partner brand), prioritizing the guest for sector.
            if pb_matches and len(pb_matches) > 1:
                host_slugs = {'turk-telekom', 'vodafone', 'turkcell', 'shell', 'opet', 'petrol-ofisi', 'totalenergies', 'dijital-platform'}
                guest_matches = [m for m in pb_matches if m.get('sector') not in ['fatura-telekomunikasyon', 'akaryakit', 'dijital-platform']]
                if guest_matches:
                    # Move guest matches to front to dictate dominant sector
                    pb_matches = guest_matches + [m for m in pb_matches if m not in guest_matches]

            pb_brands = [m["brand"] for m in pb_matches if m.get("brand")]
            db.close()
        except Exception as e:
            logger.warning(f"PBE scan failed: {e}")

        # 3. AI Call
        if not self.model_client:
            raise ValueError("Model client not provided")

        prompt = self._get_golden_prompt(cleaned_text, bank_name, pb_matches, title, og_title)
        ai_response = self.model_client.generate_content(prompt)
        parsed_data = self._extract_json(ai_response)

        # 4. Apply ALL Python Guards
        result = self._apply_business_logic(parsed_data, cleaned_text, bank_name, title, pb_matches, scraper_sector=scraper_sector)

        # ── 5. REPORT CANDIDATES BACK TO PBE ──
        # If AI found a validated brand that isn't in PBE yet, report it for admin approval.
        try:
            db = SessionLocal()
            matcher = get_point_blank_matcher(db)
            existing_pb_brands = set(pb_brands)
            
            validated_brands = result.get("brands", [])
            for b in validated_brands:
                if b and b != "Genel" and b not in existing_pb_brands:
                    # Only report if it's NOT already in our point-blank list for this campaign
                    # Use the determined sector for the new candidate
                    matcher.report_new_candidate(b, b, result.get("sector", "diger"), campaign_id=None)
            db.close()
        except Exception as e:
            logger.warning(f"Failed to report PBE candidates: {e}")

        # Inject clean text for downstream consumers
        result["_clean_text"] = cleaned_text
        return result

    # ── JSON EXTRACTOR ───────────────────────────────────────────────
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Robust JSON extractor with bracket counting."""
        try:
            start = text.find('{')
            if start == -1:
                return json.loads(text)

            depth = 0
            in_string = False
            escape_next = False
            end = start

            for i in range(start, len(text)):
                c = text[i]
                if escape_next:
                    escape_next = False
                    continue
                if c == '\\' and in_string:
                    escape_next = True
                    continue
                if c == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break

            return json.loads(text[start:end + 1])
        except Exception as e:
            logger.error(f"JSON Parsing failed: {e}")
            return {}

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  THE HARD GUARD: All Python-enforced business logic
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _apply_business_logic(self, data: Dict[str, Any], raw_text: str,
                               bank_name: str = "", title: str = "",
                               pb_matches: list = None, scraper_sector: str = None) -> Dict[str, Any]:
        today = datetime.now()
        raw_text_lower = self._tr_lower(raw_text)
        title_lower = self._tr_lower(title or "")
        bank_key = self._resolve_bank_key(bank_name)

        # ── 1. DATE GUARD ────────────────────────────────────────────
        parsed_start = self._safe_date(data.get("start_date"))
        parsed_end = self._safe_date(data.get("end_date"))

        if not parsed_start and not parsed_end:
            parsed_start = today.strftime("%Y-%m-%d")
            next_month = today.replace(day=28) + timedelta(days=4)
            parsed_end = (next_month - timedelta(days=next_month.day)).strftime("%Y-%m-%d")
        elif not parsed_start and parsed_end:
            parsed_start = today.strftime("%Y-%m-%d")
        elif parsed_start and not parsed_end:
            try:
                start_dt = datetime.strptime(parsed_start, "%Y-%m-%d")
                next_m = start_dt.replace(day=28) + timedelta(days=4)
                parsed_end = (next_m - timedelta(days=next_m.day)).strftime("%Y-%m-%d")
            except:
                next_month = today.replace(day=28) + timedelta(days=4)
                parsed_end = (next_month - timedelta(days=next_month.day)).strftime("%Y-%m-%d")

        data["start_date"] = parsed_start
        data["end_date"] = parsed_end

        # ── 2. SECTOR GUARD ──────────────────────────────────────────
        sector = data.get("sector", "diger")
        if isinstance(sector, list):
            sector = sector[0] if sector else "diger"
        
        # Priority 1: Scraper Override (Highest trust)
        if scraper_sector and scraper_sector != "diger":
            sector = scraper_sector
        # Priority 2: PBE sector override (High trust)
        elif pb_matches:
            pb_sectors = [
                m.get("sector") for m in pb_matches 
                if m.get("sector") and m.get("sector") != "diger"
                and (m.get("brand") or m.get("title_match") is True)
            ]
            if pb_sectors:
                pbe_sector = SECTOR_SLUG_FIXES.get(pb_sectors[0], pb_sectors[0])
                if pbe_sector in self.valid_sectors and pbe_sector != "diger":
                    sector = pbe_sector
        
        # Priority 3: Final normalization of AI suggestion
        sector = SECTOR_SLUG_FIXES.get(sector, sector)
        if sector not in self.valid_sectors:
            sector = self._determine_sector(sector, title, raw_text)
            
        data["sector"] = sector

        # ── 3. CARD GUARD (Core Word Matching + Sniper) ──────────────
        # 3. KART DOĞRULAMA (Hallucination Guard)
        cards = self._to_clean_list(data.get("cards"))
        if cards:
            cards = self.card_validator.validate(cards, raw_text, bank_key)
        
        # Final armored safety pass: ensure the filtered list is what actually goes into the data
        from src.services.negation_filter import filter_excluded_cards
        final_cards = filter_excluded_cards(cards, raw_text, bank_name=bank_name)
            
        data["cards"] = final_cards if final_cards else []
        print(f"   🛡️ ARMORED CHECK: Final cards in data are {data['cards']}")

        # ── 4. BRAND GUARD (Title / Illusion / Negative Context) ─────
        brands = data.get("brands", [])
        if not isinstance(brands, list):
            brands = [brands] if brands else []
        # Collect PBE-verified brand names (these bypass text-verification)
        pbe_brand_names = set()
        if pb_matches:
            for m in pb_matches:
                if m.get("brand"):
                    pbe_brand_names.add(m["brand"])
                    if m["brand"] not in brands:
                        brands.append(m["brand"])
        brands = self._validate_brands(brands, raw_text_lower, title_lower, bank_key, pbe_trusted=pbe_brand_names)
        data["brands"] = brands

        # ── 5. CONDITION GUARD ───────────────────────────────────────
        conditions = self._to_clean_list(data.get("conditions"))
        conditions = [c for c in conditions
                      if not any(bp in c.lower() for bp in CONDITION_BOILERPLATE)]
        data["conditions"] = conditions[:10]

        # ── 6. REWARD GUARD ──────────────────────────────────────────
        data["reward_value"] = self._safe_decimal(data.get("reward_value")) or 0.0

        # ── 7. PARTICIPATION GUARD ───────────────────────────────────
        participation = self._to_clean_string(data.get("participation"))
        data["participation"] = participation

        # ── 8. TITLE NORMALIZE & PREFIX GUARD ────────────────────────
        raw_title = data.get("title") or title or "Kampanya"
        
        # Hard strip known prefixes that banks inject to og:title like "Shop&Fly - ", "Garanti BBVA - "
        prefixes_to_strip = [
            "Shop&Fly", "Garanti Bonus", "Garanti BBVA", "Maximum", "Maximiles", 
            "Axess", "Wings", "Worldcard", "World", "Ziraat Bankkart", "Paraf",
            "CardFinans", "QNB", "Türkiye Finans", "Kuveyt Türk"
        ]
        
        for prefix in prefixes_to_strip:
            # Matches "Shop&Fly - " or "Shop&Fly | " or "Shop&Fly: "
            pattern = rf"^(?i)\s*{re.escape(prefix)}\s*[\-\|\:]\s*(.*)$"
            match = re.match(pattern, raw_title)
            if match:
                raw_title = match.group(1).strip()
                break # stripped the main prefix
        
        data["title"] = raw_title
        data["description"] = data.get("description") or ""
        data["ai_marketing_text"] = data.get("ai_marketing_text") or ""
        data["reward_type"] = data.get("reward_type")
        data["reward_text"] = data.get("reward_text") or "Kampanya Fırsatı"
        data["min_spend"] = self._safe_decimal(data.get("min_spend")) or 0.0

        # ── 9. FINAL PRETTIFIER (Capitalization) ────────────────────
        p = data.get("participation")
        if p and p != "-":
            data["participation"] = p[0].upper() + p[1:]
            
        if data.get("cards"):
            data["cards"] = [c[0].upper() + c[1:] if c else c for c in data["cards"]]

        return data

    # ── BANK KEY RESOLVER ────────────────────────────────────────────
    @staticmethod
    def _resolve_bank_key(bank_name: str) -> str:
        """Resolve bank name to dictionary key. Handles Turkish chars and spacing."""
        if not bank_name:
            return ""
        # Must replace Turkish İ/I BEFORE .lower() — Python's lower() turns İ→i̇ (with combining dot)
        bn = bank_name.replace("İ", "i").replace("I", "ı").lower()
        # ASCII-folded version for fuzzy matching
        def _ascii_fold(s):
            return s.replace(" ", "").replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")
        bn_folded = _ascii_fold(bn)
        for key in BANK_CARD_KEYWORDS:
            key_folded = _ascii_fold(key)
            if key in bn or key_folded in bn_folded:
                return key
        return ""

    # ── BRAND VALIDATION (from old parser, improved) ─────────────────
    def _validate_brands(self, brands: list, text_lower: str, title_lower: str, bank_key: str, pbe_trusted: set = None) -> list:
        """
        Brand Hallucination Guard V3:
        1. Self-tagging prevention (bank/card names as brands)
        2. Blocklist check (payment networks etc.)
        3. PBE Bypass (database-verified brands skip text checks)
        4. Title Guard (brands in title are always safe)
        5. Illusion Guard (sidebar/footer brands)
        6. Negative Context Guard ("dahil değildir" nearby)
        7. Common Noun Guard
        """
        if not brands:
            return []
        if pbe_trusted is None:
            pbe_trusted = set()

        # Load dynamic blocklist
        blocklist = set(_STATIC_BRAND_EXCLUSIONS)
        try:
            db = SessionLocal()
            from .point_blank_matcher import get_point_blank_matcher
            matcher = get_point_blank_matcher(db)
            blocklist = matcher.blocklist
            db.close()
        except:
            pass
            
        # Hardcoded App Store Trap Guard
        app_store_traps = {"apple", "google", "google play", "play store", "app store", "huawei", "appgallery", "huawei appgallery", "gallery store"}
        blocklist = blocklist.union(app_store_traps)

        # Self-tag names for this bank
        self_names = set()
        if bank_key and bank_key in BANK_SELF_NAMES:
            self_names = {self._tr_lower(n) for n in BANK_SELF_NAMES[bank_key]}

        # Strip symbols for title matching
        def _strip_symbols(t):
            return re.sub(r"[^a-z0-9ıişğüç ]", " ", t)

        title_plain = _strip_symbols(title_lower)

        # Noise markers for illusion detection
        noise_markers = [
            r"ilginizi çekebilecek diğer kampanyalar",
            r"benzer fırsatlar", r"benzer kampanyalar",
            r"diğer kampanyalar", r"sizin için seçtiklerimiz",
        ]

        common_nouns = {"bilet", "lastik", "sigorta", "market", "puan", "bakkal",
                        "indirim", "taksit", "faiz", "kredi"}

        full_context = text_lower + " " + title_lower
        validated = []

        for brand in brands:
            if not brand or len(brand) < 2:
                continue
            brand_norm = self._tr_lower(brand)
            brand_plain = _strip_symbols(brand_norm)

            # 1. SELF-TAGGING CHECK (applies to ALL brands, including PBE)
            is_trap = any(trap in brand_norm for trap in app_store_traps)
            is_in_title = brand_plain and brand_plain in title_plain
            if brand_norm in self_names or brand in blocklist or (is_trap and not is_in_title):
                logger.debug(f"Brand Guard: Rejected self-tag/blocklist/trap '{brand}'")
                continue

            # 2. TITLE GUARD — brands in title are always safe
            if brand_plain in title_plain:
                validated.append(brand)
                continue

            # 3. ILLUSION GUARD — only found after "benzer kampanyalar" etc.
            is_illusion = False
            for marker_pat in noise_markers:
                match = re.search(marker_pat, full_context, re.IGNORECASE)
                if match:
                    marker_pos = match.start()
                    brand_pat = rf"(?i)\b{re.escape(brand_norm)}\b"
                    found_before = re.search(brand_pat, full_context[:marker_pos])
                    found_after = re.search(brand_pat, full_context[marker_pos:])
                    if found_after and not found_before and brand_norm not in title_plain:
                        is_illusion = True
                        break
            if is_illusion:
                logger.debug(f"Brand Guard: Rejected illusion '{brand}'")
                continue

            # 4. NEGATIVE CONTEXT GUARD
            # Scans ALL occurrences of brand in text + sentence-level "hariç" detection
            def _is_negated(brand_n: str, context: str, neg_kws: list, title_p: str, is_pbe: bool = False) -> bool:
                if brand_n in title_p:
                    return False
                # Check every occurrence (handles "Bim, ..., Migros hariç" long lists)
                start = 0
                while True:
                    idx = context.find(brand_n, start)
                    if idx == -1:
                        break
                    
                    # Sentence-level: find the sentence containing the brand
                    # 🛡️ PBE PRIORITY: For trusted brands, sentence check is MUCH more reliable than broad window
                    sent_start = max(0, context.rfind(".", 0, idx) + 1)
                    sent_end = context.find(".", idx + len(brand_n))
                    if sent_end == -1:
                        sent_end = len(context)
                    sentence = context[sent_start:sent_end].lower()
                    
                    if any(neg in sentence for neg in neg_kws):
                        return True
                        
                    # Broad window check (300-char) - ONLY for non-PBE brands to catch fuzzy negations
                    # or if the sentence check missed something obvious.
                    if not is_pbe:
                        window = context[max(0, idx - 300): idx + len(brand_n) + 300].lower()
                        if any(neg in window for neg in neg_kws):
                            # Final guard: if negation is in window but NOT in sentence, 
                            # and sentence is positive ("dahildir", "geçerlidir"), trust sentence.
                            positive_kws = ["dahildir", "gecerlidir", "altindadir", "kapsamindadir"]
                            if any(pos in sentence for pos in positive_kws):
                                pass # Trust the positive sentence
                            else:
                                return True
                    
                    start = idx + 1
                return False

            if brand_norm in full_context:
                is_pbe_trusted = brand in pbe_trusted
                if _is_negated(brand_norm, full_context, NEGATION_KEYWORDS, title_plain, is_pbe=is_pbe_trusted):
                    logger.debug(f"Brand Guard: Rejected negative context '{brand}'")
                    continue
            
            # 5. COMMON NOUN GUARD (runs BEFORE PBE bypass — common nouns are NEVER valid brands)
            # "bilet", "sigorta", "market" etc. should never be tagged even if PBE has a rule for them,
            # UNLESS the brand name is explicitly in the title (e.g. title = "Bilete.com Kampanyası").
            is_generic = any(cn in brand_norm for cn in common_nouns)
            if is_generic and brand_norm not in title_lower:
                logger.debug(f"Brand Guard: Rejected common noun (pre-PBE) '{brand}'")
                continue

            # 6. GSM OPERATOR GUARD (SMS Channel Protection)
            # Prevents operators from being tagged as brands when they only appear as SMS channels.
            # Using both original and normalized variants to be 100% safe.
            gsm_operators = {
                "türk telekom", "türktelekom", "turk telekom", "turktelekom",
                "vodafone", "turkcell"
            }
            if brand_norm in gsm_operators:
                if brand_norm not in title_lower:
                    # logger.debug(f"Brand Guard: Rejected GSM operator '{brand}' (SMS channel suspected)")
                    continue

            # 7. PBE BYPASS — database-verified brands skip the remaining heuristic text checks
            if brand in pbe_trusted:
                validated.append(brand)
                continue

            if brand_norm in full_context:
                validated.append(brand)
            else:
                # Brand not found in text at all — hallucination
                logger.debug(f"Brand Guard: Rejected hallucination '{brand}' (not in text)")

        return validated

    # ── STATIC HELPERS ───────────────────────────────────────────────
    @staticmethod
    def _get_last_day_of_month(date_obj: datetime) -> datetime:
        import calendar
        last_day = calendar.monthrange(date_obj.year, date_obj.month)[1]
        return date_obj.replace(day=last_day)

    # ── DB CACHE ─────────────────────────────────────────────────────
    @staticmethod
    def _check_db_cache(tracking_url: str) -> Optional[Dict[str, Any]]:
        """Check database if this URL was already parsed successfully."""
        try:
            from src.database import SessionLocal as _SL  # type: ignore
            from src.models import Campaign, Sector  # type: ignore
            db = _SL()
            try:
                existing = db.query(Campaign).filter(
                    Campaign.tracking_url == tracking_url,
                    Campaign.description.isnot(None),
                    Campaign.reward_text.isnot(None)
                ).first()
                if existing:
                    # ♻️ UNIVERSAL REVIVAL/PENDING FIX: If campaign is passive OR pending approval, 
                    # force a fresh parse to apply the latest extraction logic (ordering, noise filters, etc.)
                    if not existing.is_active or not existing.is_approved:
                        return None
                        
                    sector_name = "Diğer"
                    if existing.sector_id:
                        sec = db.query(Sector).filter(Sector.id == existing.sector_id).first()
                        if sec:
                            sector_name = sec.name
                    return {
                        "title": existing.title,
                        "description": existing.description,
                        "reward_text": existing.reward_text,
                        "reward_value": float(existing.reward_value) if existing.reward_value else None,
                        "reward_type": existing.reward_type,
                        "conditions": existing.conditions.split("\n") if existing.conditions else [],
                        "cards": existing.eligible_cards.split(", ") if existing.eligible_cards else [],
                        "participation": existing.participation or "",
                        "start_date": existing.start_date.strftime("%Y-%m-%d") if existing.start_date else None,
                        "end_date": existing.end_date.strftime("%Y-%m-%d") if existing.end_date else None,
                        "sector": sector_name,
                        "brands": [],
                        "_cached": True,
                        "_clean_text": existing.description or ""
                    }
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
        return None

    # ── COMPATIBILITY: parse_campaign_data (eski AIParser imzası) ────
    def parse_campaign_data(
        self,
        raw_text: str,
        title: Optional[str] = None,
        bank_name: Optional[str] = None,
        card_name: Optional[str] = None,
        tracking_url: Optional[str] = None,
        force: bool = False,
        campaign_id: Optional[int] = None,
        og_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Backward-compatible wrapper. Same signature as old AIParser.parse_campaign_data().
        Routes directly to parse_campaign() with DB cache support.
        """
        if tracking_url and not force:
            cached = self._check_db_cache(tracking_url)
            if cached:
                safe_url = str(tracking_url)
                print(f"   ✨ Using cached AI data for: {safe_url[:60]}...")
                return cached

        return self.parse_campaign(raw_html=raw_text, bank_name=bank_name or "", title=title or "", og_title=og_title)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MODULE-LEVEL FACTORY & STANDALONE FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _create_default_client():
    """Create a Gemini model client using the standard rotation system."""
    from google.genai import types as _types  # type: ignore
    from src.utils.gemini_client import generate_with_rotation  # type: ignore
    import signal

    class TimeoutException(Exception):
        pass

    def timeout_handler(signum, frame):
        raise TimeoutException("Gemini API call timed out")

    _model = os.getenv("GEMINI_MODEL", "models/gemini-3.1-flash-lite-preview")

    class _GeminiClient:
        def __init__(self):
            self.model = _model

        def generate_content(self, prompt):
            import time
            time.sleep(1.0)  # Rate-limit protection
            config = _types.GenerateContentConfig(
                temperature=0.0, top_p=0.1, top_k=1,
                response_mime_type="application/json",
                max_output_tokens=6000
            )
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(65)
            try:
                res = generate_with_rotation(prompt, model=self.model, config=config)
                return str(res) if res else "{}"
            except TimeoutException:
                logger.error("Gemini API call timed out (65s)")
                return "{}"
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

    return _GeminiClient()


# Singleton instance
_parser_instance: Optional[AIParserGolden] = None


def get_golden_parser(client=None) -> AIParserGolden:
    """Get or create singleton Golden Parser instance."""
    global _parser_instance
    if _parser_instance is None:
        if client is None:
            client = _create_default_client()
        _parser_instance = AIParserGolden(client)
    return _parser_instance


def parse_api_campaign(
    title: str,
    short_description: str,
    content_html: str,
    bank_name: Optional[str] = None,
    scraper_sector: Optional[str] = None,
    tracking_url: Optional[str] = None,
    force: bool = False,
    og_title: Optional[str] = None,
    structured_cards_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    API-First Lightweight Parser (used by Garanti, Akbank, Yapı Kredi, QNB, etc.).
    Now routes through Golden Parser for consistent processing.
    """
    parser = get_golden_parser()

    # 1. Check Cache
    if tracking_url and not force:
        cached = parser._check_db_cache(tracking_url)
        if cached:
            print(f"   ✨ [API] Using cached AI data for: {str(tracking_url)[:60]}...")
            return cached

    # 2. Clean HTML content — AUTOFIX-PARITY STRATEGY
    # This mirrors what data_quality_autofix.py does: remove structural noise
    # from the DOM (nav/footer/header) BEFORE converting to text.
    # The old regex-only approach left all these tags as plain text → AI confusion.
    from bs4 import BeautifulSoup as _BS

    content_html = content_html or ''

    # 2a. Parse DOM and surgically remove noise tags
    _soup = _BS(content_html, 'html.parser')
    for _tag in _soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
        _tag.decompose()

    # 2b. GENEL gürültü selector'ları — tüm bankalar için
    _noise_selectors = [
        '.other-campaigns', '.featured-campaigns', '.similar-campaigns',
        '.campaign-recommendations', 'section.news-carousel',
        '#related-campaigns', '.campaignDetail-others',
        '.related-campaigns', '.other-campaign-list',
        '[class*="sidebar"]', '[class*="footer"]', '[class*="header"]',
        '[class*="navigation"]', '[id*="navigation"]',
    ]

    # 2b-extra. BANKA-ÖZEL ek gürültü selector'ları
    # Her bankanın sayfasındaki banka-özgü gürültüler buraya eklenir.
    # Yeni bir banka eklendiğinde sadece burası güncellenir, scraper'a dokunulmaz.
    _bank_noise_map = {
        "akbank":        ['.headerContent', '.logoBox', '.verisign', '.push',
                          '.campaignOtherCampaigns', '.footer-banner', '.listing-box'],
        "axess":         ['.headerContent', '.logoBox', '.verisign', '.push',
                          '.campaignOtherCampaigns', '.footer-banner', '.listing-box'],
        "garanti":       ['.header-v2', '.footer-v2', '.nav-v2', '.sidebar-v2',
                          '.online-islemler'],
        "garanti bbva":  ['.header-v2', '.footer-v2', '.nav-v2', '.sidebar-v2',
                          '.online-islemler'],
        "qnb":           ['.Header-navigation-top', '.Header-navigation-main',
                          '.Header-navigation-bottom', '.Header-navigation-mobil'],
        "teb":           ['#headerUp', '#headerDown', '#headerMain',
                          '#headerSrc', '#headerLoginPanelNew'],
        "ziraat bankası": ['.subpage-breadcrumb', '.subpage-sidebar',
                            '.subpage-related', '.other-content'],
        "vakıfbank":     ['.otherCampaigns', '.similarCampaigns', '.footer-campaign'],
        "yapı kredi":    ['.yk-header', '.yk-footer', '.banner-area',
                          '.related-campaigns-wrapper'],
        "işbankası":     ['.other-links', '.menu-wrapper', '.sticky-cta'],
        "maximum":       ['.other-links', '.menu-wrapper', '.sticky-cta'],
        "maximiles":     ['.other-links', '.menu-wrapper', '.sticky-cta'],
        "burgan bank":   ['.on-asistan', '.footer-navigation', '.bottom-footer'],
        "türk telekom":  ['.featured-privileges', '.other-campaigns', '.footer-main'],
        "dunyakatilim":  ['.header', '.footer', '.similar-campaigns', '.related-posts'],
        "vodafone":      ['.header', '.footer', '.sidebar', '.related-campaigns', '.bottom-bar'],
    }
    _bank_key = (bank_name or "").lower()
    for _key, _selectors in _bank_noise_map.items():
        if _key in _bank_key:
            _noise_selectors = _noise_selectors + _selectors
            break

    for _sel in _noise_selectors:
        for _el in _soup.select(_sel):
            _el.decompose()

    # 2c. BANKA-ÖZEL içerik selector öncelik listesi
    # Her bankanın gerçek içerik alanını bilen targetlama.
    # Genel liste sonunda fallback olarak devreye girer.
    _bank_content_map = {
        "akbank":        ['.campaign-detail-content', '.campaign-terms',
                          '.campaign-detail', '.campaign-detail-tab-details'],
        "axess":         ['.campaign-detail-content', '.campaign-terms',
                          '.campaign-detail', '.campaign-detail-tab-details'],
        "garanti":       ['.campaignDetailBody', '.campaign-detail__info',
                          '.campaign-detail', '.cmsContent'],
        "garanti bbva":  ['.campaignDetailBody', '.campaign-detail__info',
                          '.campaign-detail', '.cmsContent'],
        "qnb":           ['.campaign-detail-tab-details', '.campaign-detail',
                          '.cmsContent', '.how-to-win'],
        "ziraat bankası": ['.subpage-detail', '#tab-1', '#tab-2', '#tab-3', '#tab-4',
                            '.tabs-content .tab-content', '.campaign-detail'],
        "vakıfbank":     ['.kampanyaDetay', '.kampanyaDetayIcerik',
                          '.campaign-detail'],
        "yapı kredi":    ['.campaign-detail-tab-details', '.campaign-detail-box',
                          '.campaign-detail-content', '.campaign-detail'],
        "işbankası":     ['.campaign-detail-content', '.campaign-detail',
                          '.cmsContent', '#campaignDetailContent'],
        "maximum":       ['.campaign-detail-content', '.campaign-detail',
                          '.cmsContent', '#campaignDetailContent'],
        "maximiles":     ['.campaign-detail-content', '.campaign-detail',
                          '.cmsContent', '#campaignDetailContent'],
        "paraf":         ['.campaign-detail', '.campaign-content',
                          '.paraf-campaign-detail'],
        "denizbank":     ['.kampanya-detay', '.campaign-detail', '.cmsContent'],
        "chippin":       ['.campaign-body', '.campaign-detail'],
        "burgan bank":   ['.box-content', '.raw-data', '.kampanya-detay-icerik'],
        "türk telekom":  ['.campaign-detail-content', '.cms-content', '.featured-privileges'],
        "dunyakatilim":  ['.news-campaign-content', '.bt', '.richtext'],
        "vodafone":      ['.campaign-detail', '.offer-detail', '.terms-conditions'],
    }

    # Genel fallback selector listesi (banka eşleşmezse veya boş çıkarsa)
    _general_content_selectors = [
        '.campaign-terms', '.campaign-detail-content', '.campaign-detail',
        '.campaign-detail-tab-details', '.campaign-detail-box',
        'article.campaign-detail', '.cmsContent', '.how-to-win',
        '.campaign-description', '#tab-details', '.campaign-detail__info',
        '.info-content', 'main', '[role="main"]',
    ]

    # Banka-özel önce, genel sonra
    _priority_selectors = []
    for _key, _selectors in _bank_content_map.items():
        if _key in _bank_key:
            _priority_selectors = _selectors
            break
    _target_selectors = _priority_selectors + [
        s for s in _general_content_selectors if s not in _priority_selectors
    ]

    _content_parts = []
    for _sel in _target_selectors:
        for _el in _soup.select(_sel):
            _t = _el.get_text(separator='\n', strip=True)
            if _t and len(_t) > 80:  # küçük/boş container'ları atla
                _content_parts.append(_t)

    if _content_parts:
        clean_content = '\n\n'.join(_content_parts)
    else:
        # 2d. Fallback: tüm temizlenmiş body metni
        clean_content = _soup.get_text(separator='\n', strip=True)

    import re as _re, html as _html
    clean_content = _html.unescape(clean_content)
    clean_content = _re.sub(r'\n{3,}', '\n\n', clean_content).strip()

    # Combine title + description + body for full context
    raw_text = f"{title}\n{short_description or ''}\n{clean_content}"

    # 3. Call AI Parser Golden
    # Pass structured_cards_text down to the main parser to bypass guessing
    result = parser.parse_campaign(
        raw_html=raw_text, 
        bank_name=bank_name or "", 
        title=title or "", 
        og_title=og_title,
        structured_cards_text=structured_cards_text,
        scraper_sector=scraper_sector
    )
    if not result:
        result = {}

    # 4. Apply short_description fallback
    if not result.get("description") and short_description:
        result["description"] = short_description

    # 5. Ensure short_title exists
    if "short_title" not in result:
        result["short_title"] = result.get("title", title)

    # 6. Fallback error object
    if result.get("_ai_failed"):
        return {
            "_ai_failed": True,
            "title": title,
            "short_title": title,
            "description": short_description,
            "reward_value": None,
            "reward_type": None,
            "reward_text": "",
            "sector": "diger",
            "brands": [],
            "conditions": [],
            "cards": [],
            "participation": "",
            "ai_marketing_text": "",
            "start_date": None,
            "end_date": None
        }

    return result

