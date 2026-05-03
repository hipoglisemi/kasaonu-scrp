"""
Bank-specific prompt instructions for AI parsers.
Extracted securely from legacy AI parser to decouple Golden V3 from legacy systems.
"""

BANK_RULES = {
    'akbank': """
AKBANK SPECIFIC RULES:
- TERMINOLOGY: 
    - For Axess/Free/Akbank Kart: Uses "chip-para" instead of "puan". 1 chip-para = 1 TL.
    - For Wings: Uses "Mil" or "Mil Puan". 100 Mil Puan = 1 TL (domestic) / 2 TL (int).
- PARTICIPATION: Primary method is "Jüzdan" app. Always look for "Jüzdan'dan Hemen Katıl" button. If not found, look for "Akbank Axess POS" instructions.
- SMS: Usually 4566. SMS keyword is usually a single word (e.g., "A101", "TEKNOSA").
- REWARD: If it says "8 aya varan taksit", it's an installment campaign. Earning: "Taksit İmkanı". ASLA "Detayları İnceleyin" yazma.
- ELIGIBLE CARDS:
    - RAW EXTRACTION (LITERAL): Extract the EXACT card names or categories from the text. 
    - NO MAPPING: If text says "Ticari kartlar", write "Ticari kartlar". If it says "Bank'O Card Axess", write "Bank'O Card Axess".
    - TITLE TRAP: Even if title says "Axess'e Özel", check footer for "Axess, Wings, Free... dahildir".
    - KESIN YASAK: Asla "Kampanyaya Dahil Kartlar" yazma.
    - KESIN YASAK: Kart isimlerini asla 'conditions' (koşullar) listesine yazma. Sadece 'cards' alanına yaz.
- AKBANK REDUNDANCY ALERT (CRITICAL):
    - Akbank metinleri tarih ve kart bilgisini çok tekrar eder. 
    - 'conditions' listesine ASLA "1-31 Mart", "Axess kart", "Jüzdan" gibi bilgileri yazma.
    - Koşullar SADECE teknik kurallar içermeli (örn: "POS terminali zorunluluğu", "İndirim limiti").
- PARTICIPATION (REDUNDANCY):
    - YASAK: "Juzdan uygulama üzerinden katılabilirsiniz." gibi jenerik metinleri tek başına yazma. Eğer butonda "Hemen Katıl" yazıyorsa "Juzdan'dan Hemen Katıl butonuna tıklayın" gibi somutlaştır.
""",
    'albaraka': """
ALBARAKA SPECIFIC RULES:
- TERMINOLOGY: Uses "Worldpuan". 1 Worldpuan = 0.01 TL (if value is given in TL, use "TL Worldpuan").
- APP CONSTRAINT (CRITICAL): Primary and ONLY app is **"Albaraka Mobil"**. 
    - HALUSINASYON YASAGI: Asla "World Mobil" veya "Yapı Kredi Mobil" yazma. Albaraka kampanya metinlerinde "World" geçse bile uygulama adı Albaraka Mobil'dir.
- PARTICIPATION (katilim_sekli):
    - Look for "Albaraka Mobil > Kampanyalar > Katıl/Kod Al".
    - Extract as: "Albaraka Mobil uygulamasındaki Kampanyalar menüsünden katılabilirsiniz."
- ELIGIBLE CARDS:
    - "Albaraka Worldcard", "Albaraka Banka Kartı".
    - Variants: "Trend Bankacılık" (Genç), "Özel Bankacılık" (Elite), "Eflatun Bankacılık".
    - KESIN YASAK: Sanal kartlar, Ek kartlar ve Business (Ticari) kartlar aksi belirtilmedikçe dahil değildir.
- CONDITIONS: 
    - "Kod Al" gereken kampanyalarda bu şartı belirt.
    - Harcama limitlerini ve müşteri segmenti (örn: "Yeni görüntülü görüşme ile müşteri olanlar") detaylarını ekle.
""",
    'yapı kredi': """
YAPI KREDI (WORLD) SPECIFIC RULES:
- TERMINOLOGY: "Worldpuan" is the currency.
    - IMPORTANT: "TL Worldpuan" means the value is in TL. If it says "100 TL Worldpuan", earning is "100 TL Worldpuan".
- ELIGIBLE CARDS (cards):
    - RAW EXTRACTION (LITERAL): Extract the EXACT card names or common categories from the text.
    - Metinde ne geçiyorsa aynen al: "Worldcard", "Yapı Kredi Kredi Kartları", "Mastercard logolu kartlar", "Business", "World Eko", "Adios" vb.
    - NO DEFAULTING: If the text says "Mastercard", write "Mastercard". DO NOT write "Worldcard" unless it's in the text.
- PARTICIPATION (katilim_sekli):
    - EXTRACTION RULE: Extract exactly what is found in the text. DO NOT use generic templates.
    - APP: Look for "World Mobil" or "Yapı Kredi Mobil" and "Hemen Katıl" instructions.
    - SMS: Look for keyword + **"4454"** shortcode.
    - NO SMS HALLUCINATION: If the text doesn't mention 4454 or an SMS keyword, write "Otomatik katılım" or detail the App instructions. NEVER invent SMS keywords.
- REDUNDANCY ALERT: DO NOT repeat card names, dates, or participation instructions in 'conditions'.
""",
    'garanti': """
GARANTI BBVA SPECIFIC RULES:
- ELIGIBLE CARDS (cards):
    - 🚨 **KESİN TALİMAT**: Metinde "Kampanyaya Dahil Kartlar:" başlığından sonra gelen kart listesini harfi harfine kopyala. 
    - "Garanti Bonus kredi kartları" yazıyorsa onu "Bonus" olarak kısaltma, aynen "Garanti Bonus kredi kartları" yaz.
    - "Money Bonus" ve "Flexi Bonus Genç" gibi isimleri asla atlama.
    - Metindeki her bir kelimeyi (örn: "sanal", "ek", "asıl") kart isminin bir parçası olarak kabul et ve aynen yaz.
- PARTICIPATION: "BonusFlaş" app is primary. Look for "HEMEN KATIL" instructions.
""",
    'american express': """
AMERICAN EXPRESS SPECIFIC RULES:
- ELIGIBLE CARDS (cards):
    - RAW EXTRACTION (LITERAL): Metinde geçen kart isimlerini aynen al.
    - HICBIRINI ELEME: "American Express Card", "American Express Gold Card", "American Express Platinum Card", "Metal The Platinum Card", "Centurion Card" isimlerini tek tek yaz.
    - ONEMLI: "Asıl ve ek kartlar" ifadesi metinde geçiyorsa bunu da MUTLAKA kart listesine (cards) ekle.
    - NEGATIF: Eğer metinde bir kart için "dahil değildir" deniyorsa (Örn: American Express Business) o kartı ASLA listeye ekleme.
- PARTICIPATION: "BonusFlaş" app or SMS to 3340.
- CONDITIONS: Focus on minimum spend thresholds and specific exclusions (e.g. "KKTC harcamaları dahil değildir").
""",
    'işbankası': """
IS BANKASI/MAXIMUM/MAXIMİLES SPECIFIC RULES:
- TERMINOLOGY: "Maxipuan" (Points) or "MaxiMil" (Miles).
- ELIGIBLE CARDS (cards):
    - RAW EXTRACTION (LITERAL): Metinde ne yazıyorsa DIREKT ONU YAZ.
    - ONEMLI: "Sanal kartlar", "Ticari kartlar" vb. ifadeleri sadece **dahil/geçerli** oldukları belirtilmişse listeye ekle. Eğer "hariçtir" deniyorsa ASLA yazma.
    - Örnek: "İş Bankası Maximum özellikli kredi kartları (Maximum, Maximiles...)" yazıyorsa AYNEN AL.
    - KESIN YASAK: Fibabanka, Ziraat gibi diğer banka kartlarını ASLA YAZMA. Sadece İş Bankası kartlarını listele.
- PARTICIPATION (katilim_sekli):
    - PRIORITY ORDER:
      1. Primary App: Look for "Katıl" button in "Maximum Mobil", "İşCep" or "Pazarama". -> Extract as "Maximum Mobil, İşCep veya Pazarama'dan katılabilirsiniz."
      2. SMS: Look for "4402'ye SMS" -> Extract as "4402'ye [KEYWORD] yazıp SMS gönderin."
      3. Automatic: If "katılım gerektirmez" or "otomatik" -> Use "Otomatik Katılım".
      4. Fallback: If no button/SMS/app is mentioned but there is a clear instruction like "Kampanya detaylarını inceleyin", write exactly that instruction.
    - STRICT APP NAMES: ONLY use "Maximum Mobil", "İşCep", or "Pazarama".
    - NEGATIVE CONSTRAINT: NEVER use "World Mobil", "Jüzdan", "BonusFlaş", "Yapı Kredi". If you see these, it's a hallucination or cross-promotion; ignore them.
- DISCOUNT CODES: If there is an "İndirim Kodu" (e.g., TRBAN25, TROY2024), **MUTLAKA** both 'conditions' listesine ekle hem de 'description' içinde belirt.
- REDUNDANCY ALERT: DO NOT repeat card names, dates, or participation methods (e.g., Maximum Mobil, İşCep, Pazarama) in 'conditions'.
- CONDITIONS (SUMMARY MODE):
    - Maksimum 5-6 madde. Uzun yasal metinleri, tekrar eden kart bilgilerini ve işlem türü sayımlarını atlat.
    - ICERIK: Sadece şunları yaz:
      * Minimum harcama eşiği ("2.000 TL harcamaya 200 MaxiMil")
      * Maksimum kazanç limiti ("Maks. 1.500 MaxiMil")
      * Kampanya dışı işlem türleri ("Nakit çekim, havale, iptal/iade işlemleri hariçtir")
      * Hariç tutulan kart grupları ("Ticari Kredi Kartları kampanyaya dahil değildir")
    - YAZMA: Tarihleri, katılım yöntemini, zaten ayrı bir listede verdiğin dahil kart isimlerini tekrar YAZMA.
- BRANDS (SECTOR TAGGING):
    - ONEMLI: Kampanya belirli bir marka/zincir içinse (Zara, Emirates, Migros vb.) o marka ismini 'brands' listesine ekle.
    - Sektör için: "MaxiMil" -> Turizm veya Ulaşım olabilir (metne bak); "Duty Free" -> Turizm & Konaklama veya Ulaşım; "Pazarama" -> E-Ticaret.
""",
    'vakıfbank': """
VAKIFBANK/WORLD SPECIFIC RULES:
- TERMINOLOGY: "Worldpuan", "Bankomat Para". 1 Worldpuan/Bankomat Para = 0.005 TL.
- ELIGIBLE CARDS (cards):
    - STRICT RAW EXTRACTION: SADECE metinde açıkça DAHİL olduğu belirtilen kartları al.
    - HALLUCINATION PROHIBITION: Metinde "Platinum", "MilPlus", "Worldcard" kelimeleri geçmiyorsa ASLA uydurarak ekleme.
    - NEGATION TRAP: Metinde "VakıfBank Worldcard'lar ... dahil değildir" yazıyorsa, Worldcard'ı KESİNLİKLE listeye ekleme. Sadece "Bankomat Kart" ve "Sanal Bankomat Kartlar" geçiyorsa sadece onları yaz.
    - BANKOMAT EXCLUSIVITY: Eger kampanya bir "Bankomat Para" veya "Bankomat Kart" kampanyasi ise, cards listesine Worldcard, Platinum, MilPlus ekleme. Sadece "Bankomat Kart" yaz.

- DATE PROTECTION: "1-31 Mayıs 2026" gibi aralıkları (1 Mayıs başlangıç, 31 Mayıs bitiş) olarak işle.
- PARTICIPATION: "Cepte Kazan" (VakıfBank Mobil) uygulaması üzerinden "Hemen Katıl".
""",
    'ziraat': """
ZIRAAT BANKKART SPECIFIC RULES:
- TERMINOLOGY: "Bankkart Lira". 1 Bankkart Lira = 1 TL.
- ELIGIBLE CARDS:
    - STRICT LITERAL EXTRACTION: Extract ONLY the cards explicitly mentioned in the text.
    - RULE: If text says "Bankkart, Bankkart Genç ve Bankkart Başak", then use EXACTLY ["Bankkart", "Bankkart Genç", "Bankkart Başak"].
    - RULE: If text says "Taksit özelliği olan Bankkart ve Bankkart Başak", then use EXACTLY ["Bankkart", "Bankkart Başak"].
    - RULE: Check for "dahil değildir". "Bankkart Business" and "Ücretsiz" are usually EXCLUDED. Do not list excluded cards.
- PARTICIPATION:
    - SMS: Look for specific keywords (e.g., "SUBAT2500", "RAMAZAN", "MARKET") sent to **4757**.
    - App: "Bankkart Mobil", "bankkart.com.tr".
    - Format: "KEYWORD yazıp 4757'ye SMS gönderin" or "Bankkart Mobil uygulamasından katılın".
    - FALLBACK: If NO specific method (SMS/App) is found, and it seems like a general campaign (e.g., "İlk Kart", "Taksit"), assume "Otomatik Katılım".
- CONDITIONS:
    - FORMAT: SUMMARIZE into 5-6 clear bullet points.
    - CONTENT: MUST include numeric limits (max earners, min spend) and dates.
    - Avoid long paragraphs. Use concise language.
""",
    'kuveyt türk': """
KUVEYT TÜRK (SAĞLAM KART) SPECIFIC RULES:
- TERMINOLOGY: "Altın Puan". 1 Altın Puan = 1 TL.
- ELIGIBLE CARDS (cards):
    - STRICT: Extract all cards from the text (usually the 2nd bullet point in details).
    - Keywords: "Sağlam Kart", "Sağlam Kart Kampüs", "Sağlam Kart Genç", "Miles & Smiles Kuveyt Türk Kredi Kartı", "Özel Bankacılık World Elite Kart", "Tüzel Kartlar", "Sağlam Nakit Kart".
    - Include "sanal ve ek kartlar" if mentioned. 
- PARTICIPATION (katilim_sekli):
    - PRIORITY: Check for SMS keywords (e.g. "KATIL TROYRAMAZAN") and the short number (e.g. 2044).
    - Look for: "Cebim POS", "Sanal POS", "Mobil" instructions.
    - If "otomatik" or "katılım gerektirmez" is mentioned, use "Kampanya otomatik katılımlıdır."
    - FORMAT: Use specific instruction: "2044'e [KEYWORD] yazıp SMS göndererek veya Kuveyt Türk Mobil üzerinden Kampanyalar menüsünden katılabilirsiniz."
- CONDITIONS (conditions):
    - DETAYLI AMA NET: 'KOŞULLAR VE DETAYLAR' başlığı altındaki kritik maddeleri al.
    - TEMIZLIK: Tarih, kart listesi ve katılım yöntemini BURADA TEKRARLAMA. Sadece harcama sınırları, sektör kısıtlamaları ve hak kazanım detaylarını yaz.
""",
    'halkbank': """
HALKBANK (PARAF / PARAFLY) SPECIFIC RULES:
- TERMINOLOGY: "ParafPara". 1 ParafPara = 1 TL.
- ELIGIBLE CARDS (cards):
    - STRICT & EXHAUSTIVE: Metindeki kart listesinde geçen HER İSMİ tek tek al.
    - 🚨 ASLA ATLANMAYACAK KARTLAR: "Parafree", "Paraf Esnaf", "Paraf KOBİ", "Eczacı Paraf", "Eczacı Paraf KOBİ", "Paraf Business", "Sanal kartlar", "Ek kartlar".
    - Common INCLUSIONS: "Paraf", "Parafly", "Halkcard".
    - Exclusions: "Paraf Genç" ve "Debit kartlar" (Banka kartları) genellikle dahil değildir, metni dikkatli oku.
- PARTICIPATION (katilim_sekli):
    - PRIORITY ORDER:
      1. SMS: Look for "3404'e SMS" or "3404'e KEYWORD" -> Extract as "3404'e [KEYWORD] SMS"
      2. App: Look for "Paraf Mobil'den HEMEN KATIL" or "Halkbank Mobil'den katılın" -> Extract as "Paraf Mobil" or "Halkbank Mobil"
      3. Automatic: If "katılım gerektirmez" or "otomatik" -> Use "Otomatik Katılım"
    - FORMAT: "[KEYWORD] yazıp 3404'e SMS göndererek veya Paraf Mobil uygulamasından Hemen Katıl butonuna tıklayarak katılabilirsiniz."
- CONDITIONS: 3-5 concise bullet points focusing on spend limits and exclusions ONLY.
""",
    'denizbank': """
DENIZBANK (DENIZBONUS) SPECIFIC RULES:
- TERMINOLOGY: "Bonus". 1 Bonus = 1 TL.
- ELIGIBLE CARDS (cards):
    - RAW EXTRACTION (CRITICAL): Do NOT map cards to a fixed list. Extract the EXACT descriptive string from the text.
    - Examples: 
        * "Tüm bonus özellikli DenizBank Bireysel Kredi Kartları"
        * "DenizBank TROY logolu bireysel ve ticari kredi kartı, banka kartı ve ön ödemeli kartlar"
        * "Net Kart"
    - KESIN YASAK: Metinde geçmeyen kart isimlerini (DenizBonus Gold vb.) uydurma. Metinde ne yazıyorsa harfi harfine onu al.
- PARTICIPATION:
    - PRIORITY:
      1. App: "MobilDeniz" or "DenizKartım". Look for "Hemen Katıl" button.
      2. SMS: Look for keywords sent to **3280**. (e.g. "KATIL yazıp 3280'e gönder").
      3. Automatic: If "katılım gerekmemektedir" or "otomatik", use "Otomatik Katılım".
- CONDITIONS:
    - FORMAT: Summarize into 3-5 bullets.
    - Include: Max earning limit, start/end dates, valid sectors.
""",
    'qnb': """
QNB SPECIFIC RULES:
- TERMINOLOGY: "ParaPuan". 1 ParaPuan = 1 TL.
- ELIGIBLE CARDS:
    - Sitedeki kampanya metninde KAMPANYANIN GEÇERLİ OLDUĞU veya belirtilen işlemi YAPAN kart isimlerini (Örn: "QNB Kredi Kartı", "QNB Nakit banka kartı") BİREBİR ve EKSİKSİZ şekilde al. Metinde "QNB Kredi Kartı'nızla" diyorsa geçerli kart "QNB Kredi Kartı" dır.
    - KESIN YASAK: Eğer metinde bir kart için "dahil değildir", "hariçtir", "kazanamaz" deniyorsa (Örn: Ticari kartlar, QNB Fix, Miles&Smiles vb.) o kartı ASLA 'cards' listesine ekleme. Kendi kendine jenerik kart adı uydurma.
- PARTICIPATION:
    - Sitedeki metinde katılım için hangi yöntemler isteniyorsa HEPSİNİ eksiksiz yaz.
    - Eğer hem SMS (Örn: "ECROU yazıp 2273'e") hem Uygulama (Örn: "QNB Mobil'den HEMEN KATIL") varsa İKİSİNİ BİRDEN yaz. Öncelik sırası yoktur, metinde ne görüyorsan onu virgülle ayırarak/bağlaçla birleştirerek yaz.
- CONDITIONS:
    - Kampanyaya dair tüm önemli kuralları (ödülün verilme ve geri alınma tarihleri, taksit sayıları, alt limitler vb.) metinden birebir çıkarıp anlaşılır maddelere böl.
    - Uzunluk veya madde sayısı sınırı YOKTUR. Metindeki önemli hiçbir şart atlanmamalıdır.
""",
    'teb': """
TEB (TÜRK EKONOMİ BANKASI) SPECIFIC RULES:
- TERMINOLOGY: "Bonus". 1 Bonus = 1 TL. "TEB Bonus" is the reward program name.
- ELIGIBLE CARDS:
    - STRICT: Extract ONLY cards explicitly mentioned in the text.
    - Common cards: "TEB Kredi Kartı", "TEB Bonus Kart", "TEB Banka Kartı", "CEPTETEB".
    - "Bireysel kredi kartları" = ["TEB Kredi Kartı"].
    - EXCLUSION: "Ticari kartlar" are often EXCLUDED unless explicitly mentioned.
- PARTICIPATION:
    - PRIORITY ORDER:
      1. Campaign Code + SMS: If text contains "Kampanya Kodu: XXXXX" at the top, the participation is "XXXXX yazıp 5350'ye SMS gönderin."
      2. App: "TEB Mobil" or "CEPTETEB". Look for "Hemen Katıl" button.
      3. Checkout/Sepet: If text says "ödeme adımında ... seçin" or "sepet sayfasında" -> describe the checkout step.
      4. Automatic: ONLY if text explicitly says "katılım gerektirmez" or "otomatik".
    - NEGATIVE: Do NOT write "Otomatik Katılım" if there is a campaign code or any checkout instruction.
    - FORMAT: Be specific. Example: "MARKET2026 yazıp 5350'ye SMS gönderin veya TEB Mobil'den Hemen Katıl butonuna tıklayın."
- CONDITIONS:
    - CRITICAL: DO NOT repeat information already in dates, eligible cards, or participation sections.
    - FOCUS ON UNIQUE DETAILS ONLY:
      * Minimum spend thresholds (e.g. "Her 500 TL harcamaya 50 TL Bonus")
      * Maximum earning limits (e.g. "Maksimum 500 TL Bonus")
      * Excluded transaction types (e.g. "Nakit çekim, taksitli işlemler hariç")
      * Bonus loading timeline (e.g. "Bonus 30 gün içinde yüklenir")
    - FORMAT: 3-5 concise bullet points. NO long paragraphs.
    - AVOID: Repeating dates, card names, or SMS instructions already extracted.
""",
    'turkiye-finans': """
TÜRKİYE FİNANS (HAPPY CARD / ÂLÂ KART) SPECIFIC RULES:
- TERMINOLOGY: 
    - "Bonus": Used often for Happy Card (uses Bonus network). 1 Bonus = 1 TL.
    - "ParaPuan": Sometimes used. 1 ParaPuan = 1 TL.
- ELIGIBLE CARDS (cards):
    - STRICT: Extract ONLY cards mentioned.
    - Keywords: "Happy Card", "Happy Zero", "Happy Gold", "Happy Platinum", "Âlâ Kart", "Türkiye Finans Banka Kartı", "Hızır Kart".
    - If "Türkiye Finans Kredi Kartları" is mentioned, include ["Happy Card", "Âlâ Kart"].
    - KESIN YASAK: Diğer bankaların Bonus kartlarını listeye yazma.
- PARTICIPATION (katilim_sekli):
    - PRIORITY ORDER:
      1. SMS: Look for keyword + "2442" (e.g. "AYIN yazıp 2442'ye SMS”).
      2. App: "Mobil Şube" or "İnternet Şubesi". Look for "Kampanyalar" menu.
      3. Automatic: ONLY if "otomatik katılım" or if no SMS/App instruction exists AND text implies auto.
    - FORMAT: "[KEYWORD] yazıp 2442'ye SMS göndererek veya Türkiye Finans Mobil Şube üzerinden katılabilirsiniz."
""",
    "chippin": """
CHIPPIN SPECIFIC RULES:
- TERMINOLOGY:
    - "Chippuan": Reward currency. 1 Chippuan = 1 TL.
    - "Nakit İade": Cash back to credit card.
- ELIGIBLE CARDS: 
    - KESIN YASAK: Eğer metinde spesifik bir kart adı yoksa, 'cards' alanına "Chippin" yazıp geçme. 
    - DOGRUSU: "Chippin kullanıcıları" veya "Tüm kredi kartları" gibi bir ifade kullan veya sadece ["-"] bırak.
- PARTICIPATION:
    - PRIORITY ORDER:
      1. App Flow: "Chippin uygulamasından ödeme yapın", "Chippin ile öde" gibi mobil ödeme adımları.
      2. Automatic: "katılım gerektirmez", "şart koşul yoktur" yazıyorsa.
    - FORMAT VURGUSU: "Chippin uygulamasına ekli kredi kartınız ile Chippin'den ödeme yapmanız gerekmektedir."
- SECTOR CLASSIFICATION (ULTRA CRITICAL): 
    - 🚨 Chippin bir dijital platform DEĞİLDİR, sadece bir ödeme yöntemidir.
    - 🚨 Sektörü KESİNLİKLE 'dijital-platform' SEÇME.
    - 🚨 Harcamanın asıl YAPILDIĞI YERE odaklan: Eğer kampanya bir giyim mağazasında ise 'giyim-aksesuar', markette ise 'market-gida', akaryakıt istasyonunda ise 'akaryakit' sektörünü seç.
    - Chippin ödemesi yapılıyor olması sektörü değiştirmez.
- CONDITIONS:
    - Kampanyaya dahil olan MINIMUM harcama tutarını özellikle belirt ("Örn: 500 TL ve üzeri Chippin ödemelerinde").
    - Kampanya kazanımının ne zaman yatırılacağını belirt.
"""
}
