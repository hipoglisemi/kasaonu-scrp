"""
AI Parser Service - THE BRAIN 🧠
Uses Gemini or Groq AI to parse campaign data from raw HTML/text
Replaces 100+ lines of regex with intelligent natural language understanding
"""
import os
import json
import re
import html
import logging
import decimal
import signal
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dotenv import load_dotenv # type: ignore

# Find project root
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from .text_cleaner import clean_campaign_text # type: ignore
from .brand_normalizer import cleanup_brands # type: ignore

# DB Imports for Caching (Lazy to avoid circularity)
_SessionLocal = None
_Campaign = None
_Sector = None

from .point_blank_matcher import get_point_blank_matcher # type: ignore
from src.database import SessionLocal # type: ignore

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Gemini API call timed out")

def call_with_timeout(func, args=(), kwargs=None, timeout_sec=60):
    if kwargs is None:
        kwargs = {}
    
    # Set the signal handler and a alarm
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_sec)
    try:
        result = func(*args, **kwargs)
        return result
    finally:
        # Disable the alarm
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

load_dotenv(os.path.join(_root, ".env"), override=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bank Specific Rules (Ported from kartavantaj-scraper)
BANK_RULES = {
    'akbank': """
🚨 AKBANK SPECIFIC RULES:
- TERMINOLOGY: 
    - For Axess/Free/Akbank Kart: Uses "chip-para" instead of "puan". 1 chip-para = 1 TL.
    - For Wings: Uses "Mil" or "Mil Puan". 🚨 100 Mil Puan = 1 TL (domestic) / 2 TL (int).
- PARTICIPATION: Primary method is "Jüzdan" app. Always look for "Jüzdan'dan Hemen Katıl" button. If not found, look for "Akbank Axess POS" instructions.
- SMS: Usually 4566. SMS keyword is usually a single word (e.g., "A101", "TEKNOSA").
- REWARD: If it says "8 aya varan taksit", it's an installment campaign. Earning: "Taksit İmkanı". 🚨 ASLA "Detayları İnceleyin" yazma.
- ELIGIBLE CARDS:
    - 🚨 RAW EXTRACTION (LITERAL): Extract the EXACT card names or categories from the text. 
    - ⛔ NO MAPPING: If text says "Ticari kartlar", write "Ticari kartlar". If it says "Bank’O Card Axess", write "Bank’O Card Axess".
    - ⚠️ TITLE TRAP: Even if title says "Axess'e Özel", check footer for "Axess, Wings, Free... dahildir".
    - ❌ KESİN YASAK: Asla "Kampanyaya Dahil Kartlar" yazma.
    - ⚠️ KESİN YASAK: Kart isimlerini asla 'conditions' (koşullar) listesine yazma. Sadece 'cards' alanına yaz.
- 🚨 AKBANK REDUNDANCY ALERT (CRITICAL):
    - Akbank metinleri tarih ve kart bilgisini çok tekrar eder. 
    - 'conditions' listesine ASLA "1-31 Mart", "Axess kart", "Jüzdan" gibi bilgileri yazma.
    - Koşullar SADECE teknik kurallar içermeli (örn: "POS terminali zorunluluğu", "İndirim limiti").
- PARTICIPATION (REDUNDANCY):
    - 🚨 YASAK: "Juzdan uygulama üzerinden katılabilirsiniz." gibi jenerik metinleri tek başına yazma. Eğer butonda "Hemen Katıl" yazıyorsa "Juzdan'dan Hemen Katıl butonuna tıklayın" gibi somutlaştır.
""",
    'albaraka': """
🚨 ALBARAKA SPECIFIC RULES:
- TERMINOLOGY: Uses "Worldpuan". 1 Worldpuan = 0.01 TL (if value is given in TL, use "TL Worldpuan").
- 🚨 APP CONSTRAINT (CRITICAL): Primary and ONLY app is **"Albaraka Mobil"**. 
    - ⛔ HALÜSİNASYON YASAĞI: Asla "World Mobil" veya "Yapı Kredi Mobil" yazma. Albaraka kampanya metinlerinde "World" geçse bile uygulama adı Albaraka Mobil'dir.
- PARTICIPATION (katilim_sekli):
    - Look for "Albaraka Mobil > Kampanyalar > Katıl/Kod Al".
    - Extract as: "Albaraka Mobil uygulamasındaki Kampanyalar menüsünden katılabilirsiniz."
- ELIGIBLE CARDS:
    - "Albaraka Worldcard", "Albaraka Banka Kartı".
    - Variants: "Trend Bankacılık" (Genç), "Özel Bankacılık" (Elite), "Eflatun Bankacılık".
    - ❌ KESİN YASAK: Sanal kartlar, Ek kartlar ve Business (Ticari) kartlar aksi belirtilmedikçe dahil değildir.
- CONDITIONS: 
    - "Kod Al" gereken kampanyalarda bu şartı belirt.
    - Harcama limitlerini ve müşteri segmenti (örn: "Yeni görüntülü görüşme ile müşteri olanlar") detaylarını ekle.
""",
    'yapı kredi': """
🚨 YAPI KREDI (WORLD) SPECIFIC RULES:
- TERMINOLOGY: "Worldpuan" is the currency.
    - ⚠️ IMPORTANT: "TL Worldpuan" means the value is in TL. If it says "100 TL Worldpuan", earning is "100 TL Worldpuan".
- ELIGIBLE CARDS (cards):
    - 🚨 RAW EXTRACTION (LITERAL): Extract the EXACT card names or common categories from the text.
    - Metinde ne geçiyorsa aynen al: "Worldcard", "Yapı Kredi Kredi Kartları", "Mastercard logolu kartlar", "Business", "World Eko", "Adios" vb.
    - ❌ NO DEFAULTING: If the text says "Mastercard", write "Mastercard". DO NOT write "Worldcard" unless it's in the text.
- PARTICIPATION (katilim_sekli):
    - 🚨 PRIORITY ORDER:
      1. App: "World Mobil" or "Yapı Kredi Mobil". Look for "Hemen Katıl" button.
      2. SMS: Look for a keyword + "4402" (e.g., "KAZAN yazıp 4402'ye SMS gönderin").
    - 🚨 FORMAT: "World Mobil uygulamasından Hemen Katıl butonuna tıklayarak veya [KEYWORD] yazıp 4402'ye SMS göndererek katılabilirsiniz."
- 🚨 REDUNDANCY ALERT: DO NOT repeat card names or dates in 'conditions'.
""",
    'garanti': """
🚨 GARANTI BBVA / BONUS / MILES&SMILES / SHOP&FLY SPECIFIC RULES:
- TERMINOLOGY: "Bonus" (Bonus/Flexi), "Mil" (Miles&Smiles/Shop&Fly).
- ELIGIBLE CARDS (cards):
    - 🚨 RAW EXTRACTION (LITERAL): Metinde ne yazıyorsa DİREKT ONU YAZ.
    - Örnek: "Kampanyaya bireysel Garanti BBVA kredi kartları ve Bonusnet platformundaki bankaların bireysel Bonus kredi kartları dahildir." yazıyorsa AYNEN AL.
    - Sektöre veya markaya özel kart isimlerini (Örn: "Shop&Fly", "Miles&Smiles") metindeki halleriyle listele.
    - ❌ YASAK: "Kampanyaya Dahil Kartlar" gibi başlıkları ASLA kart listesine yazma. Sadece kartın kendi ismini yaz.
- PARTICIPATION: "BonusFlaş" app is primary. Look for "HEMEN KATIL" instructions.
- 🚨 REDUNDANCY ALERT: DO NOT repeat card names, dates, or participation methods (e.g., BonusFlaş) in 'conditions'.
""",
    'işbankası': """
🚨 IS BANKASI/MAXIMUM/MAXIMİLES SPECIFIC RULES:
- TERMINOLOGY: "Maxipuan" (Points) or "MaxiMil" (Miles).
- ELIGIBLE CARDS (cards):
    - 🚨 RAW EXTRACTION (LITERAL): Metinde ne yazıyorsa DİREKT ONU YAZ.
    - 📍 ÖNEMLİ: "Sanal kartlar", "Ticari kartlar" vb. ifadeleri sadece **dahil/geçerli** oldukları belirtilmişse listeye ekle. Eğer "hariçtir" deniyorsa ASLA yazma.
    - Örnek: "İş Bankası Maximum özellikli kredi kartları (Maximum, Maximiles...)" yazıyorsa AYNEN AL.
    - ❌ KESİN YASAK: Fibabanka, Ziraat gibi diğer banka kartlarını ASLA YAZMA. Sadece İş Bankası kartlarını listele.
- PARTICIPATION (katilim_sekli):
    - 🚨 PRIORITY ORDER:
      1. Primary App: Look for "Katıl" button in "Maximum Mobil", "İşCep" or "Pazarama". → Extract as "Maximum Mobil, İşCep veya Pazarama'dan katılabilirsiniz."
      2. SMS: Look for "4402'ye SMS" → Extract as "4402'ye [KEYWORD] yazıp SMS gönderin."
      3. Automatic: If "katılım gerektirmez" or "otomatik" → Use "Otomatik Katılım".
      4. Fallback: If no button/SMS/app is mentioned but there is a clear instruction like "Kampanya detaylarını inceleyin", write exactly that instruction.
    - 🚨 STRICT APP NAMES: ONLY use "Maximum Mobil", "İşCep", or "Pazarama".
    - ⛔ NEGATIVE CONSTRAINT: NEVER use "World Mobil", "Jüzdan", "BonusFlaş", "Yapı Kredi". If you see these, it's a hallucination or cross-promotion; ignore them.
- 🚨 DISCOUNT CODES: If there is an "İndirim Kodu" (e.g., TRBAN25, TROY2024), **MUTLAKA** both 'conditions' listesine ekle hem de 'description' içinde belirt.
- 🚨 REDUNDANCY ALERT: DO NOT repeat card names, dates, or participation methods (e.g., Maximum Mobil, İşCep, Pazarama) in 'conditions'.
- CONDITIONS (SUMMARY MODE):
    - ✔️ ÖZETLE: Maksimum 5-6 madde. Uzun yasal metinleri, tekrar eden kart bilgilerini ve işlem türü sayımlarını atlat.
    - 🚨 İÇERİK: Sadece şunları yaz:
      * Minimum harcama eşiği ("2.000 TL harcamaya 200 MaxiMil")
      * Maksimum kazanç limiti ("Maks. 1.500 MaxiMil")
      * Kampanya dışı işlem türleri ("Nakit çekim, havale, iptal/iade işlemleri hariçtir")
      * Hariç tutulan kart grupları ("Ticari Kredi Kartları kampanyaya dahil değildir")
    - ⛔ YAZMA: Tarihleri, katılım yöntemini, zaten ayrı bir listede verdiğin dahil kart isimlerini tekrar YAZMA.
- BRANDS (SECTOR TAGGING):
    - 🚨 ÖNEMLI: Kampanya belirli bir marka/zincir içinse (Zara, Emirates, Migros vb.) o marka ismini 'brands' listesine ekle.
    - Sektör için: "MaxiMil" → Turizm veya Ulaşım olabilir (metne bak); "Duty Free" → Turizm & Konaklama veya Ulaşım; "Pazarama" → E-Ticaret.
""",
    'vakıfbank': """
🚨 VAKIFBANK/WORLD SPECIFIC RULES:
- TERMINOLOGY: "Worldpuan". 1 Worldpuan = 0.005 TL usually. "TL Worldpuan" = TL value.
- ELIGIBLE CARDS:
    - 🚨 RAW EXTRACTION (LITERAL): Metinde geçen kart isimlerini aynen al: "VakıfBank Worldcard", "Platinum", "Rail&Miles", "Bankomat Kart", "Business", "TROY".
    - 📍 LOCATION: Bilgi genelde metnin ilk cümlesinde veya "Dahil Olan Kartlar" tablosundadır.
- CONDITIONS (SUMMARY MODE):
    - ✂️ SUMMARIZE: The source text is very long. Convert it into max 4-5 bullet points.
    - SCOPE: Include dates, min spend, reward limit, and exclusions.
- PARTICIPATION:
    - Primary: "Cepte Kazan" app or "VakıfBank Mobil".
    - SMS: Often 6635.
""",
    'ziraat': """
🚨 ZIRAAT BANKKART SPECIFIC RULES:
- TERMINOLOGY: "Bankkart Lira". 1 Bankkart Lira = 1 TL.
- ELIGIBLE CARDS:
    - 🚨 STRICT LITERAL EXTRACTION: Extract ONLY the cards explicitly mentioned in the text.
    - 📍 RULE: If text says "Bankkart, Bankkart Genç ve Bankkart Başak", then use EXACTLY ["Bankkart", "Bankkart Genç", "Bankkart Başak"].
    - 📍 RULE: If text says "Taksit özelliği olan Bankkart ve Bankkart Başak", then use EXACTLY ["Bankkart", "Bankkart Başak"].
    - 📍 RULE: Check for "dahil değildir". "Bankkart Business" and "Ücretsiz" are usually EXCLUDED. Do not list excluded cards.
- PARTICIPATION:
    - SMS: Look for specific keywords (e.g., "SUBAT2500", "RAMAZAN", "MARKET") sent to **4757**.
    - App: "Bankkart Mobil", "bankkart.com.tr".
    - Format: "KEYWORD yazıp 4757'ye SMS gönderin" or "Bankkart Mobil uygulamasından katılın".
    - 🚨 FALLBACK: If NO specific method (SMS/App) is found, and it seems like a general campaign (e.g., "İlk Kart", "Taksit"), assume "Otomatik Katılım".
- CONDITIONS:
    - 🚨 FORMAT: SUMMARIZE into 5-6 clear bullet points.
    - 🚨 CONTENT: MUST include numeric limits (max earners, min spend) and dates.
    - Avoid long paragraphs. Use concise language.
""",
    'kuveyt türk': """
🚨 KUVEYT TÜRK (SAĞLAM KART) SPECIFIC RULES:
- TERMINOLOGY: "Altın Puan". 1 Altın Puan = 1 TL.
- ELIGIBLE CARDS (cards):
    - 🚨 STRICT: Extract all cards from the text (usually the 2nd bullet point in details).
    - Keywords: "Sağlam Kart", "Sağlam Kart Kampüs", "Sağlam Kart Genç", "Miles & Smiles Kuveyt Türk Kredi Kartı", "Özel Bankacılık World Elite Kart", "Tüzel Kartlar", "Sağlam Nakit Kart".
    - Include "sanal ve ek kartlar" if mentioned. 
- PARTICIPATION (katilim_sekli):
    - 🚨 PRIORITY: Check for SMS keywords (e.g. "KATIL TROYRAMAZAN") and the short number (e.g. 2044).
    - Look for: "Cebim POS", "Sanal POS", "Mobil" instructions.
    - If "otomatik" or "katılım gerektirmez" is mentioned, use "Kampanya otomatik katılımlıdır."
    - 🚨 FORMAT: Use specific instruction: "2044'e [KEYWORD] yazıp SMS göndererek veya Kuveyt Türk Mobil üzerinden Kampanyalar menüsünden katılabilirsiniz."
- CONDITIONS (conditions):
    - 🚨 DETAYLI AMA NET: 'KOŞULLAR VE DETAYLAR' başlığı altındaki kritik maddeleri al.
    - 🚨 TEMİZLİK: Tarih, kart listesi ve katılım yöntemini BURADA TEKRARLAMA. Sadece harcama sınırları, sektör kısıtlamaları ve hak kazanım detaylarını yaz.
""",
    'halkbank': """
🚨 HALKBANK (PARAF / PARAFLY) SPECIFIC RULES:
- TERMINOLOGY: "ParafPara". 1 ParafPara = 1 TL.
- ELIGIBLE CARDS (cards):
    - 🚨 STRICT: Look for "Dahil:" or "Geçerli kartlar:" section in conditions.
    - Common INCLUSIONS: "Paraf", "Parafly", "sanal kartlar", "ek kartlar", "Ticari kartlar", "Business", "Halkcard".
    - Exclusions like "Paraf Genç" should be checked carefully.
- PARTICIPATION (katilim_sekli):
    - 🚨 PRIORITY ORDER:
      1. SMS: Look for "3404'e SMS" or "3404'e KEYWORD" → Extract as "3404'e [KEYWORD] SMS"
      2. App: Look for "Paraf Mobil'den HEMEN KATIL" or "Halkbank Mobil'den katılın" → Extract as "Paraf Mobil" or "Halkbank Mobil"
      3. Automatic: If "katılım gerektirmez" or "otomatik" → Use "Otomatik Katılım"
    - 🚨 FORMAT: "[KEYWORD] yazıp 3404'e SMS göndererek veya Paraf Mobil uygulamasından Hemen Katıl butonuna tıklayarak katılabilirsiniz."
- CONDITIONS: 🚨 3-5 concise bullet points focusing on spend limits and exclusions ONLY.
""",
    'denizbank': """
🚨 DENIZBANK (DENIZBONUS) SPECIFIC RULES:
- TERMINOLOGY: "Bonus". 1 Bonus = 1 TL.
- ELIGIBLE CARDS (cards):
    - 🚨 RAW EXTRACTION (CRITICAL): Do NOT map cards to a fixed list. Extract the EXACT descriptive string from the text.
    - Examples: 
        * "Tüm bonus özellikli DenizBank Bireysel Kredi Kartları"
        * "DenizBank TROY logolu bireysel ve ticari kredi kartı, banka kartı ve ön ödemeli kartlar"
        * "Net Kart"
    - ❌ KESİN YASAK: Metinde geçmeyen kart isimlerini (DenizBonus Gold vb.) uydurma. Metinde ne yazıyorsa harfi harfine onu al.
- PARTICIPATION:
    - 🚨 PRIORITY:
      1. App: "MobilDeniz" or "DenizKartım". Look for "Hemen Katıl" button.
      2. SMS: Look for keywords sent to **3280**. (e.g. "KATIL yazıp 3280'e gönder").
      3. Automatic: If "katılım gerekmemektedir" or "otomatik", use "Otomatik Katılım".
- CONDITIONS:
    - 🚨 FORMAT: Summarize into 3-5 bullets.
    - Include: Max earning limit, start/end dates, valid sectors.
""",
    'qnb': """
🚨 QNB SPECIFIC RULES:
- TERMINOLOGY: "ParaPuan". 1 ParaPuan = 1 TL.
- ELIGIBLE CARDS:
    - 🚨 Sitedeki kampanya metninde KAMPANYANIN GEÇERLİ OLDUĞU veya belirtilen işlemi YAPAN kart isimlerini (Örn: "QNB Kredi Kartı", "QNB Nakit banka kartı") BİREBİR ve EKSİKSİZ şekilde al. Metinde "QNB Kredi Kartı'nızla" diyorsa geçerli kart "QNB Kredi Kartı" dır.
    - ❌ KESİN YASAK: Eğer metinde bir kart için "dahil değildir", "hariçtir", "kazanamaz" deniyorsa (Örn: Ticari kartlar, QNB Fix, Miles&Smiles vb.) o kartı ASLA 'cards' listesine ekleme. Kendi kendine jenerik kart adı uydurma.
- PARTICIPATION:
    - 🚨 Sitedeki metinde katılım için hangi yöntemler isteniyorsa HEPSİNİ eksiksiz yaz.
    - Eğer hem SMS (Örn: "ECROU yazıp 2273'e") hem Uygulama (Örn: "QNB Mobil'den HEMEN KATIL") varsa İKİSİNİ BİRDEN yaz. Öncelik sırası yoktur, metinde ne görüyorsan onu virgülle ayırarak/bağlaçla birleştirerek yaz.
- CONDITIONS:
    - Kampanyaya dair tüm önemli kuralları (ödülün verilme ve geri alınma tarihleri, taksit sayıları, alt limitler vb.) metinden birebir çıkarıp anlaşılır maddelere böl.
    - Uzunluk veya madde sayısı sınırı YOKTUR. Metindeki önemli hiçbir şart atlanmamalıdır.
"""
    ,
    'teb': """
🚨 TEB (TÜRK EKONOMİ BANKASI) SPECIFIC RULES:
- TERMINOLOGY: "Bonus". 1 Bonus = 1 TL. "TEB Bonus" is the reward program name.
- ELIGIBLE CARDS:
    - 🚨 STRICT: Extract ONLY cards explicitly mentioned in the text.
    - Common cards: "TEB Kredi Kartı", "TEB Bonus Kart", "TEB Banka Kartı", "CEPTETEB".
    - "Bireysel kredi kartları" = ["TEB Kredi Kartı"].
    - 🚨 EXCLUSION: "Ticari kartlar" are often EXCLUDED unless explicitly mentioned.
- PARTICIPATION:
    - 🚨 PRIORITY ORDER:
      1. Campaign Code + SMS: If text contains "Kampanya Kodu: XXXXX" at the top, the participation is "XXXXX yazıp 5350'ye SMS gönderin."
      2. App: "TEB Mobil" or "CEPTETEB". Look for "Hemen Katıl" button.
      3. Checkout/Sepet: If text says "ödeme adımında ... seçin" or "sepet sayfasında" → describe the checkout step.
      4. Automatic: ONLY if text explicitly says "katılım gerektirmez" or "otomatik".
    - ⛔ NEGATIVE: Do NOT write "Otomatik Katılım" if there is a campaign code or any checkout instruction.
    - 🚨 FORMAT: Be specific. Example: "MARKET2026 yazıp 5350'ye SMS gönderin veya TEB Mobil'den Hemen Katıl butonuna tıklayın."
- CONDITIONS:
    - 🚨 CRITICAL: DO NOT repeat information already in dates, eligible cards, or participation sections.
    - 🚨 FOCUS ON UNIQUE DETAILS ONLY:
      * Minimum spend thresholds (e.g. "Her 500 TL harcamaya 50 TL Bonus")
      * Maximum earning limits (e.g. "Maksimum 500 TL Bonus")
      * Excluded transaction types (e.g. "Nakit çekim, taksitli işlemler hariç")
      * Bonus loading timeline (e.g. "Bonus 30 gün içinde yüklenir")
    - 🚨 FORMAT: 3-5 concise bullet points. NO long paragraphs.
    - 🚨 AVOID: Repeating dates, card names, or SMS instructions already extracted.
"""
    ,
    'turkiye-finans': """
🚨 TÜRKİYE FİNANS (HAPPY CARD / ÂLÂ KART) SPECIFIC RULES:
- TERMINOLOGY: 
    - "Bonus": Used often for Happy Card (uses Bonus network). 1 Bonus = 1 TL.
    - "ParaPuan": Sometimes used. 1 ParaPuan = 1 TL.
- ELIGIBLE CARDS (cards):
    - 🚨 STRICT: Extract ONLY cards mentioned.
    - Keywords: "Happy Card", "Happy Zero", "Happy Gold", "Happy Platinum", "Âlâ Kart", "Türkiye Finans Banka Kartı", "Hızır Kart".
    - If "Türkiye Finans Kredi Kartları" is mentioned, include ["Happy Card", "Âlâ Kart"].
    - ❌ KESİN YASAK: Diğer bankaların Bonus kartlarını listeye yazma.
- PARTICIPATION (katilim_sekli):
    - 🚨 PRIORITY ORDER:
      1. SMS: Look for keyword + "2442" (e.g. "AYIN yazıp 2442'ye SMS”).
      2. App: "Mobil Şube" or "İnternet Şubesi". Look for "Kampanyalar" menu.
      3. Automatic: ONLY if "otomatik katılım" or if no SMS/App instruction exists AND text implies auto.
    - 🚨 FORMAT: "[KEYWORD] yazıp 2442'ye SMS göndererek veya Türkiye Finans Mobil Şube üzerinden katılabilirsiniz."
""",
    "chippin": """
🚨 CHIPPIN SPECIFIC RULES:
- TERMINOLOGY:
    - "Chippuan": Reward currency. 1 Chippuan = 1 TL.
    - "Nakit İade": Cash back to credit card.
- ELIGIBLE CARDS: 
    - 🚨 KESİN YASAK: Eğer metinde spesifik bir kart adı yoksa, 'cards' alanına "Chippin" yazıp geçme. 
    - 📍 DOĞRUSU: "Chippin kullanıcıları" veya "Tüm kredi kartları" gibi bir ifade kullan veya sadece ["-"] bırak.
- PARTICIPATION:
    - 🚨 PRIORITY ORDER:
      1. App Payment: "Chippin ile ödeme yapmanız gerekmektedir."
      2. QR Code: "Chippin numaranızı söyleyin" or "QR kodunu okutun".
- CONDITIONS:
    - 🚨 CRITICAL: Extract minimum spend, max reward, and specific branch/online restrictions.
    - 🚨 FORMAT: 3-5 concise bullet points.
    """,
    "enpara": """
🚨 ENPARA SPECIFIC RULES:
- TERMINOLOGY: "İade" or "Geri Ödeme" is commonly used. Rewards are usually TL value.
- ELIGIBLE CARDS: 
    - 🚨 STRICT: "Enpara.com Kredi Kartı" or "Enpara Kredi Kartı".
    - 🚨 NOTE: If "Enpara.com Nakit Kart" is mentioned, include it.
- PARTICIPATION:
    - 🚨 PRIORITY: "Ayın Enparalısı". 
    - Almost all campaigns require being "Ayın Enparalısı". 
    - 🚨 FORMAT: If you see "Ayın Enparalısı olmanız yeterli", the participation method is "Ayın Enparalısı olma şartlarını yerine getirin."
    - No SMS or "Katıl" button is typically needed. 
- CONDITIONS:
    - 🚨 🚨 **CRITICAL**: Extract every important point from the specific section "Nelere Dikkat Etmelisiniz".
    - 🚨 FORMAT: 4-6 concise bullet points.
    - Include: Spend limits, dates, "Ayın Enparalısı" requirement, and brand-specific exclusions.
    """,
    "param": """
🚨 PARAM SPECIFIC RULES:
- TERMINOLOGY: "Nakit İade". 
- ELIGIBLE CARDS:
    - 🚨 STRICT: Sadece metinde geçen kartları al (Örn: "ParamKart").
    - 🚨 KESİN YASAK: Eğer kart ismi yoksa, 'cards' alanına sadece "Param" yazma. "ParamKart sahipleri" yaz veya ["-"] bırak.
- BRANDS & SECTOR:
    - 🚨 CRITICAL: Extract the brand name accurately (e.g., 'Koton', 'Pazarama', 'IKEA') and put it in the `brands` array. Do NOT put 'Param' as a brand.
    - Sector: Pick the correct sector from the valid list based on the brand or general context (e.g., 'Koton' -> 'Giyim & Aksesuar').
- PARTICIPATION:
    - Primary method is typically clicking "Katıl" in "Param Mobil" or checking out with "TROY indirim kodu".
    """,
    "masterpass": """
🚨 MASTERPASS SPECIFIC RULES:
- TERMINOLOGY: "İndirim", "Kupon", "İade". Rewards are usually TL value or Percent.
- ELIGIBLE CARDS: 
    - 🚨 STRICT: Sadece metinde geçen kartları al (Örn: "Mastercard", "Troy"). 
    - 🚨 KESİN YASAK: Kart ismi yoksa 'cards' alanına sadece "Masterpass" veya "Mastercard" yazma. "Masterpass'e kayıtlı kart sahipleri" yaz veya ["-"] bırak.
- BRANDS & SECTOR:
    - 🚨 CRITICAL: Extract the brand name accurately (e.g., 'Martı', 'Boyner', 'Uber', 'Getir', 'Galatasaray') and put it in the `brands` array. Do NOT put 'Masterpass' or 'Mastercard' as a brand.
    - Sector: Pick the correct sector from the valid list based on the brand or general context. If it's a sports event, match, or team (like UEFA, Galatasaray), categorize as 'Kültür & Sanat' or 'Eğlence'.
- PARTICIPATION:
    - Look for "Masterpass ile ödeme" or "Masterpass'e kayıtlı kartınızla".
    - Often requires clicking "Kupon Al". Write participation instructions exactly as described.
    """,
    "dunyakatilim": """
🚨 DÜNYA KATILIM SPECIFIC RULES:
- TERMINOLOGY: Rewards are often "İndirim", "Taksit", "Nakit İade" or physical rewards like "Altın". Write exactly what's offered (e.g., "Altın Hediye", "9 Ay Taksit", "%18 Nakit İade").
    - 🚨 CRITICAL: `reward_text` alanı ASLA "Detayları İnceleyin" olmamalıdır. Başlıktan veya içerikten mutlak bir kampanya özeti çıkar.
- SECTOR & BRANDS:
    - 🚨 CRITICAL: If the campaign is about "Altın", "Fiziki Altın", "FX", or Foreign Exchange, classify it as "Kuyum, Optik ve Saat", NEVER "Hizmet".
- ELIGIBLE CARDS:
    - Often "Dünya Katılım Kartı", "DKart Debit" or "Dünya Katılım Ticari Kart". Extract the exact card name mentioned.
- DATES:
    - If the campaign doesn't explicitly mention dates, return null. The system will automatically assign defaults (current month).
    - 🚨 DO NOT invent 9999-12-31. Use null for missing dates.
- PARTICIPATION:
    - 🚨 CRITICAL: Look very carefully for SMS instructions (e.g., "TROY boşluk ... yazarak 2345'e SMS gönderilmesi"). If present, extract the exact SMS text.
    - If Mobile/Internet app check-in is required, mention it.
    - If there are no specific participation steps mentioned, output "Otomatik Katılım".
- CONDITIONS:
    - Always generate at least 1-2 bullet points for conditions summarizing the title or text.
    """,
    'turkcell': """
🚨 TURKCELL SPECIFIC RULES:
- PARTICIPATION: Details are usually hidden in accordions.
    - 🚨 PRIORITY: Look for keywords like "Katılım Kriterleri", "Nasıl Faydalanırım", "Diğer Satın Alma Seçenekleri", "Kampanya Detayları".
    - If headers contain these, their content is the MOST IMPORTANT for the 'participation' field.
    - If the text mentions "Uygulama üzerinden", "Şifre al", "Paycell", extract these exact steps.
- ELIGIBLE CARDS: 
    - 🚨 KESİN YASAK: Kart ismi yoksa 'cards' alanına sadece "Turkcell" yazma. 
    - 📍 DOĞRUSU: "Turkcell müşterileri", "Paycell Kart sahipleri" veya "Turkcell Pasaj müşterileri" gibi ifadeler kullan.
- BRAND: Identify the partner brand (e.g., Obilet, Sigortam.net, Uber) clearly.
""",
    'paycell': """
🚨 PAYCELL SPECIFIC RULES:
- TERMINOLOGY: "Nakit İade" (Direct cash back to Paycell balance).
- ELIGIBLE CARDS: "Paycell Kart".
- PARTICIPATION: 
    - 🚨 CRITICAL: Look for "Kampanyaya Katıl" buttons or specific instructions in the "Kampanya Koşulları" list.
    - If it says "Kampanyaya katılarak abonelik bedelinizin yarısını geri almanın keyfini çıkarın", look for a "Hemen Katıl" action.
    - If the campaign says "Sadece tvplus.com.tr üzerinden yapılan paket alımlarında geçerlidir", the participation might be "tvplus.com.tr üzerinden harcama yaparak".
    - 🚨 FALLBACK: If NO specific button/SMS is found, and it's a usage-based campaign (e.g. "X harcamasına Y iade"), use "Paycell Kartınızla kampanya kapsamındaki harcamalarınızı yaparak otomatik olarak faydalanabilirsiniz."
- BRANDS & SECTOR:
    - 🚨 CRITICAL: Paycell often has many digital/streaming partners. Extract brands like 'TV+', 'HBO Max', 'Exxen', 'A101', 'Şok', 'Trendyol'.
    - Sector: Match correctly (TV+, HBO Max -> 'dijital-platform').
""",
    'vodafone': """
🚨 VODAFONE RED / FREEZONE SPECIFIC RULES:
- ELIGIBLE CARDS: 
    - 🚨 KESİN YASAK: Kart ismi yoksa 'cards' alanına sadece "Vodafone" yazma. 
    - 📍 DOĞRUSU: "Vodafone Red", "Vodafone FreeZone", "Vodafone müşterileri" gibi ifadeler kullan veya ["-"] bırak.
- PARTICIPATION: 
    - 🚨 PRIORITY: "Vodafone Yanımda" app. Look for "Fırsatı Kullan" or "Şifre Al" buttons.
    - 🚨 FORMAT: "Vodafone Yanımda uygulaması üzerinden kampanya sayfasındaki butona tıklayarak şifre alabilir veya fırsatı kullanabilirsiniz."
- CONDITIONS: Extract "şifre geçerlilik süresi", "tek seferlik", "aylık limit" fields.
""",
    'turk-telekom': """
🚨 TÜRK TELEKOM SPECIFIC PARTICIPATION RULES (MEGA-STRICT):
- TERMINOLOGY: 
    - 🚨 KESİN YASAK: Asla "banka", "banka kanalları" veya "banka şubesi" ifadelerini kullanma. Türk Telekom bir banka değildir.
- PARTICIPATION (katilim_sekli):
    - 🚨 KESİN KURAL: "Kampanyaya katılım kod ile gerçekleştirilecektir" veya "Uygulama üzerinden katılabilirsiniz" gibi kısa ve jenerik özetler ASLA yazma.
    - 🚨 SMS DETECTION (PRIORITY 1): Metinde "şifre", "kod", "sms", "6262", "4000", "5000", "7000" gibi ibareler geçiyorsa DİKKAT kesil.
    - 🚨 SMS EXTRACTION: Eğer metinde bir Anahtar Kelime (Örn: PRIME MIGROS, CHAKRA, SELFY vb.) ve bir Kısa Numara (Örn: 6262) varsa, 'katilim_sekli' kısmına MUTLAKA şu formatta tam cümleyi yaz: "[ANAHTAR KELİME] yazıp [NUMARA]'ya SMS göndererek şifrenizi alabilirsiniz."
    - 🚨 APP DETECTION (PRIORITY 2): Eğer SMS yoksa, "Türk Telekom Uygulaması" (Online İşlemler) içinden hangi menüye girileceğini yaz (Örn: "Bana Özel menüsünden şifre alarak katılabilirsiniz").
    - 📍 NOT: Hiçbir detay yoksa sadece "Türk Telekom uygulaması üzerinden katılabilirsiniz" yaz.
- ELIGIBLE CARDS: "Türk Telekom Prime", "Selfy", "Türk Telekom Mobil müşterileri".
- 🚨 BRAND EXCLUSION (CRITICAL):
    - "Tivibu", "Muud", "Selfy", "Prime", "Evde İnternet", "Mobil" gibi ifadeler Türk Telekom'un kendi markalarıdır.
    - Bunları ASLA 'brands' listesinde birer PARTNER olarak verme.
    - SADECE dış ortaklar (örn: Idefix, Evidea, LC Waikiki) partner markadır.
""",
    'sekerbank': """
🚨 SEKERBANK SPECIFIC RULES:
- TERMINOLOGY: 
    - "Bonus": Reward currency (linked to Bonus network).
    - "Şekerbank Bonus", "Şekerbank Diamond": Main card products.
- ELIGIBLE CARDS: 
    - 🚨 STRICT: "Şekerbank Bonus", "Şekerbank Diamond", "Şekerbank Bonus Business".
    - ❌ KESİN YASAK: Diğer bankaların (Garanti vb.) Bonus kartlarını yazma.
- PARTICIPATION: 
    - Look for SMS keywords sent to **1953**. (e.g. "KAZAN yaz 1953'e gönder").
    - App: "Şeker Mobil Şube".
- BRANDS & SECTOR:
    - 🚨 CRITICAL: Extract the brand name and match to correct sector.
""",
    'tami': """
🚨 TAMI KART SPECIFIC RULES:
- TERMINOLOGY: 
    - "Nakit İade": Cash back to the card. (Earning type: "puan" or "indirim" contextually, but usually maps to direct balance).
    - "Yıldız": Usually for Starbucks campaigns.
- ELIGIBLE CARDS: 
    - 🚨 STRICT: "Tami Kart". 
    - 🚨 NOTE: If it says "Masterpass'e kayıtlı Tami kart", it's still "Tami Kart".
- PARTICIPATION: 
    - 🚨 PRIORITY: Tami campaigns are often AUTOMATIC after card usage. 
    - Look for: "Tami kartınızla yapacağınız harcamalarda", "Masterpass üzerinden ödemelerde".
    - If no specific "button" or "SMS" is mentioned, use "Tami kartınızla kampanya kapsamındaki harcamalarınızı yaparak otomatik olarak faydalanabilirsiniz."
- BRANDS & SECTOR:
    - 🚨 CRITICAL: Extract the partner brand accurately (e.g., 'Starbucks', 'Tıkla Gelsin', 'Hop', 'Kitapyurdu', 'Sigortam.net').
    - 🚨 SECTOR MATCHING: Identify the sector based on the brand:
        * 'Starbucks', 'Tıkla Gelsin' -> 'Restoran & Kafe'
        * 'Hop', 'BinBin' -> 'Ulaşım'
        * 'Kitapyurdu' -> 'Eğitim & Kitap'
        * 'Sigortam.net' -> 'Sigorta'
        * 'Şok', 'A101', 'Migros' -> 'Market'
    - If a brand is found, put it in 'brands' and categorize under the most logical Turkish sector name.
- CONDITIONS:
    - Extract min spend and max reward carefully (e.g., "100 TL Nakit İade").
""",
    'uption': """
🚨 UPTION SPECIFIC RULES:
- TERMINOLOGY: 
    - "Nakit İade": Cash back (Earning type: "cashback").
    - "Uption Kart": The primary payment card.
- ELIGIBLE CARDS: 
    - 🚨 STRICT: "Uption Kart".
- DATES (CRITICAL):
    - Uption detail pages often mention dates like "1-31 Mart" or "tarihleri arasında". 
    - 🚨 MUST: Search the text carefully for these dates. If found, use the current year.
    - If NO date is found at all, return null for both start_date and end_date.
- PARTICIPATION: 
    - Usually automatic when used at the relevant merchant.
    - If the campaign is about "RIA", "Para Transferi" or "Hesaba Al", participation is "Uption uygulaması üzerinden ilgili işlemi gerçekleştirerek".
    - If no specific instructions, use "Uption kartınızla kampanya kapsamındaki harcamalarınızı yaparak otomatik olarak faydalanabilirsiniz."
- BRANDS & SECTOR:
    - 🚨 CRITICAL: Extract the brand (e.g., 'Spotify', 'Netflix', 'YouTube', 'Steam', 'PlayStation', 'RIA', 'Bilet.com').
    - 🚨 SECTOR MATCHING: 
        * 'Spotify', 'Netflix', 'YouTube', 'Steam', 'PlayStation' -> 'dijital-platform'
        * 'Yemeksepeti', 'GetirYemek' -> 'restoran-kafe'
        * 'Uber', 'BiTaksi' -> 'ulasim'
        * 'RIA', 'Para Transferi', 'Hesaba Al' -> 'finans-yatirim'
        * 'Bilet.com', 'Yolcu360', 'Enuygun' -> 'turizm-konaklama'
    - Map brands to Turkish sector slugs accurately.
""",
    'hsbc': """
🚨 HSBC PREMIER SPECIFIC RULES:
- TERMINOLOGY: "NakitPuan". 1 NakitPuan = 1 TL.
- ELIGIBLE CARDS: 
    - 🚨 STRICT: "HSBC Premier" (Do NOT use Advantage terminology, map all to "HSBC Premier" or "Premier").
    - "HSBC Bankamatik Kartı" = ["Bankamatik Kartı"].
- PARTICIPATION:
    - 🚨 PRIORITY: SMS to **4477**. Look for keywords (e.g. "GEYIK yazıp 4477'ye").
    - App: "HSBC Mobil".
    - Automatic: If "katılım gerektirmez" or "otomatik".
- CONDITIONS:
    - 🚨 FORMAT: 3-5 concise bullets.
    - Include: Min spend, max NakitPuan, valid dates.
""",
    'burgan': """
🚨 BURGAN BANK / ON DIGITAL SPECIFIC RULES:
- TERMINOLOGY: "İade" or "Nakit İade". 
- ELIGIBLE CARDS: "ON Kredi Kartı", "ON Banka Kartı", "Burgan Vadeli Hesap".
- PARTICIPATION (participation):
    - 🚨 MANDATORY: Primary method is the "ON Mobil" app.
    - 🚨 EXTRACTION: Search the campaign details/bullets for phrases like "ON Mobil'den 'Hemen Katıl' butonuna tıklayarak", "kampanyaya kaydolması gerekmektedir", or "Hemen Katıl butonuna basın".
    - 🚨 MOVE vs REPEAT: If you find this in the list of conditions, MOVE it to the 'participation' field and DELETE it from the 'conditions' list.
    - ❌ FORBIDDEN: Do NOT use generic text like "Mobil uygulama üzerinden veya banka kanallarından talimatları izleyin". Use the EXACT sentence from the page if found, otherwise use "ON Mobil uygulamasında 'Kampanyalar' bölümünden 'Hemen Katıl' butonuna tıklayarak katılabilirsiniz."
- 🚨 REDUNDANCY ALERT: 
    - Ensure participation steps are ONLY in 'participation', never in 'conditions'.
    - DO NOT repeat dates or eligible cards in the 'conditions' list.
    - 'conditions' should ONLY contain rule-based constraints (e.g., "Maksimum 500 TL iade", "İptal/İadenin yansıması").
"""
}

# ── AI Provider Configuration ──────────────────────────────────────────────
from google.genai import types # type: ignore
from src.utils.gemini_client import get_gemini_client, generate_with_rotation # type: ignore

_GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
try:
    _gemini_client = get_gemini_client()
    print(f"[DEBUG] Gemini AI initialized via gemini_client module (Model: {_GEMINI_MODEL_NAME}).")
except Exception as e:
    print(f"[WARN] Gemini client init failed: {e}")
    _gemini_client = None
# ────────────────────────────────────────────────────────────────────────────


# Global Brand Exclusions (Payment Schemes, Networks, etc.)

class AIParser:
    """
    Gemini AI-powered campaign parser.
    Extracts structured data from unstructured campaign text.
    Uses exponential backoff for rate limits and rotates keys.
    """

    def __init__(self, model_name: Optional[str] = None):
        self._client = _gemini_client
        self.model = None
        print(f"[DEBUG] AIParser using Gemini | model: {_GEMINI_MODEL_NAME}")

    # ── Unified call helper ──────────────────────────────────────────────────
    def _call_ai(self, prompt: str, timeout_sec: int = 65) -> str:
        """Send prompt to active AI provider."""
        import time
        # Intentional delay to avoid violent RPM spikes across workers
        time.sleep(1.0) 
        
        # Token optimization settings (AI Studio web settings do NOT apply to raw API keys)
        config = types.GenerateContentConfig(
            temperature=0.0,
            top_p=0.1,
            top_k=1,
            response_mime_type="application/json",
            max_output_tokens=6000
        )

        result = call_with_timeout(
            generate_with_rotation,
            kwargs={
                "prompt": prompt,
                "model": _GEMINI_MODEL_NAME, 
                "config": config
            },
            timeout_sec=timeout_sec,
        )
        return str(result) if result else "{}"  # type: ignore
    # ────────────────────────────────────────────────────────────────────────
        
    def parse_campaign_data(
        self,
        raw_text: str,
        title: Optional[str] = None,
        bank_name: Optional[str] = None,
        card_name: Optional[str] = None,
        tracking_url: Optional[str] = None,
        force: bool = False,
        campaign_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Parse campaign data using Gemini AI
        
        Args:
            raw_text: Raw HTML/text from campaign page
            title: Campaign title (optional, helps with context)
            bank_name: Bank name (optional, helps identify cards)
            card_name: Card name (optional, for context)
            tracking_url: URL to check in cache (Madde 1)
            force: If True, skip cache and force AI call
            campaign_id: Optional campaign ID for source tracking
            
        Returns:
            Dictionary with structured campaign data
        """
        # 1. Check Global Cache (Madde 1)
        if tracking_url and not force:
            cached_data = self._check_db_cache(tracking_url)
            if cached_data:
                # Type-safe slicing for linter
                safe_url = str(tracking_url)
                print(f"   ✨ Using cached AI data for: {safe_url[:60]}...")  # type: ignore
                return cached_data

        # Clean text
        clean_text = self._clean_text(raw_text)

        # --- 2. Point-Blank Pre-Extraction (Nokta Atışı) ---
        pb_matches = []
        db = SessionLocal()
        try:
            matcher = get_point_blank_matcher(db)
            # 🛡️ EXCLUSION LIST: Avoid matching the scraper name as a partner brand
            exclude_list = [bank_name, card_name]
            pb_matches = matcher.match_campaign(str(title) if title else "", clean_text, exclude_terms=exclude_list)
            
            # 🛡️ HOST PROTECTION: If we have multiple matches and one of them is a "Host" (TT, Vodafone, etc.),
            # and another is a "Guest" (D&R, TikTak, etc.), we SHOULD NOT let the host dictate the sector.
            if pb_matches and len(pb_matches) > 1:
                host_slugs = {'turk-telekom', 'vodafone', 'turkcell', 'shell', 'opet', 'petrol-ofisi', 'totalenergies'}
                guest_matches = [m for m in pb_matches if m.get('sector') != 'fatura-telekomunikasyon' and m.get('sector') != 'akaryakit']
                if guest_matches:
                    # Keep host for brand extraction but prioritized guest for sector instructions
                    pb_matches = guest_matches + [m for m in pb_matches if m not in guest_matches]
        except Exception as e:
            print(f"   ⚠️ Point-Blank matcher error: {e}")
        finally:
            db.close()
        
        # Build prompt
        prompt = self._build_prompt(clean_text, datetime.now().strftime("%Y-%m-%d"), bank_name, title, pb_matches)
        
        # --- 3. AI Call ---
        # Resilience is now handled at the gemini_client level (sequential retries + global cooling)
        try:
            result_text = self._call_ai(prompt, timeout_sec=120)

            if not result_text:
                print("   ⚠️ Empty response text.")
                result_text = "{}"

            # ── DEBUG RAW RESPONSE ──
            if os.getenv("DEBUG_AI"):
                print(f"DEBUG: RAW AI RESPONSE FOR {title or 'Campaign'}:\n{result_text}")
            
            # Extract JSON from response
            json_data = self._extract_json(result_text)

            # Validate and normalize
            normalized = self._normalize_data(json_data)

            # --- 4. Report Potential New Rules to Pool ---
            db = SessionLocal()
            try:
                # If we have matches already, we still report NEW ones found by AI
                matcher = get_point_blank_matcher(db)
                existing_pb_brands = [m["brand"] for m in pb_matches]
                
                if normalized.get("brands"):
                    for b in normalized["brands"]:
                        if b and b != "Genel" and b not in existing_pb_brands:
                            # Only report if it's NOT already in our point-blank list for this campaign
                            matcher.report_new_candidate(b, b, normalized["sector"], campaign_id=campaign_id)
            except Exception as e:
                print(f"   ⚠️ Reporting candidate failed: {e}")
            finally:
                db.close()
            
            # --- 5. Card Hallucination Guard ---
            if normalized.get("cards") and clean_text:
                normalized["cards"] = self._validate_cards_against_text(
                    normalized["cards"], clean_text
                )
            
            # --- 6. Brand Hallucination Guard ---
            if normalized.get("brands") and clean_text:
                normalized["brands"] = self._validate_brands_against_text(
                    normalized["brands"], clean_text, str(title) if title else ""
                )
            
            # INJECT cleaned text into the result dictionary for scrapers to save to DB
            normalized["_clean_text"] = clean_text

            return normalized

        except Exception as e:
            logger.error(f"AI Parser Final Failure: {e}")
            fallback = self._get_fallback_data(str(title) if title else "Kampanya") # type: ignore
            fallback["_clean_text"] = clean_text
            return fallback

    def _check_db_cache(self, tracking_url: str) -> Optional[Dict[str, Any]]:
        """Check database if this URL was already parsed successfully."""
        global _SessionLocal, _Campaign, _Sector
        try:
            # Lazy import to avoid circular dependencies
            from src.database import SessionLocal # type: ignore
            from src.models import Campaign, Sector # type: ignore
            if _SessionLocal is None:
                _SessionLocal = SessionLocal
                _Campaign = Campaign
                _Sector = Sector
            
            db = _SessionLocal()
            try:
                # Find existing campaign with same tracking_url that has minimum metadata
                # Priority to one that has reward_text or description
                existing = db.query(_Campaign).filter(
                    _Campaign.tracking_url == tracking_url,
                    _Campaign.description.isnot(None),
                    _Campaign.reward_text.isnot(None)
                ).first()

                if existing:
                    # Map to AI schema
                    sector_name = "Diğer"
                    if existing.sector_id:
                        sec = db.query(_Sector).filter(_Sector.id == existing.sector_id).first()
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
                        "participation": "Otomatik katılım" if "Otomatik" in (existing.conditions or "") else "",
                        "start_date": existing.start_date.strftime("%Y-%m-%d") if existing.start_date else None,
                        "end_date": existing.end_date.strftime("%Y-%m-%d") if existing.end_date else None,
                        "sector": sector_name,
                        "brands": [], # Not stored as names in Campaign table, usually acceptable to omit from cache
                        "_cached": True,
                        "_clean_text": existing.description # Fallback
                    }
            finally:
                db.close()
        except Exception as e:
            print(f"   ⚠️ Cache check failed: {e}")
        return None

    def _clean_text(self, text: str, title: Optional[str] = None) -> str:
        """
        Clean and normalize text before sending to AI.
        Relaxed strategy to prevent stripping critical reward/participation data.
        """
        if not text:
            return ""

        # ── Step 0: HTML parsing and decomposing ─────────────────────
        try:
            from bs4 import BeautifulSoup # type: ignore
            soup = BeautifulSoup(text, 'html.parser')
            # Keeping 'button' and 'a' text as they often contain participation triggers
            unwanted_tags = ['script', 'style', 'footer', 'nav', 'header', 'noscript', 'meta', 'iframe', 'svg']
            for tag in soup(unwanted_tags):
                tag.decompose()
            text = soup.get_text(separator='\n', strip=True)
        except Exception as e:
            print(f"[WARN] BeautifulSoup parsing failed in _clean_text: {e}")

        # ── Step 1: line-level boilerplate filter ────────────────────────────
        _NAV_PATTERNS = re.compile(
            r'^(ana sayfa|şubeler|iletişim|bize ulaşın|hakkımızda|kvkk|gizlilik|'
            r'çerez|copyright|tüm hakları|instagram|twitter|facebook|linkedin|'
            r'youtube|bizi takip|site haritası|kariyer|başvuru|indir|download)$',
            re.IGNORECASE
        )

        lines = text.split('\n')
        seen: set = set()
        filtered: list = []
        for line in lines:
            stripped = line.strip()
            # Relaxed length check: Keep anything over 5 chars (e.g. "100 TL", "SMS")
            if len(stripped) < 40:
                lower = stripped.lower()
                if _NAV_PATTERNS.match(lower) or len(stripped) < 5:
                    continue
            # Drop exact duplicates to save tokens
            if stripped in seen:
                continue
            seen.add(stripped)
            filtered.append(stripped)

        text = '\n'.join(filtered)

        # ── Step 2: normalise whitespace ────────────────────────────
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[^\w\s\.,;:!?%₺\-/()İıĞğÜüŞşÖöÇç\n]', ' ', text)

        # ── Step 2.5: BOILERPLATE SNIPER (Truncate at noise sections) ──
        # These markers usually signal the end of campaign data and beginning of site footer/sidebar/other campaigns.
        noise_markers = [
            r"çerez aydınlatma metni",
            r" zorunlu çerezler ",
            r"daha fazla bilgi için",
            r"benzer (kampanyalar|fırsatlar)",
            r"diğer (kampanyalar|fırsatlar)",
            r"ilginizi çekebilecek kampanyalar",
            r"ilginizi çekebilir",
            r"sizin için seçtiklerimiz",
            r"popüler markalar",
            r"bizi takip edin",
            r"site haritası",
            r"tüm hakları saklıdır",
            r"copyright",
            r"en çok tercih edilen kredi kartlarını keşfedin",
            r"fırsatlardan hemen yararlanın",
            r"seveni, kullananı, bedavası en bol",
            r"başvurunuzu hemen yapın",
            r"deniz bonus.*en çok tercih edilen",
            # Akbank footer patterns
            r"axess mobil.*hemen indir",
            r"app store ile indir",
            r"google play ile indir",
            r"mesajınız gönderildi",
            r"ana sayfaya dön",
            r"merak ettikleriniz",
            r"sıkça sorulan sorular",
            r"başvurum nerede",
            r"kart şifresi al",
            r"faiz ve ücretler",
            r"hesap özeti açıklamaları",
            r"kişisel verilerin korunması",
            r"e-?mail toplama ve gönderim",
            # İşbankası footer patterns
            r"kampanyayı paylaş",
            r"maximum mobil.*indir",
            # Garanti / BonusFlaş footer
            r"bonusflaş.*indirmek için",
            r"bonusflaş.*ı indirin",
            r"cüzdan\s+kampanyalar\s+ödemeler\s+kartlar",
            r"qr kod okuyucu",
            # General bank footers
            r"sosyal medya\s+her hakkı",
            r"her hakkı.*\.a\.ş",
            r"çerez politikası\s+bize ulaşın",
            r"bize ulaşın\s+sosyal medya",
            r"biten kampanyalar",
            # Şekerbank sidebar (benzer kampanya link listesi)
            r"şekerbank\s+troy\s+thy\s+kampanyası",
            r"kampanyası\s+\w+\s+kampanyası\s+\w+\s+kampanyası",
            # Nays navigation menu
            r"al/sat\s+biriktir\s+otomatik\s+para",
            r"paribu.ya\s+para\s+gönder",
            r"faturasız\s+hatta.*tl\s+yükl",
            # Akbank HEMEN İNDİR footer
            r"hemen\s+indir\s+veya\s+app\s+store",
            r"jüzdan.*ı\s+indir",
            # Generic cross-campaign / sidebar navigation
            r"prev\s+next\s+\w+\s+servis",
            r"detaylı\s+bilgi\s+prev\s+next",
            # Vodafone/Turkcell footer
            r"vodafone\s+yanımda.*indir",
            r"turkcell\s+dijital\s+operatör",
        ]
        
        text_lower = text.lower()
        earliest_noise_idx = len(text)
        
        # 🚨 SMART TRUNCATION GUARD: Truncate at noise sections to prevent illusion brands.
        # But only if it's in the second half of the text (nav/boilerplate protection).
        min_truncation_pos = int(len(text) * 0.4)
        
        for marker in noise_markers:
            for match in re.finditer(marker, text_lower):
                if match.start() >= min_truncation_pos and match.start() < earliest_noise_idx:
                    earliest_noise_idx = match.start()
        
        if earliest_noise_idx < len(text):
            # If noise marker found after the middle, truncate there to kill "Related Offers"
            text = text[:earliest_noise_idx].strip()

        # ── Step 2.6: LEADER NOISE REMOVAL (Header/Nav) ──
        # If the campaign title exists deep in the text, and there's a lot of nav noise before it, trim it.
        if title:
            # Look for the FIRST occurrence of the title in the cleaned text
            title_pos = text.lower().find(title.lower())
            # If title is found and it's preceded by more than 800 chars of likely nav noise
            if title_pos > 800:
                # Basic guard: ensure we don't trim if title is found extremely late
                if title_pos < len(text) * 0.8:
                    text = text[title_pos:].strip()
        
        # ── Step 2.7: YAPIKREDI SPECIFIC HEADER CLEANING (Manual patterns)
        yapi_header_markers = ["world nedir?", "worldcard kredi kartı başvurusu", "world'e özel hizmetler"]
        for marker in yapi_header_markers:
             m_pos = text.lower().find(marker)
             if 0 <= m_pos < 1000: # Only if found early in the text
                  # Find the first 'Kampanyalar' or 'Ana Sayfa' which usually follows these
                  restart_pos = text.lower().find("ana sayfa", m_pos)
                  if restart_pos != -1 and restart_pos < 2500:
                       text = text[restart_pos:].strip()
                       break

        # ── Step 3: Length limit (reverting to a safer 8000 AFTER cleaning) ──────────
        if len(text) > 8000:
            text = text[:8000] # type: ignore

        return text.strip()
    
    def _build_prompt(self, raw_text: str, current_date: str, bank_name: Optional[str], page_title: Optional[str] = None, pb_matches: Optional[List[Dict]] = None) -> str:
        # 1. Clean Text (Remove boilerplate)
        cleaned_text = clean_campaign_text(raw_text)

        # 1.1 Fetch Dynamic Blocklist for the prompt
        dynamic_blocklist = "Bonusnet, BonusFlaş, Jüzdan, Masterpass, Mastercard, Visa" # Fallback
        db = SessionLocal()
        try:
            from .point_blank_matcher import get_point_blank_matcher
            matcher = get_point_blank_matcher(db)
            if matcher.blocklist:
                # Group names for a clean prompt
                dynamic_blocklist = ", ".join(sorted(list(matcher.blocklist)))
        except:
            pass
        finally:
            db.close()
        
        # 2. Get Bank Specific Instructions
        bank_instructions = ""
        if bank_name:
            bank_name_lower = bank_name.lower()
            for bank_key, rules in BANK_RULES.items():
                if bank_key in bank_name_lower:
                    bank_instructions = rules
                    break

        # 3. If page h1 title provided, lock it in the prompt
        title_instruction = ""
        if page_title and page_title.strip() and page_title.strip() != "Başlık Yok":
            title_instruction = f"""
🔒 BAŞLIK KILIDI: Bu kampanyanın resmi başlığı sayfadan alındı:
"{page_title.strip()}"
'title' alanına SADECE bu başlığı yaz. Metinden farklı bir başlık TÜRETME. Kısaltabilir veya dilbilgisi düzeltmesi yapabilirsin ama anlamı değiştirme.
"""

        # 4. Point-Blank Instructions (The Hallucination Killers)
        pb_instruction = ""
        if pb_matches:
            brand_names = [m["brand"] for m in pb_matches if m.get("brand")]
            
            pb_instruction = f"""
🔒 POINT-BLANK (POTANSİYEL MARKA ADAYLARI):
- METİNDE GEÇEN MARKALAR: {', '.join(brand_names)}

TALİMATlar (AKILLI AYRIŞTIRMA):
1. 🧠 ANALİZ ET: Yukarıdaki markalar gerçek bir kampanya ORTAĞI mı (örn: Trendyol, Migros) yoksa sadece alt yapı/katılım kanalı mı (örn: Tivibu, Online İşlemler, Fiber)?
2. 🛡️ FİLTRELE: Sadece gerçek partnerleri 'brands' listesine ekle. Bankanın veya kurumun (TT, Turkcell vb.) kendi servislerini partner olarak YAZMA.
3. ⚠️ KRİTİK: '{bank_name or 'Banka'}' ismini veya kart isimlerini (Axess, Bonus, Maximum vb.) ASLA marka olarak yazma.
4. 🚨 **AMAZON AYRIMI (KRİTİK)**: Metin genel bir alışveriş veya kargo kampanyasıysa sektörü 'e-ticaret' seç. SADECE 'Amazon Prime' üyeliği, aboneliği veya Prime Video/Müzik ödemesi ise 'dijital-platform' seç.
5. 🚨 **SEKTÖR HİYERARŞİSİ (ÇOK KRİTİK)**:
        1. Eğer kampanya belirli bir dikey sektöre (Giyim, Elektronik, Kitap, Kozmetik, Akaryakıt, Turizm vb.) ait uzman bir markada ise (örn: Altınyıldız, Teknosa, İdefix, Gratis, ETS Tur), işlem web sitesinden/mobil uygulamadan yapılsa dahi sektörü o **DİKEY SEKTÖR** (Giyim, Elektronik vb.) olarak belirle.
        2. 'e-ticaret' sektörü SADECE çok kategorili "Pazar Yerleri" (Marketplace) için saklanmalıdır: Trendyol, Hepsiburada, Amazon (Shopping), Pazarama, Çiçeksepeti, n11.
        3. Bir marka hem dikey bir uzmanlığa sahipse hem de internetten satılıyorsa, dikey uzmanlık (Giyim, Elektronik vb.) HER ZAMAN kazanır.
     Kısacası: Ödeme yöntemine veya satış kanalına değil, harcamanın YAPILDIĞI YERE ve SATIN ALINAN ÜRÜNE odaklan. Sektörü belirlemek için Başlık + Metin içeriğindeki ana amaca odaklan.
6. 🛡️ SEKTÖR ODAKLI MARKA DENETİMİ: Metinde açıkça bu isimler geçmiyorsa marka UYDURMA. Metinde spesifik marka yoksa 'brands' listesini BOŞ bırak. 
"""

        return f"""
Sen uzman bir kampanya analistisin. Aşağıdaki kampanya metnini analiz et ve JSON formatında yapısal veriye dönüştür.
Bugünün tarihi: {current_date} (Yıl: {datetime.now().year})

{bank_instructions}
{title_instruction}
{pb_instruction}

VALID- SECTOR (CRITICAL):
    Valid Sectors for Validation:
    {{
        "Market & Gıda": "market-gida",
        "Akaryakıt": "akaryakit",
        "Giyim & Aksesuar": "giyim-aksesuar",
        "Restoran & Kafe": "restoran-kafe",
        "Elektronik": "elektronik",
        "Mobilya, Dekorasyon & Yapı Market": "mobilya-dekorasyon",
        "Sağlık, Kozmetik & Kişisel Bakım": "kozmetik-saglik",
        "E-Ticaret": "e-ticaret",
        "Ulaşım": "ulasim",
        "Dijital Platform & Oyun": "dijital-platform",
        "Kültür, Sanat & Spor": "kultur-sanat",
        "Eğitim": "egitim",
        "Sigorta": "sigorta",
        "Otomotiv": "otomotiv",
        "Vergi & Kamu": "vergi-kamu",
        "Turizm, Konaklama & Seyahat": "turizm-konaklama",
        "Mücevherat, Optik & Saat": "kuyum-optik-ve-saat",
        "Fatura & Telekomünikasyon": "fatura-telekomunikasyon",
        "Anne, Bebek & Oyuncak": "anne-bebek-oyuncak",
        "Kitap, Kırtasiye & Ofis": "kitap-kirtasiye-ofis",
        "Evcil Hayvan & Petshop": "evcil-hayvan-petshop",
        "Hizmet & Bireysel Gelişim": "hizmet-bireysel-gelisim",
        "Finans & Yatırım": "finans-yatirim",
        "Diğer": "diger"
    }}
    🚨 NOTE: If the campaign is about Sports, Matches, Football, Theatre, or Concerts (e.g., UEFA, Galatasaray, tiyatro, sinema), it MUST be categorized as 'kultur-sanat' (Kültür, Sanat & Spor), NOT 'diger'.
    🚨 NOTE: If the campaign is about "yeni müşteri" (new customer), "kredi kartı başvurusu" (credit card application), "ihtiyaç kredisi" (loan) or any banking/financial product sale, you MUST categorize it as 'finans-yatirim'.
    🚨 SECTOR OUTPUT RULE: Your JSON `"sector"` value must ONLY be one of the slugs above (e.g. "market-gida", NOT "Market & Gıda").
    🚨 🛡️ ÖDEME YÖNTEMİ VS ÜRÜN AYRIMI (ÇOK ÖNEMLİ): Eğer metinde "Faturana Yansıt", "Vodafone faturana ek ödeme", "Masterpass ile öde" gibi ibareler geçiyorsa, sektörü 'fatura-telekom' veya 'finans-yatirim' SEÇME. Ödeme yöntemi kampanya sektörünü değiştirmez.
       - Örn: Hatemoğlu mağazasında faturana ek ödeme ile kıyafet alınıyorsa sektör 'giyim-aksesuar' olmalıdır.
       - Örn: TikTak araç kiralamada faturaya ek ödeme yapılıyorsa sektör 'ulasim' olmalıdır.
    Kısacası: Ödeme yöntemine değil, harcamanın YAPILDIĞI YERE ve SATIN ALINAN ÜRÜNE odaklan. Sektörü belirlemek için Başlık + Metin içeriğindeki ana amaca odaklan.

⭐⭐⭐ KRİTİK KURALLAR (DOKUNULMAZ) ⭐⭐⭐
1. **DİL**: Tamamı TÜRKÇE olmalı.
2. **BRANDS**: Metinde geçen markayı TAM OLARAK al. 
    - 🚨 **ILLUSION PROTECTION (CRITICAL)**: Metnin sonu veya yan kolonlarında geçen "İLGİNİZİ ÇEKEBİLECEK DİĞER KAMPANYALAR" veya "Benzer Kampanyalar" bölümlerindeki markaları (Örn: Beymen, Avva vb.) KESİNLİKLE EKLEME! Sadece ana kampanya metninde asıl konu olarak geçen markayı belirt.
    - 🚨 **HALÜSİNASYON YASAĞI (ÇOK ÖNEMLİ)**: Sadece metin içinde AÇIKÇA okuduğun marka isimlerini ekle. Eğer kampanya tüm e-ticaret siteleri gibi "Genel Sektör" kampanyasıysa (ve açıkça marka listesi verilmemişse), asla kafandan tahmini markalar (Trendyol, Hepsiburada, Opet, THY vb.) UYDURMA! Metinde marka yoksa 'brands' listesini boş bırak veya sadece ["Genel"] yaz.
    - 🚨 **ÖNEMLİ YASAK**: Asla kampanya sahibi bankayı ({bank_name or 'Banka'}), kart programını (Maximum, Axess, Bonus, World, Wings, Paraf, Maximiles vb.) veya banka uygulamalarını/ödeme sistemlerini ({dynamic_blocklist}) MARKA olarak ekleme. Sadece ortak markayı (ör. Trendyol, Migros, THY) ekle.
    - 🚨 **FORMAT KURALI**: Marka veya kart isimlerini asla "P, a, r, a, f" veya "A, x, e, s, s" gibi her harfi virgülle ayrılmış şekilde yazma. Sadece tam ve okunabilir ismi yaz ("Paraf", "Axess").
    - 🚨 **GENEL KAMPANYALAR KURALI (ŞART!)**: Eğer kampanya kredi başvurusu, nakit avans, limit artırımı, ek taksit gibi SADECE bankanın kendi genel kampanyasıysa ve ortada dışarıdan başka bir ortak marka (Trendyol, Migros, THY vb.) YOKSA, markayı KESİNLİKLE BOŞ bırak. ["Genel"] yazma! Sadece [] yaz!
3. **SECTOR**: Yukarıdaki VALID SECTORS listesinden EN UYGUN olanı seç. Asla bu liste dışına çıkma.
4. **MARKETING**: 'description' alanı MUTLAKA 2 cümle olmalı. Samimi ve kullanıcıyı teşvik edici olmalı.
    - 🚨 BÜYÜK HARF KURALI (HARF DÜZENİ): Eğer girdi metninde veya başlıkta TAMAMI BÜYÜK HARFLE (ALL CAPS) yazılmış kelimeler/cümleler (örn: "KAMPANYAYA KATIL", "İNDİRİM FIRSATI") varsa, JSON çıktısındaki her bir alanda ('description', 'conditions', 'title', vs.) bunları normal Cümle Düzenine (Sentence case) veya Başlık Düzenine (Title case) TERCÜME ET. Asla tamamı büyük harfli kelime gruplarını olduğu gibi bırakma.
5. **PARTICIPATION (katilim_sekli)**:
    - 🚨 ASLA ATLATMA: SMS anahtar kelimeleri (örn: SUBAT1000, KATIL) ve kısa numaralar (örn: 4566, 4757) kampanya için kritik hayati veridir. Bunları mutlaka 'katilim_sekli' alanına formatlı şekilde yaz.
    - 🚨 ASLA ÖZETLEME: Metinde spesifik bir buton ("Hemen Katıl"), bir sayfa ("Kampanyalar sekmesi") veya bir menü geçiyorsa bunu ASLA silme ve "ürün satın alarak" diye jenerik bir cümleye dönüştürme. Kullanıcının tam olarak NEYE tıklayacağı eksiksiz yer alsın.
    - Örn: "4757'ye SUBAT1000 yazıp SMS göndererek katılabilirsiniz veya ON Mobil'de Kampanyalar sekmesinden Hemen Katıl butonuna basabilirsiniz."
6. **CONDITIONS (STRICT BUT INCLUSIVE)**: 
    - 🚨 **NEVER SKIP CRITICAL DATA**: Eğer girdi metni 1000 karakterden uzunsa ve birçok kural içeriyorsa, 'conditions' listesini ASLA 1-2 maddeyle geçiştirme veya boş bırakma.
    - 🚨 **İÇERİK ODAKLI AYRIŞTIRMA**: Kampanyaya özel her türlü kuralı (Örn: "Günde en fazla 1 işlem", "Kampanya kapsamında kazanılan puanların son kullanım tarihi", "Fiziki POS'tan geçme zorunluluğu") MUTLAKA listeye ekle.
    - 🚨 **PARTNER BANKALAR (CRITICAL)**: Eğer metinde "Anadolu Bank", "Albaraka", "Vakıfbank" veya "Worldcard lisanslı bankalar" gibi isimler geçiyorsa, bu isimleri MUTLAKA 'cards' listesine veya 'conditions' alanına KURTARARAK ekle. Asla "Worldcard" diyerek sadeleştirip silme.
    - 🚨 🚨 **YASAK**: Sadece 'start_date' ve 'end_date' gibi tarihleri 'conditions' içine yazma.
    - 🚨 **TAKSİT & BDDK UYARISI**: Başlıkta "9 Taksit" yazsa bile, koşullar alanında "BDDK kuralları gereği mobilyada 9 taksit" gibi detaylı halini MUTLAKA koru. Başlıkta var diye silme.
    - 🚨 **JURIDICAL BOILERPLATE REMOVAL (SMART MODE)**: Sadece tamamen standart olan "Banka kampanyayı durdurma hakkını saklı tutar" gibi her bankada aynı olan cümleleri sil. Kampanyanın kendi kurgusuna ait kısıtlamaları (Ticari kartlar dahil değil, Anadolu Bank dahil vb.) SİLME.
    - ✅ **HEDEF**: Kullanıcının kampanya detay sayfasında bilmesi gereken her teknik/operasyonel kısıtı maddedeler halinde sunmak.
10. **CARDS (cards)**:
    - 🚨 MUTLAK KURAL: 'cards' listesine SADECE ve SADECE metinde birebir okuduğun kart isimlerini yaz. Metinde "Paraf, Parafly, Paraf Business" yazıyorsa AYNEN bu 3 kartı listele.
    - 🚨 HALÜSİNASYON YASAĞI: Metinde geçmeyen kart ismini KESİNLİKLE EKLEME. Eğer metinde sadece "Axess" geçiyorsa "Axess Gold", "Axess Platinum" gibi varyantları UYDURMA.
    - 🚨 **NEGATİF KISITLAMALAR (Dahil Değildir)**: Metinde 'dahil değildir', 'geçerli değildir', 'hariçtir', 'kapsam dışıdır', 'sayılmamaktadır' gibi ifadeler geçen cümleleri çok dikkatli oku. Özellikle "X markalı ürünler", "X satıcılı ürünler" gibi ibarelerden sonra gelen kısıtlamalara dikkat et. Bu markaları 'brands' listesinden KESİNLİKLE çıkar.
    - 🚨 **MARKA-KOŞUL EŞLEŞTİRME**: 'brands' alanına eklediğin her ana markayı, 'conditions' listesine de "X mağazalarında geçerlidir." (veya "X sitesinde geçerlidir.") maddesi olarak MUTLAKA ekle.
    - 🚨 METNE SADIK KAL: Kart isimlerini metin içindeki YAZILIŞIYLA al. "DenizBonus" yazıyorsa "DenizBonus" yaz, "Deniz Bonus" YAZMA.
    - 🚨 VARSAYIM YAPMA: Banka adını bildiğin için o bankanın tüm kart çeşitlerini listeye EKLEME. Sadece metinde açıkça yazan kartları al.
    - 🚨 KURUM KAMPANYALARI (Turk Telekom, Shell, Turkcell vb.): Eğer metinde spesifik bir kart adı geçmiyorsa, 'cards' alanına kurumun adını tek başına yazma (Örn: "Turkcell", "Turkcell" yazma). Onun yerine kimlerin dahil olduğunu belirten ifadeyi yaz (Örn: "Turk Telekom müşterileri", "Shell Club Smart sahipleri") veya hiçbir şey bulamazsan sadece ["-"] bırak.
    - Eğer metinde hiçbir kart ismi veya dahil olan grup bilgisi geçmiyorsa boş liste [] döndür.

    - 🚨 KESİN YASAK: 'description' alanına tarih, kart veya katılım bilgisi ASLA EKLEME.
5. **REWARD TEXT (PUNCHY)**: 
    - 'reward_text' kısmına en kısa ve çarpıcı ödülü yaz.
    - "Peşin fiyatına" gibi detayları yazma, sadece "150 TL Puan", "+4 Taksit", "%20 İndirim" yaz.
    - Eğer "100 TL Worldpuan" diyorsa "100 TL Worldpuan" yaz. (Değer + Tür)
6. **CONDITIONS (STRICT REDUNDANCY & BOILERPLATE REMOVAL)**: 
    - 🚨 🚨 **YASAK**: Aşağıdaki alanlarda zaten olan bilgileri 'conditions' içine yazmak KESİNLİKLE YASAKTIR:
        - 'start_date' ve 'end_date' (Örn: "Şubat ayı boyunca" yazma!)
        - 'cards' (Örn: "Axess sahipleri" yazma!)
        - 'participation' (Örn: "Jüzdan'dan katılın" yazma!)
        - 'title' (Başlıkta olan bilgiyi tekrarlama!)
    - 🚨 **JURIDICAL BOILERPLATE REMOVAL (ULTRA STRICT)**: Aşağıdaki jenerik metinleri KESİNLİKLE SİL:
        - "Taksit sayısı ürün gruplarına göre yasal mevzuat çerçevesinde belirlenir."
        - "Bireysel kredi kartlarıyla gerçekleştirilecek basılı ve külçe altın, kuyum, telekomünikasyon, akaryakıt, yemek, gıda, kozmetik vb. harcamalarda taksit uygulanamaz."
        - "Yasal mevzuat gereği azami taksit sayısı..."
        - "Kampanya farklı kampanyalarla birleştirilemez."
    - ✅ SADECE SADECE KAMPANYAYA ÖZEL ŞARTLARI YAZ: "Maksimum 500 TL", "Harcama alt sınırı 2000 TL", "İade/İptal hariçtir".
    - Eğer tüm sayfa içeriği zaten bu 4 alanda varsa 'conditions' boş (boş liste) olabilir. Gereksiz kalabalık yapma.

7. **DATES**: 
    - Tüm tarihleri 'YYYY-MM-DD' formatında ver.
    - 🚨 YIL KURALI: Eğer yıl belirtilmemişse:
      * Bugünün tarihi: {current_date} (Yıl: {datetime.now().year}, Ay: {datetime.now().month})
      * Kampanya ayı < Bugünün ayı → Yıl: {datetime.now().year + 1}
      * Kampanya ayı >= Bugünün ayı → Yıl: {datetime.now().year}
    - Sadece bitiş tarihi varsa, başlangıç tarihi olarak bugünü ({current_date}) al.
    - 🚨 BULUNAMAYAN TARİH KURALI: Eğer metinde başlangıç veya bitiş tarihi AÇIKÇA BELİRTİLMEMİŞSE (veya süresiz vb. ise), o alanı KESİNLİKLE null olarak bırak. Asla bugünün tarihini tahmini olarak yazma. Uydurma tarih üretmek veya mevcut günün tarihini ezbere eklemek YASAKTIR.

8. **KATILIM (PARTICIPATION)**: 
    - 🚨 KRİTİK: SMS, Mobil, Uygulama, Katıl, Gönder gibi teknik katılım mekanizmalarını ara.
    - 🚨 ULTRA YASAK: "Hemen faydalanabilirsiniz", "Detayları inceleyin", "Mobil uygulama üzerinden katılabilirsiniz" gibi anlamsız/jenerik metinleri ASLA yazma.
    - Bulamadığında bankanın mobil uygulaması üzerinden katılımı vurgula (Örn: "BonusFlaş üzerinden Hemen Katıl butonuna tıklayarak katılın").
    - 🚨 ÖZEL: Eğer katılım için "Rezervasyon", "Axess POS terminali" gibi teknik bir şart varsa bunu 'participation' alanına yaz.
    - 🚨 DOĞRULAMA: İş Bankası için ASLA "World Mobil" yazma, "Maximum Mobil" olarak düzelt. Akbank için "Jüzdan", Garanti için "BonusFlaş", Yapı Kredi için "World Mobil" ifadelerini doğrula.
    - Varsa tam talimatı yaz: "KAZAN yazıp 4455'e SMS gönderin" veya "Maximum Mobil üzerinden Hemen Katıl butonuna tıklayın".

9. **REWARD_TEXT**: 
    - 🚨 ASLA YAZMA: "Detayları İnceleyin", "Hemen Faydalanın" gibi jenerik ifadeler yasaktır. 
    - 🚨 SOURCE PRIORITY: Ödül metin içinde yoksa MUTLAKA BAŞLIKTAN (TITLE) çıkar (Örn: "3 Taksit", "%20 İndirim"). 
    - Hiçbir somut değer bulamazsan "Kampanya Fırsatı" yaz.

10. **PAZARLAMA ÖZETİ (MARKETING TEXT)**:
    - 'ai_marketing_text' alanı için: Kampanyanın avantajını özetleyen, kullanıcıyı heyecanlandıran, enerjik ve samimi bir metin oluştur.
    - 🚨 UZUNLUK: Mutlaka 2-3 cümle olmalı (en az 150, en fazla 300 karakter).
    - 🚨 EMOJİ KURALI: Cümlelerin arasına ve sonuna uygun emojiler ekle (🎉, 🚀, 💳, 🛒, ✈️, ⛽, 🍕 gibi kampanya konusuyla ilgili emojiler).
    - 🚨 DİL: Enerjik, davetkar ve heyecan verici ol. "Kaçırmayın!", "Fırsatı yakalayın!", "Hemen katılın!" gibi ifadeler kullan.
    - 🚨 İÇERİK: Somut rakamları (TL, puan, %, taksit sayısı) mutlaka belirt. Jenerik cümleler YASAK.
    - Örnek: "Manisa, Çanakkale, Muğla ve Uşak'ta TROY logolu QNB kartınızla toplu taşımada ilk yolculuğunuz tamamen ücretsiz! 🚌💳 Hafta içi binek ulaşımınızı QNB karşılıyor, bu fırsatı sakın kaçırmayın! 🎉"

11. **HARCAMA-KAZANÇ KURALLARI (MATHEMATIC LOGIC)**:
    - `reward_value`: Harcanması gereken miktar veya kazanılacak miktar değil, sadece KAZANILAN sayısal NET DEĞER (örn: 100, 150). Sadece float olmalı.
    - `min_spend`: Gereken minimum harcama tutarı. Yoksa 0.0.

12. **MARKA (BRANDS) ETİKETLEME - 🚨 KATI KURALLAR (SMART GUARD V4.9)**:
    - ⛔ NEGATION TRAP (HAYATİ): Eğer bir marka isminin yakınlarında "dahil değildir", "hariçtir", "geçerli değildir", "kapsam dışıdır" ibaresi geçiyorsa o markayı ASLA 'brands' listesine EKLEME. (Örn: "Google, Facebook, SGK ödemeleri dahil değildir" -> Bunlar ASLA marka olamaz).
    - ⛔ ILLUSION TRAP: Kampanyanın en altındaki "Benzer Fırsatlar", "İlginizi çekebilecek diğer kampanyalar" veya "Sizin için seçtiklerimiz" gibi başlıkların altındaki markaları ASLA 'brands' listesine EKLEME.
    - ⛔ APP/PAYMENT TRAP: Ödeme/Uygulama aracıları marka DEĞİLDİR. "Hepsipay", "Vodafone Yanımda", "Maximum Mobil", "Jüzdan", "GarantiPay", "Passo", "Privia" gibi banka veya cüzdan kelimelerini ASLA marka listesine ekleme. Sadece ana kurum (Örn: Vodafone) markadır.
    - ⛔ PUBLIC/GOVERNMENT TRAP: "SGK", "GİB", "Gelir İdaresi", "Duty Free" gibi devlet veya genel şemsiye kurumları marka DEĞİLDİR. ASLA ekleme.
    - ✅ INCLUSION OVERRIDE: Sadece bağlamda açıkça "geçerlidir" veya "dahildir" denen GERÇEK/TİCARİ mağaza ve site markalarını (Trendyol, İpekyol, Avva vb.) listeye dahil et.

  "reward_value": 0.0,
  "reward_type": "puan/indirim/taksit/mil",
  "reward_text": "150 TL Puan",
  "min_spend": 0.0,
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "sector": "Sektör Slug'ı",
  "brands": ["Marka1", "Marka2"], // 🚨 KATI KURAL: Sadece geçerli, kısıtlanmamış ana markaları yaz. SGK, Youtube, Privia, Hepsipay yasak.
  "cards": ["Kart1", "Kart2"],    // 🚨 METİNE HARFİYEN SADIK KAL: Sadece metinde birebir okuduğun kart isimlerini yaz.
 
JSON Formatı:
{{
  "title": "Kısa ve çarpıcı başlık",
  "description": "2 cümlelik detaylı açıklama metni",
  "ai_marketing_text": "2-3 cümlelik enerjik, emojili pazarlama özeti",
  "reward_value": 0.0,
  "reward_type": "puan/indirim/taksit/mil",
  "reward_text": "150 TL Puan",
  "min_spend": 0.0,
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "sector": "Sektör Slug'ı",
  "brands": ["Marka1", "Marka2"],
  "cards": ["Kart1", "Kart2"], // 🚨 METİNE HARFİYEN SADIK KAL: Sadece metinde birebir okuduğun kart isimlerini veya kategorilerini yaz. Hiçbir ismi standartlaştırma veya başka bir isme çevirme.
  "participation": "Katılım talimatı (SMS/App)",
  "conditions": ["Madde 1", "Madde 2"] // 🚨 ASLA madde işareti (- , * , •) kullanma, sadece metni yaz.
}}

ANALİZ EDİLECEK METİN:
"{cleaned_text}"
"""
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from AI response — handles extra data after JSON"""
        # Find the first '{' and count brackets to find matching '}'
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
        
        json_str = text[start:end + 1]
        return json.loads(json_str)
    
    def _get_last_day_of_month(self, date_obj: datetime) -> datetime:
        """Helper to get the last day of the month for a given date."""
        import calendar
        last_day = calendar.monthrange(date_obj.year, date_obj.month)[1]
        return date_obj.replace(day=last_day)

    def _normalize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize and validate parsed data"""
        
        def _to_clean_string(val: Any, separator: str = "\n") -> str:
            if not val: return ""
            if isinstance(val, list):
                # Filter out empty/nulls and join with specified separator
                items = [str(x).strip() for x in val if x]
                return separator.join(items) if len(items) > 1 else (items[0] if items else "")
            return str(val).strip()

        def _to_clean_list(val: Any) -> list:
            """Always return a list. If val is already a list, clean it. If string, wrap in list."""
            if not val:
                return []
            
            # Regex to strip leading bullets like "-", "•", "*", "1.", etc.
            bullet_pattern = re.compile(r'^[\s\-_•*\\.]+')

            if isinstance(val, list):
                cleaned_list = []
                for x in val:
                    if x and str(x).strip():
                        # Strip leading bullets and whitespace
                        cleaned_item = bullet_pattern.sub('', str(x).strip()).strip()
                        if cleaned_item:
                            cleaned_list.append(cleaned_item)
                return cleaned_list
            
            # val is a string — wrap as single-item list
            cleaned = str(val).strip()
            if cleaned:
                cleaned = bullet_pattern.sub('', cleaned).strip()
            return [cleaned] if cleaned else []

        # Get dates
        parsed_start = self._safe_date(data.get("start_date"))
        parsed_end = self._safe_date(data.get("end_date"))
        
        # Fallback Logic (Madde 1, 2, 3)
        now = datetime.now()
        if not parsed_start and not parsed_end:
            # 1. Tarih hiç yok ise
            parsed_start = now.strftime("%Y-%m-%d")
            parsed_end = self._get_last_day_of_month(now).strftime("%Y-%m-%d")
        elif not parsed_start and parsed_end:
            # 2. başlangıc tarihi yok-bitiş tarihi var ise
            parsed_start = now.strftime("%Y-%m-%d")
        elif parsed_start and not parsed_end:
            # 3. başlangıc tarihi var-bitiş tarihi yok ise
            try:
                start_dt = datetime.strptime(parsed_start, "%Y-%m-%d")
                parsed_end = self._get_last_day_of_month(start_dt).strftime("%Y-%m-%d")
            except:
                parsed_end = self._get_last_day_of_month(now).strftime("%Y-%m-%d")

        normalized = {
            "title": data.get("title") or "Kampanya",
            "description": data.get("description") or "",
            "ai_marketing_text": data.get("ai_marketing_text") or "",
            "reward_value": self._safe_decimal(data.get("reward_value")),
            "reward_type": data.get("reward_type"),
            "reward_text": data.get("reward_text") or "Kampanya Fırsatı",
            "min_spend": self._safe_int(data.get("min_spend")),
            "start_date": parsed_start,
            "end_date": parsed_end,
            "sector": data.get("sector") or "Diğer",
            "brands": data.get("brands") or [],
            "cards": _to_clean_list(data.get("cards")),
            "participation": _to_clean_string(data.get("participation")),
            "conditions": _to_clean_list(data.get("conditions"))
        }
        
        return normalized

    def _validate_cards_against_text(self, cards: list, clean_text: str) -> list:
        """
        Card Hallucination Guard — Verifies each card name AI returned actually
        appears in the clean_text. Removes hallucinated card names.
        """
        if not clean_text or not cards:
            return cards
        
        # Normalize ampersand AND Turkish characters for comparison
        def _normalize(s: str) -> str:
            """Normalize all '&' variants and turkish characters."""
            s = s.lower().replace("&", " & ").replace("  ", " ")
            # Basic Turkish normalization for case-insensitive match
            s = s.replace('ı', 'i').replace('ş', 's').replace('ğ', 'g').replace('ü', 'u').replace('ö', 'o').replace('ç', 'c')
            return s.strip()
        
        text_normalized = _normalize(clean_text)
        
        validated = []
        rejected = []
        
        passthrough_terms = {
            "tüm kartlar", "tüm kredi kartları", "tüm banka kartları", "tüm müşteriler",
            "sanal ve ek kartlar", "sanal kartlar", "ek kartlar",
            "türk telekom müşterileri", "vodafone müşterileri", "turkcell müşterileri", "bireysel müşteriler", "faturalı müşteriler"
        }
        
        for card in cards:
            card_orig = card
            card_norm = _normalize(card)
            
            # Pass through generic terms
            if card_norm in passthrough_terms:
                validated.append(card_orig)
                continue
            
            # Strategy 1: Direct substring match in normalized text
            if card_norm in text_normalized:
                validated.append(card_orig)
                continue
            
            # Strategy 2: Core word matching in normalized text
            # Strategy 2: Core word matching in normalized text
            stop_words = {"ve", "ile", "için", "&", "and", "the", "logolu"}
            core_words = []
            for w in card_norm.split():
                if len(w) > 2 and w not in stop_words:
                    if w == 'karti':
                        w = 'kart' # Lenient match for 'Kart ınızla' OCR errors
                    core_words.append(w)
            
            if not core_words:
                rejected.append(card_orig)
                continue
            
            # All core words must appear in normalized text
            if all(w in text_normalized for w in core_words):
                validated.append(card_orig)
            else:
                rejected.append(card_orig)
        
        if rejected:
            print(f"   🛡️ Card Guard: Rejected {rejected} (not found in clean_text)")
            
        # Ziraat Specific Overrides (Card Sniper)
        # If AI misses Bankkart variations due to model intelligence stripping them, we strictly enforce them reading the raw text.
        if "bankkart" in text_normalized:
            if "basak" in text_normalized and "bankkart basak" in text_normalized and not any("basak" in _normalize(c) for c in validated):
                validated.append("Bankkart Başak")
                print("   🎯 Card Sniper: Restored 'Bankkart Başak'")
            if "genc" in text_normalized and "bankkart genc" in text_normalized and not any("genc" in _normalize(c) for c in validated):
                validated.append("Bankkart Genç")
                print("   🎯 Card Sniper: Restored 'Bankkart Genç'")
            if "business" in text_normalized and "bankkart business" in text_normalized and not any("business" in _normalize(c) for c in validated):
                validated.append("Bankkart Business")
                print("   🎯 Card Sniper: Restored 'Bankkart Business'")
        
        return validated

    def _tr_lower(self, text: str) -> str:
        """Turkish-aware lowering of strings."""
        if not text: return ""
        return text.replace('İ', 'i').replace('I', 'ı').lower()

    def _validate_brands_against_text(self, brands: list, clean_text: str, title: str) -> list:
        """
        Brand Hallucination Guard V4.5 — Precision Mode.
        1. Title Guard (Turkish-aware): Brands in title are always safe.
        2. Happy Center Guard: Prevent mis-tagging 'Happy Card' as 'Happy Center'.
        3. Partial Exclusion Guard: Don't exclude brand if only 'belirli ürünler' are excluded.
        4. Contextual Negation: 100-char window check in sentences.
        """
        if not brands:
            return brands
            
        validated = []
        rejected = []
        
        full_context_lower = self._tr_lower((clean_text or "") + " " + (title or ""))
        
        # Enhanced normalization for Title Guard (ignore symbols like ® or ™)
        def _strip_symbols(t):
            return re.sub(r"[^a-z0-9ıişğüç ]", " ", t) 
            
        title_plain = _strip_symbols(self._tr_lower(title or ""))
        brand_plain_map = {} # Cache for plain brand names
        
        negation_keywords = ["dahil değildir", "hariçtir", "geçerli değildir", "kapsam dışıdır", "dahil edilmeyecektir", "sayılmamaktadır", "taksitlendirilmemektedir"]
        positive_keywords = ["geçerlidir", "dahildir", "geçerli olacaktır"]
        PARTIAL_EXCLUSION_WORDS = ["belirli", "seçili", "bazı", "haricindeki", "dışındaki", "markalı", "kategorisindeki"]
        NOISE_MARKERS = [
            r"ilginizi çekebilecek diğer kampanyalar", 
            r"benzer fırsatlar", 
            r"benzer kampanyalar", 
            r"diğer kampanyalar", 
            r"sizin için seçtiklerimiz"
        ]
        
        # Load blocklist
        matcher_blocklist = set()
        db = SessionLocal()
        try:
            from .point_blank_matcher import get_point_blank_matcher
            matcher = get_point_blank_matcher(db)
            matcher_blocklist = matcher.blocklist
        except: pass
        finally: db.close()

        for brand in brands:
            if not brand or len(brand) < 2: continue
            brand_norm = self._tr_lower(brand)
            brand_plain = _strip_symbols(brand_norm)
            
            # --- 1. TITLE & BLOCKLIST GUARD (V4.8: Symbol-Insensitive) ---
            # If brand (even without symbols) is in title (even without symbols), PROTECT IT.
            if brand_plain in title_plain or brand_norm in title_plain:
                validated.append(brand)
                continue
            
            if brand in matcher_blocklist or brand_norm == "mercedescard":
                rejected.append(brand)
                continue
            
            # --- 2. HAPPY CENTER SPECIAL GUARD ---
            if brand_norm == "happy center":
                if not re.search(r"(?i)\bcenter\b", full_context_lower):
                    if re.search(r"(?i)\bhappy\b", full_context_lower):
                        rejected.append(brand)
                        print(f"   🛡️ Happy Guard: Rejected '{brand}' (only 'Happy' found)")
                        continue

            # --- 3. ILLUSION (RECLAM) CHECK ---
            is_illusion = False
            for marker_pat in NOISE_MARKERS:
                match = re.search(marker_pat, full_context_lower, re.IGNORECASE)
                if match:
                    marker_pos = match.start()
                    # If brand is only found AFTER this position in main context
                    # (and NOT in title or before position)
                    brand_pat = rf"(?i)\b{re.escape(brand_norm)}\b"
                    found_before = re.search(brand_pat, full_context_lower[:marker_pos])
                    found_after = re.search(brand_pat, full_context_lower[marker_pos:])
                    
                    if found_after and not found_before and brand_norm not in title_plain:
                        is_illusion = True
                        break
            
            if is_illusion:
                rejected.append(brand)
                print(f"   🛡️ Illusion Guard: Rejected '{brand}' (Found only in related offers)")
                continue
                
            # --- 4. CONTEXTUAL CHECK (V4.9 Smart Guard) ---
            # Negation/Inclusion is now STRICTLY handled by the AI Prompt (Smart Guard).
            # This Python layer only ensures the brand actually exists in the raw text.
            
            def _clean_ws(t):
                return re.sub(r"\s+", " ", t).strip()
                
            clean_context = _clean_ws(full_context_lower)
            clean_brand = _clean_ws(brand_norm)

            if clean_brand in clean_context:
                validated.append(brand)
            else:
                rejected.append(brand)
                
        if rejected:
            print(f"   🛡️ Brand Guard: Rejected {rejected}")
            
        return validated

    def _safe_decimal(self, value: Any) -> Optional[float]:
        """Safely convert to decimal"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert to integer"""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    def _safe_date(self, value: Any) -> Optional[str]:
        """Safely validate date string"""
        if not value:
            return None
        
        # Check if it's already in YYYY-MM-DD format
        if isinstance(value, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', value):
            return value
        
        return None
    
    def _get_fallback_data(self, title: str) -> Dict[str, Any]:
        """Return fallback data if AI parsing fails — marked with _ai_failed=True"""
        return {
            "_ai_failed": True,         # ← scrapers use this to skip saving
            "title": title or "Kampanya",
            "description": "",
            "reward_value": None,
            "reward_type": None,
            "reward_text": "",
            "min_spend": None,
            "start_date": None,
            "end_date": None,
            "sector": "Diğer",
            "brands": [],
            "cards": [],
            "participation": "",
            "conditions": []
        }


# Singleton instance
_parser_instance = None


def get_ai_parser() -> AIParser:
    """Get singleton AI parser instance"""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = AIParser()
    return _parser_instance


def parse_campaign(raw_text: str, title: Optional[str] = None, bank_name: Optional[str] = None, card_name: Optional[str] = None, tracking_url: Optional[str] = None, force: bool = False, campaign_id: Optional[int] = None) -> Dict:
    """
    Main entry point for AI parsing.
    """
    parser = get_ai_parser()
    return parser.parse_campaign_data(raw_text, title, bank_name, card_name, tracking_url, force, campaign_id)


def parse_api_campaign(
    title: str,
    short_description: str,
    content_html: str,
    bank_name: Optional[str] = None,
    scraper_sector: Optional[str] = None,
    tracking_url: Optional[str] = None,
    force: bool = False
) -> Dict[str, Any]:
    """
    API-First Lightweight Parser.
    ...
    Args:
        scraper_sector: Optional sector hint from bank website/API (will be mapped to our 18 sectors)
        tracking_url: URL to check in cache (Madde 1)
        force: If True, skip cache and force AI call
    """
    parser = get_ai_parser()

    # 1. Check Cache
    if tracking_url and not force:
        cached = parser._check_db_cache(tracking_url)
        if cached:
            # Type-safe slicing for linter
            safe_url = str(tracking_url)
            print(f"   ✨ Using cached AI data for API campaign: {safe_url[:60]}...")  # type: ignore
            return cached
    
    # Clean HTML tags from content to get plain text conditions
    import re as _re
    import html as _html
    
    # 1. Strip script and style tags WITH their content (to remove GTM, CSS noise)
    content_html = content_html or ''
    temp_content = _re.sub(r'<script.*?>.*?</script>', ' ', content_html, flags=_re.DOTALL | _re.IGNORECASE)
    temp_content = _re.sub(r'<style.*?>.*?</style>', ' ', temp_content, flags=_re.DOTALL | _re.IGNORECASE)
    
    # 2. Strip all other tags
    clean_content = _re.sub(r'<[^>]+>', '\n', temp_content)
    
    # 3. Decode HTML entities (fix &#x2019; etc)
    clean_content = _html.unescape(clean_content)
    
    clean_content = _re.sub(r'\n+', '\n', clean_content).strip()
    # Limit content length
    # For Garanti BBVA, we need more context (sidebar info often gets cut off)
    # User requested no limit for Garanti
    limit = 25000 if bank_name == "Garanti BBVA" else 6000
    
    if len(clean_content) > limit:
        clean_content = str(clean_content)[:limit] # type: ignore
        
    clean_text = clean_content
    
    # Get bank-specific rules
    bank_instructions = ""
    if bank_name:
        bank_name_lower = bank_name.lower()
        for bank_key, rules in BANK_RULES.items():
            if bank_key in bank_name_lower:
                bank_instructions = rules
                break
    
    today = datetime.now()
    current_date = today.strftime("%Y-%m-%d")
    
    # Add scraper sector hint if available
    sector_hint = ""
    if scraper_sector and scraper_sector.strip():
        sector_hint = f"""
🎯 SEKTÖR İPUCU (Banka Sitesinden):
Banka bu kampanyayı "{scraper_sector}" kategorisinde gösteriyor.
Bu ipucunu kullanarak aşağıdaki VALID SECTORS listesinden EN UYGUN olanı seç.
"""
    
    prompt = f"""Sen uzman bir kampanya analistisin. Aşağıdaki kampanya bilgilerini analiz et.
Bugünün tarihi: {current_date} (Yıl: {today.year})

{bank_instructions}

{sector_hint}

VALID SECTORS (BİRİNİ SEÇ — SADECE bu slug listeden):
- market-gida
- akaryakit
- giyim-aksesuar
- restoran-kafe
- elektronik
- mobilya-dekorasyon
- kozmetik-saglik
- e-ticaret
- ulasim
- dijital-platform
- kultur-sanat
- egitim
- sigorta
- otomotiv
- vergi-kamu
- turizm-konaklama
- kuyum-optik-ve-saat
- fatura-telekomunikasyon
- anne-bebek-oyuncak
- kitap-kirtasiye-ofis
- evcil-hayvan-petshop
- hizmet-bireysel-gelisim
- finans-yatirim
- diger

⚠️ ÖNEMLİ: Sektör değerini AYNEN yukarıdaki slug listeden seç. Türkçe isim yazma!
   ✅ DOĞRU: "ulasim"
   ❌ YANLIŞ: "Ulaşım"


KURALLAR:
1. short_title: Başlığı KISA ve ÇARPICI hale getir. Kartlarda 2 satır dolduracak uzunlukta (40-70 karakter).
   ❌ Çok kısa / Yanlış: Sadece marka ismi ("D&R" veya "Market Fırsatı")
   ✅ İdeal: "D&R'da 150 TL'ye Varan İndirim!" veya "Market Alışverişinde 300 TL Puan!"
   ❌ Çok uzun: "Yapı Kredi Play ile her 300 TL ve üzeri market alışverişlerinde 60 TL puan" (3+ satır)
2. description: 2 cümlelik, samimi ve teşvik edici pazarlama metni. Kullanıcıyı kampanyaya katılmaya ikna etmeli.
3. reward_value: Sayısal değer. "75 TL" → 75.0, "%20" → 20.0
4. reward_type: "puan", "indirim", "taksit", veya "mil"
5. reward_text: Kısa ve çarpıcı. "75 TL Worldpuan", "%20 İndirim", "300 TL'ye Varan Puan"
6. sector: VALID SECTORS slug listesinden seç (örn: "ulasim", "market-gida").
7. brands: Metinde geçen dış marka isimlerini çıkar (ör. Trendyol, Migros). Asla Garanti BBVA, İş Bankası gibi banka adlarını yazma! Eğer ortada harici bir marka yoksa (kredi, nakit avans, otomatik fatura, ek taksit gibi bankanın genel bir kampanyasıysa) SADECE [] yaz.
8. conditions: Koşulları kısa maddeler halinde özetle (max 5 madde). 
   🚨 🚨 **ULTRA KRİTİK - YASAK**: Aşağıdaki bilgileri 'conditions' içine yazmak KESİNLİKLE YASAKTIR:
   - **Participation (Katılım)**: "Hemen Katıl butonuna tıklayın", "SMS gönderin" gibi katılım adımlarını ASLA burada tekrarlama. Bunlar sadece `participation` alanında olmalı.
   - **Cards (Kartlar)**: Dahil/geçerli kart isimlerini burada tekrarlama. Sadece `cards` alanında olmalı.
   - **Dates (Tarihler)**: "Şu tarihler arasında" gibi bilgileri tekrarlama. Sadece `start_date` ve `end_date` alanlarında olmalı.
   - ✅ SADECE teknik kuralları yaz: "Harcama alt sınırı", "Maksimum ödül limitleri", "İade/iptal durumları" vb.
9. cards: 🚨 METİNE HARFİYEN SADIK KAL: SADECE metinde birebir okuduğun kart isimlerini veya özel kategorilerini yaz. Metinde "Paraf, Parafly, Paraf Business" yazıyorsa AYNEN ["Paraf", "Parafly", "Paraf Business"] listele. Metinde "Ticari" geçiyorsa "Ticari" yaz. Hiçbir ismi standartlaştırma veya başka bir isme çevirme! Varsayım yapma, uydurma!
10. participation: 🚨 KRİTİK — Detay İçerik'te "SMS", "4454", "Mobil", "Katıl", "Jüzdan", "World Mobil", "ON Mobil" gibi ifadeleri ARA.
   - Katılım adımlarını buraya açık ve net yaz. Örn: "ON Mobil üzerinden Hemen Katıl butonuna tıklayarak katılın."
   - SMS varsa: "KEYWORD yazıp NUMARA'ya SMS gönderin" formatında yaz.
   - Mobil uygulama varsa: "World Mobil uygulamasından Kampanyalar bölümünde Katıl butonuna tıklayın" yaz.
   - Her ikisi de varsa: "World Mobil'den Katıl butonuna tıklayın veya KEYWORD yazıp NUMARA'ya SMS gönderin" yaz.
   - Hiçbiri yoksa: "Otomatik katılım" yaz.
10. dates: Metinde geçen başlangıç ve bitiş tarihlerini bul. Format: "YYYY-MM-DD". Bulamazsan null yap. 🚨 EĞER TARİHLER AÇIKÇA YOKSA ASLA BUGÜNÜN TARİHİNİ (<current_date>) KULLANMA. UYDURMA YASAKTIR. KESİNLİKLE `null` OLARAK BIRAK.

KAMPANYA BİLGİLERİ:
Başlık: "{title}"
Açıklama: "{short_description}"
Detay İçerik:
{clean_content}

JSON olarak cevap ver:
{{
  "short_title": "40-70 karakter kısa başlık",
  "description": "2 cümlelik pazarlama metni",
  "reward_value": 0.0,
  "reward_type": "puan/indirim/taksit/mil",
  "reward_text": "Kısa ödül metni",
  "sector": "slug-format",
  "brands": [],
  "conditions": ["Madde 1", "Madde 2"],
  "cards": ["Kart1"],
  "participation": "Katılım talimatı",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD"
}}}}"""
    
    try:
        result_text = parser._call_ai(prompt, timeout_sec=65)
        json_data = parser._extract_json(result_text)
        
        # Map fields for normalization
        if "short_title" in json_data and not json_data.get("title"):
            json_data["title"] = json_data["short_title"]
        
        # If AI didn't return a description, use the one passed to the function
        if not json_data.get("description"):
            json_data["description"] = short_description

        # Use the central normalization logic (Safe Dates, Fallbacks, etc.)
        normalized = parser._normalize_data(json_data)
        
        # --- Card Hallucination Guard ---
        if normalized.get("cards") and clean_content:
            normalized["cards"] = parser._validate_cards_against_text(
                normalized["cards"], clean_content
            )
            
        # --- Brand Hallucination Guard ---
        if normalized.get("brands"):
            normalized["brands"] = parser._validate_brands_against_text(
                normalized["brands"], clean_content, title
            )
        
        # INJECT cleaned text for scrapers to save
        normalized["_clean_text"] = clean_content
        
        # Ensure 'short_title' is available for consumers of this specific function
        if "short_title" in json_data:
            normalized["short_title"] = json_data["short_title"]
        elif "title" in normalized:
            normalized["short_title"] = normalized["title"]
            
        return normalized
    except Exception as e:
        print(f"API Parser Error: {e}")
        return {
            "_ai_failed": True,
            "title": title,
            "short_title": title,
            "description": short_description,
            "reward_value": None,
            "reward_type": None,
            "reward_text": "",
            "sector": "Diğer",
            "brands": [],
            "conditions": [],
            "cards": [],
            "participation": "",
            "start_date": None,
            "end_date": None
        }
