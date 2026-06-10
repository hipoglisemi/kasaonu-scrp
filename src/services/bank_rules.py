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
- ELIGIBLE CARDS (CRITICAL):
    - 🚨 **METNE SADIK SIRALI LİSTE**: Kart isimlerini metinde geçtiği sırayla, virgülle ayrılmış temiz bir liste olarak yaz. **SIRALAMAYI ASLA BOZMAYIN VE HİÇBİR MARKAYI ATLAMAYIN.**
    - 🚨 **TEMİZLEME KURALLARI**:
        - "Axess Bireysel kartlar" -> **Axess**
        - "Wings Bireysel kartlar" -> **Wings**
        - "Free Bireysel kartlar" -> **Free**
        - "Bireysel kredi kartları", "Bireysel kartlar", "Kredi kartları" ibarelerini TEMİZLE, sadece marka kalsın.
        - "Akbank Kart" ibaresini OLDUĞU GİBİ KORU (markadır).
        - "Ticari kartlar", "Ek kartlar", "Sanal kartlar" ibarelerini OLDUĞU GİBİ KORU. ("Ticari" olarak kısaltma yapma, tam yaz).
    - 💡 **ÖREK DÖNÜŞÜMLER**:
        - "Kampanyaya bireysel Wings kartlar ile ek kartlar dahildir" -> **Wings, Ek kartlar**
        - "Axess, Wings, Free ve Ticari kartlar dahildir" -> **Axess, Wings, Free, Ticari kartlar**
        - "Bank’O Card Axess Bireysel kartlar ile sanal kartlar dahildir" -> **Bank’O Card Axess, Sanal kartlar**
    - ⛔ **KESIN YASAK**: Hiçbir kartı (özellikle Wings listede varsa) "başlıkta var zaten" diyerek listeden ELEMEYİN.
    - ⛔ **KESIN YASAK**: Asla "Kampanyaya Dahil Kartlar" yazma.
    - ⛔ **KESIN YASAK**: Kart isimlerini asla 'conditions' (koşullar) listesine yazma. Sadece 'cards' alanına yaz.
- PARTICIPATION (katilim_sekli):
    - 🚨 **ULTRA-CONCISE**: Use ONLY these 3 options:
      1. If Jüzdan: "Jüzdan'dan Hemen Katıl butonuna tıklayın."
      2. If SMS: "[KEYWORD] yazıp 4566'ya SMS gönderin."
      3. If no registration: "Otomatik Katılım" (Tercihen bunu kullan). Eğer harcama yeri çok kritikse en fazla "Axess üye işyerlerinde harcama yapın" şeklinde kısa tut. (ASLA metindeki o uzun boilerplate cümleleri kopyalama).
- SMS: Usually 4566. SMS keyword is usually a single word (e.g., "A101", "TEKNOSA").
- REWARD: If it says "8 aya varan taksit", it's an installment campaign. Earning: "Taksit İmkanı". ASLA "Detayları İnceleyin" yazma.
- MARKETING (ai_marketing_text):
    - 🚨 **KESİN TALİMAT**: Pazarlama metni 'description' alanından FARKLI olmalıdır. 
    - Kampanya içeriğine (sektör/marka) uygun ve çeşitli emojiler kullanarak kullanıcının ilgisini çek.
    - SEO uyumlu, enerjik ve somut kazancı vurgulayan 2-3 cümle kur.
- AKBANK REDUNDANCY ALERT (CRITICAL):
    - Akbank metinleri tarih ve kart bilgisini çok tekrar eder. 
    - 'conditions' (koşullar) listesine ASLA tarih, kart adı veya "Jüzdan" gibi bilgileri yazma.
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
    - 🚨 **ELIGIBLE CARDS DIRECTORY**: Worldcard, World, Play, adios, Crystal, Metal Crystal, asıl metal Crystal kartlar, adios premium, Play card, World Eko, World Gold, World Platinum, TLcard, Yapı Kredi bireysel kredi kartları, Yapı Kredi banka kartları, Vakıfbank Worldcard, Albaraka Worldcard, Anadolubank Worldcard, Bireysel kredi kartları, Bireysel banka kartları, Ticari kartlar, Ticari kredi kartları, Business, Sanal kartlar, Ek kartlar, TROY logolu kartlar, Mastercard logolu kartlar, Visa logolu kartlar.
    - 🚨 **METNE SADIK SIRALI LİSTE (CRITICAL)**: Kart isimlerini metinde geçtiği sırayla, virgülle ayrılmış temiz bir liste olarak yaz. **Worldcard**, **Play**, **adios**, **Crystal**, **TLcard** ana markalarını parantez içinde bile olsa (Örn: "... (Worldcard, Play) ...") MUTLAKA ayrı kalemler olarak ekle. "Metal Crystal", "asıl metal Crystal kartlar" gibi özel asıl varyasyonları AYNEN KORUYARAK EKLE.
    - 🚨 **KAYNAK KONTROLÜ VE BAŞLIK ODAKLI ARAMA (ULTRA CRITICAL)**: Yapı Kredi (World) metinlerinde kart listeleri genellikle belirli başlıklardan sonraki paragraflarda yer alır. 
        - Kampanyaya dahil veya hariç kartları belirlemek için **ÖNCELİKLE** metindeki şu başlıkların altındaki maddeleri veya paragrafları tara:
            * `"Kampanyaya Dahil Harcamalar"`
            * `"Kampanya Koşulları"`
            * `"Kampanya Faydası"`
            * `"Kampanya Katılım Koşulları"`
            * `"Katılım Koşulları"`
            * `"Kampanya Koşulları ve Katılım Koşulları"`
        - Kart bilgilerini **SADECE VE SADECE** bu başlıkların altındaki metinlerden çıkar! 
        - 🚨 **FOOTER VE GÜRÜLTÜ YASAĞI**: Sayfanın en altında veya standart yasal uyarılarda geçen, kampanya ile doğrudan ilişkisi olmayan standart banka kartı listelerini, taksit tablolarını ya da yasal sorumluluk metinlerindeki kart isimlerini (Örn: World Platinum, World Gold, World Eko vb.) **KESİNLİKLE DİKKATE ALMA**. Metnin geri kalanındaki bu gürültüler sadece yasal detaylardır, kampanya kapsamında geçerli olan kartları temsil etmezler.
        - Eğer yukarıdaki özel başlıklar metinde bulunmuyorsa, tüm metni ("Kampanya Koşulları" altındaki tüm maddeleri) tarayarak kartların dahil/hariç olduğunu belirten cümleyi izole et ve oradaki kartları çıkar.
    - RAW EXTRACTION (LITERAL): Metinde ne yazıyorsa (Örn: "Mastercard logolu Yapı Kredi bireysel kredi kartları") DIREKT ONU YAZ.
    - ONEMLI: "Sanal kartlar", "Ticari kartlar" vb. ifadeleri sadece **dahil/geçerli** oldukları belirtilmişse listeye ekle. Eğer "hariçtir" deniyorsa ASLA yazma.
    - 🚨 **HARİÇ KART KURALI (CRITICAL)**: Yapı Kredi'de hariç tutulan kartlar ("dahil değildir", "hariçtir", "kapsam dışıdır") genellikle ayrı bir başlık altında listelenmez, kampanya koşulları paragrafları veya bullet point maddeleri içinde düz metin olarak yazılır (Örn: "Ticari kartlar ve Anadolubank bireysel Worldcard'lar kampanyaya dahil değildir", "World Eko kartlar hariçtir"). Bu olumsuz cümlelerde doğrudan adı geçen hariç kart varyasyonlarını (Örn: World Eko, Ticari kartlar, Anadolubank Worldcard) `cards` listesinden KESİNLİKLE ÇIKAR ve `excluded_cards` listesine yaz. Ancak bu hariç tutulan alt kartların bağlı olduğu asıl geçerli ana kart gruplarını (Örn: Yapı Kredi bireysel kredi kartları, Vakıfbank Worldcard) `cards` listesine eklemeyi MUTLAKA sürdür! 🚨 **İSTİSNA**: Bir alt varyasyonun (Örn: "Play Genç", "World Eko") hariç tutulması, bağlı olduğu ana kartın (Örn: "Play", "Worldcard", "Yapı Kredi bireysel kredi kartları") hariç tutulduğu anlamına GELMEZ.
        - 🚨 **KOŞULLARA (CONDITIONS) EKLEME ZORUNLULUĞU**: Kampanyada geçersiz olan kart gruplarını, ticari kartları veya belirli varyasyonları (Örn: "World Eko kartlar kampanyaya dahil değildir", "Ticari kartlar ve Anadolubank Worldcard dahil değildir") `excluded_cards` listesine eklemenin yanı sıra, **MUTLAKA ve EKSİKSİZ OLARAK** kampanya koşulları (`conditions`) dizisine de birer madde olarak ekle! Kullanıcı, kampanya koşullarını okuduğunda hangi kartların kapsam dışı olduğunu net olarak görmelidir.
    - 🚨 **ORTAK KART İSTİSNASI**: Yapı Kredi Worldcard kampanyalarında Vakıfbank, Albaraka ve Anadolubank ortaklıkları çok yaygındır. Cümle içinde açıkça geçen ortak banka kartlarını (Örn: "Vakıfbank ve Albaraka Worldcard'lar kampanyaya dahildir") listeye KESİNLİKLE ekle. "Dahil değildir" denilenleri (Örn: "Anadolubank Worldcard'lar kampanyaya dahil değildir") kesinlikle ekleme.
- PARTICIPATION (katilim_sekli):
    - EXTRACTION RULE: Extract exactly what is found in the text. DO NOT use generic templates.
    - APP: Look for "World Mobil" or "Yapı Kredi Mobil" and "Hemen Katıl" instructions. -> Extract as "World Mobil veya Yapı Kredi Mobil uygulamasından Hemen Katıl butonuna tıklayarak katılabilirsiniz."
    - SMS: Look for keyword + **"4454"** shortcode. -> Extract as "4454'e [KEYWORD] yazıp SMS göndererek katılabilirsiniz."
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
    - 🚨 **ELIGIBLE CARDS DIRECTORY**: Maximum, Maximiles, Maximum Genç, Maximiles Black, Maximiles Select, Privia, Privia Black, Bankamatik Kartı, TROY logolu kartlar, MercedesCard, Maximum Pati Kart, Maximum Tema Kart, İşte Üniversiteli, MaxiPara Kartı, Ticari Kredi Kartları, Fibabanka Gold, Fibabanka Prestige, Getir, Business, İmece Kart, Vergi Kart, KOSGEB Kart, Bayi Kart, Ticari Bankamatik Kartı.
    - 🚨 **METNE SADIK SIRALI LİSTE (CRITICAL)**: Kart isimlerini metinde geçtiği sırayla, virgülle ayrılmış temiz bir liste olarak yaz. **Maximum** ve **Maximiles** ana markalarını parantez içinde bile olsa (Örn: "... (Maximum, Maximiles) ...") MUTLAKA ayrı kalemler olarak ekle. "Maximum" kelimesini "Maximum Genç" ile karıştırıp listeden ELEME. Her ikisi de metinde varsa her ikisini de yaz.
    - 🚨 **KAYNAK KONTROLÜ (SAFE ZONE)**: Geçerli kart listesini **MUTLAKA** metinde geçen **"Kampanyaya dahil/dâhil olan kartlar:"**, **"Kampanyaya dahil/dâhil olan kartlar ve işlemler:"** veya **"KAMPANYAYA DÂHİL OLAN KARTLAR VE İŞLEMLER:"** başlıklarının altından harfiyen çıkar. Bu başlıkların altındaki her bir kart tanımı (Maximum, Maximiles, TROY logolu kartlar, Bankamatik Kartı, MaxiPara Kartı vb.) KESİNLİKLE geçerlidir ve hiçbirini atlamadan listele.
    - RAW EXTRACTION (LITERAL): Metinde ne yazıyorsa (Örn: "İş Bankası TROY logolu bireysel ve ticari kredi kartı") DIREKT ONU YAZ.
    - ONEMLI: "Sanal kartlar", "Ticari kartlar" vb. ifadeleri sadece **dahil/geçerli** oldukları belirtilmişse listeye ekle. Eğer "hariçtir" deniyorsa ASLA yazma.
    - 🚨 **BAŞLIK KURALI (CRITICAL)**: "Kampanyaya dahil/dâhil olmayan kartlar:" başlığı altında listelenen hiçbir kartı `cards` listesine EKLEME. 🚨 **İSTİSNA**: Bir alt varyasyonun (Örn: "Maximum Fırsat", "Maximum Aidatsız") hariç tutulması, ana kartın (Örn: "Maximum") hariç tutulduğu anlamına GELMEZ. Eğer metin başında "Maximum Kart" dahil deniyorsa onu MUTLAKA listeye ekle.
    - Örnek: "İş Bankası Maximum özellikli kredi kartları (Maximum, Maximiles...)" yazıyorsa AYNEN AL.
    - 🚨 **ORTAK KART İSTİSNASI**: Eğer "Kampanyaya dahil olan kartlar" bloğunda Fibabanka Gold/Prestige veya GetirFinans gibi başka banka kartları/markaları açıkça listelenmişse, bunları KESİNLİKLE listeye ekle. Başka bankalardan sadece kampanya metninde adı geçen ortak/partner kartları yazabilirsin; bunun dışındaki bankaları yazma.
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
    - 🚨 BRAND EXCLUSION (CRITICAL): "Getir", "GetirFinans" ve "Business" kelimeleri kampanya metninde sadece kart markası/adı olarak geçmektedir (Örn: "Getir ve Business kartları"). Bunları ASLA 'brands' listesine birer partner marka olarak ekleme, tamamen hariç tut!
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
- ELIGIBLE CARDS (cards) - THE "DAHIL" RULE (CRITICAL):
    - 🚨 **PATTERN MATCHING**: Ziraat campaigns have a very strict structure. 
    - 1. Look for sentences ending with "**dahildir.**" or "**dahil edilecektir.**". Extract all cards listed BEFORE these words. 
    - 2. **PARENTHESES LISTS**: If you see a list inside parentheses like "(Bankkart, Bankkart Genç, ...)", these are EXPLICITLY INCLUDED. Extract all of them. 
    - 3. **NEGATION**: Look for sentences ending with "**dahil değildir.**". Any cards listed before this word MUST BE EXCLUDED from the 'cards' list.
    - 4. **BANKKART LITERAL (CRITICAL)**: Always include "Bankkart" (without any suffixes) as a card if it is mentioned as included. Do NOT omit it.
    - 5. **REWARD TRAP (CRITICAL)**: "**Bankkart Lira**" is a reward unit (like points), NOT a card. **NEVER** include "Bankkart Lira" in the cards list.
    - 6. **PRESTIJ BOILERPLATE (CRITICAL)**: Sentences mentioning "Katlanan Bankkart Lira özelliği" or "Bankkart Prestij/Bankkart Prestij Plus kredi kartları için sunulan" are just informational boilerplate. Do NOT extract "Bankkart Prestij" or "Bankkart Prestij Plus" from these sentences unless they are explicitly listed in the main "dahildir" sentence.
- TERMINOLOGY: "Bankkart Lira". 1 Bankkart Lira = 1 TL.
- PARTICIPATION:
    - SMS: Look for specific keywords (e.g., "SUBAT2500", "RAMAZAN", "MARKET") sent to **4757**.
    - App: "Bankkart Mobil", "bankkart.com.tr".
    - Format: "KEYWORD yazıp 4757'ye SMS gönderin" or "Bankkart Mobil uygulamasından katılın".
    - FALLBACK: If NO specific method (SMS/App) is found, and it seems like a general campaign (e.g., "İlk Kart", "Taksit"), assume "Otomatik Katılım".
- CONDITIONS:
    - FORMAT: SUMMARIZE into 5-6 clear bullet points.
    - CONTENT: MUST include numeric limits (max earners, min spend). 
    - 🚨 **EXCLUSIONS**: You SHOULD mention non-eligible (excluded) cards here (e.g., "Bankkart Business kartlar dahil değildir").
    - 🚨 **NO REPETITION**: Do NOT repeat the campaign dates or the list of ELIGIBLE cards in the conditions.
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
    - 🚨 **ELIGIBLE CARDS DIRECTORY**: Paraf, Parafly, Parafree, Paraf Genç, Paraf Debit, Paraf Banka Kartı, Paraf Esnaf, Paraf KOBİ, Paraf Business, Eczacı Paraf, Eczacı Paraf KOBİ, Halkcard, Sanal kartlar, Ek kartlar, TROY logolu kartlar, Paraf Troy, Halkbank Kredi Kartları, Halkbank Banka Kartı, Paraf Kadın, Paraf Üreten Kadın, Paraf Premium, Parafly Platinum, Paraf Platinum, Emlak Katılım Paraf, Dünya Katılım Paraf.
    - 🚨 **METNE SADIK SIRALI LİSTE (CRITICAL)**: Kart isimlerini metinde geçtiği sırayla, virgülle ayrılmış temiz bir liste olarak yaz. **Paraf** ve **Parafly** ana markalarını parantez içinde bile olsa (Örn: "... (Paraf, Parafly) ...") MUTLAKA ayrı kalemler olarak ekle. "Paraf" kelimesini "Parafree" veya "Paraf Genç" ile karıştırıp listeden ELEME. Her ikisi de metinde varsa her ikisini de yaz.
    - 🚨 **KAYNAK KONTROLÜ (SAFE ZONE)**: Halkbank / Paraf metinlerinde geçerli kart listeleri genellikle ayrı bir başlık altında listelenmez. Genellikle metin içinde bir paragraf veya madde halinde geçer (Örn: "Paraf ve Parafly kredi kartları, Paraf Genç, Ticari kartlar, Emlak Katılım Paraf, Dünya Katılım Paraf... kampanyadan faydalanabilecektir. Debit kartlar, Halkcard... dahil değildir"). Bu yüzden özel bir başlık aramak yerine tüm metni tarayarak kartların dahil (kampanyadan faydalanabilecektir / dahil olup) ve hariç (dahil değildir) olduğunu belirten cümleyi izole et ve oradaki kartları çıkar.
    - RAW EXTRACTION (LITERAL): Metinde ne yazıyorsa (Örn: "Paraf TROY logolu bireysel kredi kartı") DIREKT ONU YAZ.
    - ONEMLI: "Sanal kartlar", "Ticari kartlar" vb. ifadeleri sadece **dahil/geçerli** oldukları belirtilmişse listeye ekle. Eğer "hariçtir" deniyorsa ASLA yazma.
    - 🚨 **BAŞLIK KURALI (CRITICAL)**: "Kampanyaya dahil/dâhil olmayan kartlar:" veya hariç tutulma cümlelerinde geçen hiçbir kartı `cards` listesine EKLEME. 🚨 **İSTİSNA**: Bir alt varyasyonun (Örn: "Paraf Esnaf", "Paraf Business") hariç tutulması, ana kartın (Örn: "Paraf") hariç tutulduğu anlamına GELMEZ. Eğer metin başında "Paraf" dahil deniyorsa onu MUTLAKA listeye ekle.
    - Örnek: "Paraf kredi kartları (Paraf, Parafly, Parafree...)" yazıyorsa AYNEN AL.
    - 🚨 **ORTAK KART İSTİSNASI**: Paraf kampanyalarında **Emlak Katılım Paraf** ve **Dünya Katılım Paraf** ortak lisanslı kartları sıklıkla kampanyalara dahil edilir. Eğer bu ortak bankaların Paraf logolu kartları cümlede geçiyorsa (Örn: "...Emlak Katılım Paraf, Dünya Katılım Paraf... kampanyadan faydalanabilecektir") bunları listeye KESİNLİKLE ekle.
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
    - 🚨 **MODIFIER DISTRIBUTION (ULTRA CRITICAL)**: 
        * Denizbank metinlerinde "Mastercard/Visa/TROY logolu banka kartı, kredi kartı veya ön ödemeli kartlar" gibi gruplar çok yaygındır.
        * Bu durumlarda sıfatı (örn: "Mastercard logolu") HER BİR kart tipine tek tek dağıtarak listele.
        * DOĞRU: ["DenizBank Mastercard logolu banka kartı", "DenizBank Mastercard logolu kredi kartı", "DenizBank Mastercard logolu ön ödemeli kartlar"]
        * YANLIŞ (DEVRİK): ["Kredi kartı", "Ön ödemeli kartlar", "DenizBank Mastercard logolu banka kartı"]
    - 🚨 **EXACT EXTRACTION**: Metindeki tanımlayıcı ifadeleri (örn: "Tüm bonus özellikli Bireysel Kredi Kartları") olduğu gibi koru ama yukarıdaki dağıtma kuralını uygula.
    - KESIN YASAK: Metinde geçmeyen kart isimlerini uydurma.
- PARTICIPATION (🚨 KRİTİK — EN ÖNEMLİ ALAN):
    - Denizbank kampanya sayfalarında katılım bilgisi MUTLAKA "KATILMAK İÇİN" başlıklı bir blokta yer alır.
    - Bu blok genellikle --- ÖNEMLİ BİLGİLER (KATILIM VE TARİHLER) --- veya sayfa sağ sütununda bulunur.
    - ✅ DOĞRU KAYNAK: "KATILMAK İÇİN" başlığının hemen altındaki talimat cümlesi(leri).
    - ✅ SMS VAR: "X yazıp 3280'e SMS gönderin" formatında SMS talimatı varsa TÜM CÜMLEYİ aynen yaz. Örn: '"RESTORAN" yazıp 3280'e SMS gönderin.'
    - ✅ UYGULAMA VAR: "DenizKartım" veya "MobilDeniz uygulamasından Hemen Katıl butonuna tıklayın" ifadesi varsa TÜM CÜMLEYİ aynen yaz.
    - ✅ HEM SMS HEM UYGULAMA: Her ikisi de belirtilmişse ikisini de yaz — örn: 'Harcamadan önce DenizKartım, MobilDeniz uygulamasından "Hemen Katıl" butonunu tıklayın veya "RESTORAN" yazıp 3280'e SMS gönderin.'
    - ✅ OTOMATİK: Sadece "katılım gerekmemektedir", "otomatik katılım", "kendiliğinden" gibi ifadeler varsa "Otomatik Katılım" yaz.
    - 🚫 KESİN YASAK: "Kampanyaya katılım sonrasında gerçekleştirilen işlemler kampanya kapsamında değerlendirilir." GİBİ KOŞUL CÜMLELERİNİ 'participation' ALANINA YAZMA. Bu bir katılım talimatı değil, bir kural/koşuldur — bunu 'conditions' listesine yaz.
    - 🚫 KESİN YASAK: Veri yoksa "Detayları İnceleyin" veya "Hemen Faydalanın" YAZMA.
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
- ELIGIBLE CARDS (cards):
    - 🚨 **ÖNCELİK SIRASI**: 
        1. "Kampanyaya Dahil Kartlar" veya "Kampanya Bilgileri" başlığı altındaki maddeler.
        2. Eğer başlık yoksa, metnin giriş paragrafları ve şartlar listesi içindeki tüm kart tanımları (Örn: "Mastercard logolu TEB Kredi Kartları", "Visa logolu kartlar").
    - 🚨 **ZENGİN LİTERAL KURALI**: Kart isimlerini metindeki tüm niteleyicileriyle birlikte al. **"Mastercard logolu"**, **"Visa özellikli"**, **"TROY logolu"**, **"Bonus özellikli"** gibi ifadeler kartın ta kendisidir, bunları KESİNLİKLE LİSTEYE EKLE.
    - 🚨 **KESİN YASAK (HALLUCINATION)**: Metinde "She", "Genç", "CEPTETEB" gibi spesifik alt markalar AÇIKÇA (karakter karakter) geçmiyorsa, bu isimleri ASLA 'cards' listesine ekleme. 
    - 🚨 **DIŞLAMA KONTROLÜ**: **"Kampanyaya Dahil Olmayan Kartlar"** başlığı altındaki hiçbir kartı (Örn: Sade Kart, Ticari Kart) 'cards' listesine EKLEME.
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
- NOISE FILTERING (CRITICAL):
    - 🚨 **ÇAPA METNİ**: "Türkiye Finans Katılım Bankası A.Ş. kampanya koşullarını değiştirme hakkını saklı tutar." cümlesinden sonrasını KESİNLİKLE dikkate alma. Bu metin ve sonrası tamamen gürültü (footer, yasal adresler vb.) içerir.
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
""",
    'dunyakatilim': """
DÜNYA KATILIM SPECIFIC RULES:
- TERMINOLOGY: "Harcama Puan", "İndirim" or "ParafPara".
- ELIGIBLE CARDS (cards):
    - 🚨 **LİTERAL KURALI (CRITICAL)**: Sadece metinde AKTİF kampanya maddeleri içinde geçen kart isimlerini al. 
    - 🚨 **HALÜSİNASYON YASAĞI**: Sayfanın en altındaki "Dünya Katılım Bankası A.Ş. kampanya koşullarında değişiklik yapma hakkını saklı tutar" gibi yasal metinlerden kart ismi ÇIKARMA.
    - 🚨 **ÖNCELİK**: Eğer metinde "Dünya Katılım Paraf" geçiyorsa sadece onu yaz. Metinde açıkça geçmiyorsa "Dünya Katılım Banka Kartı", "Dünya Katılım Kredi Kartı" gibi jenerik isimleri uydurma.
    - Keywords: "Dünya Katılım Paraf", "Dünya Katılım Banka Kartı", "Dünya Katılım Kredi Kartı", "Dünya Katılım Troy Kart".
    - 🚨 ASLA ATLANMAYACAK: "TROY" logolu kartlar vurgulanmışsa bunu kart listesine ekle.
- PARTICIPATION (katilim_sekli):
    - 🚨 **ÖNEMLİ**: Katılım şeklini bulamazsan BOŞ BIRAKMA. Eğer SMS veya Uygulama kaydı yoksa "Otomatik Katılım" veya "Paraf POS üzerinden işlem" şeklinde belirt.
    - PRIORITY ORDER:
      1. App: "Dünya Katılım Mobil" application. Look for "Kampanyalar" menu and "Katıl" button.
      2. SMS: If any shortcode is mentioned.
      3. POS/In-store: "Mağazada Paraf POS cihazı üzerinden işlem yaparak" or "Kasada belirtilerek".
      4. Automatic: If it's a simple installment or discount, use "Harcama anında otomatik olarak uygulanır."
    - FORMAT: "Dünya Katılım Mobil uygulamasındaki Kampanyalar menüsünden katılabilirsiniz." or "Paraf POS cihazı üzerinden işleminizi yaparak katılabilirsiniz."
- CONDITIONS: 
    - Focus on specific merchant categories and minimum spend requirements.
    - Mention if "TROY" logo is mandatory for the campaign.
""",
    'vodafone': """
VODAFONE SPECIFIC RULES:
- TERMINOLOGY: "Fayda", "İndirim", "Kod".
- ELIGIBLE CARDS / CUSTOMER SEGMENTS (cards) - **STRICT LITERAL & REDUNDANCY GUARD**:
    - 🚨 **KESİN TALİMAT**: Metinde "Klasik", "RED Premium" gibi spesifik gruplar listelenmişse, ayrıca genel bir "Vodafone Müşterileri" maddesi EKLEME (eğer metinde bağımsız bir grup olarak geçmiyorsa).
    - 🚨 **HASSASİYET**: Eğer grupların başında "Faturalı" veya "Bireysel" gibi belirteçler varsa bunları MUTLAKA koru.
    - 🚨 **KISA VE ÖZ İSİMLENDİRME**: Segment isimlerini listelerken **SADECE VE SADECE EN SON** maddeye "müşterileri" ekini ekle. Diğer tüm maddelerin sonundaki "müşterileri", "aboneleri", "kullanıcıları" gibi ekleri metinde yazsa bile **SİL**.
    - **DOĞRU**: `["Vodafone Ev İnterneti", "Vodafone RED Premium", "Vodafone Faturasız müşterileri"]`
    - **YANLIŞ**: `["Vodafone Ev İnterneti müşterileri", "Vodafone RED Premium", "Vodafone Faturasız müşterileri"]`
    - Metinde geçen her grubu `cards` alanına **ayrı ayrı** ve **standardize ederek** (Başına "Vodafone" ekleyerek) yaz.
    - ⛔ **YASAK**: Metinde açıkça yazmayan ("FreeZone" vb.) hiçbir grubu ekleme.
- PARTICIPATION (katilim_sekli):
    - 🚨 **ÖNEMLİ**: Kod alma, SMS, şifre söyleme gibi teknik adımları SADECE `participation` alanına yaz. 
    - ⛔ **YASAK**: Bu teknik adımları `ai_marketing_text` alanına yazma.
    - Look for "Vodafone Yanımda", "Happy" or "Fırsatlar Dünyası" app instructions.
    - Extract as: "Vodafone Yanımda uygulamasındaki Fırsatlar Dünyası / Happy menüsünden indirim kodunuzu alarak katılabilirsiniz."
    - Metinde SMS (7276 vb.) veya Kasa adımları varsa mutlaka ekle.
- CONDITIONS: 
    - Focus on usage frequency (e.g., "30 günde 1 kez", "ayda 2 kez").
    - Mention minimum spend thresholds and specific exclusions.
    - ⛔ **TEKRAR YASAĞI**: `cards` alanında belirttiğin müşteri gruplarını burada tekrar yazma.
""",
    'paycell': """
PAYCELL SPECIFIC RULES:
- STRUCTURE (CRITICAL): Paycell uses a Q&A format. Map these headers DIRECTLY:
    1. "Kampanyaya Kimler Katılabilir?" -> **ELIGIBLE CARDS (cards)** (Source for cards/segments)
    2. "Kampanyaya Dahil Harcamalar Nelerdir?" -> **ELIGIBLE CARDS (cards)** (Source for cards/payment methods)
    3. "Kampanyadan Nasıl Kazanırım?" -> **PARTICIPATION (participation)**
    4. "Kampanya Geçerlilik Tarihi Nedir?" -> **DATES (start_date, end_date)**
    5. "Kampanya Faydası Nedir?" -> **REWARD (reward_text)**
- DESCRIPTION (CRITICAL):
    - 🚨 **ASLA ÖZETLEME**: Paycell metinleri soru-cevap formatındadır. 'description' alanına metnin TAMAMINI (tüm soru ve cevapları) olduğu gibi yaz. Bilgi kaybını önlemek için bu hayati önem taşır.
- ELIGIBLE CARDS (cards):
    - 🚨 **ÖNEMLİ**: Paycell için "Faturana Yansıt", "Mobil Ödeme", "Turkcell müşterileri" ve "Paycell Kart" ibarelerini metnin neresinde olursa olsun mutlaka 'cards' listesine ekle. "Faturana Yansıt" bir ödeme ürünü ismidir.
    - **LİTERAL EXTRACTION**: Metinde karakter karakter ne görüyorsan (örn: "Faturana Yansıt", "Fiziksel Paycell Kart") aynen al.
    - **SIFIR HALÜSİNASYON**: Metinde açıkça geçmeyen bir kartı ASLA ekleme.
- PARTICIPATION (participation):
    - 🚨 **KAYNAK KONTROLÜ**: Katılım şekli bilgisini **ÖNCELİKLE** "Kampanyadan Nasıl Kazanırım?" bölümünden al. 
    - **FALLBACK**: Eğer bu başlık yoksa tüm metne bak.
    - Buton tıklama ("Hemen Katıl"), SMS veya diğer aksiyonları bu bölümden özetleyerek yaz.
- TERMINOLOGY: "Hediye Para" or "Nakit İade".
- CONDITIONS: Use "Diğer Koşullar" and "Kampanyaya Dahil Harcamalar Nelerdir?" for the conditions list.
""",
    'opet': """
OPET SPECIFIC RULES:
- ELIGIBLE CARDS / CUSTOMER SEGMENTS (cards):
    - 🚨 **VARSAYILAN MÜŞTERİ GRUBU**: Opet kampanyalarında eğer metinde spesifik bir banka kartı (örn: "Axess", "Opet Worldcard") belirtilmemişse, `cards` alanına mutlaka **"Opet Müşterileri"** yazılmalıdır.
    - 🚨 **ÖNCELİK KURALI**: Eğer metinde "Opet Worldcard ile..." veya "Yapı Kredi kredi kartları ile..." gibi banka spesifik bir ifade geçiyorsa, sadece o banka kartlarını yaz. "Opet Müşterileri" ifadesini bu durumda EKLEME.
    - 🚨 **METİN KONTROLÜ**: "Opet müşterilerine özel", "Opetlilere özel", "Opet Kart sahiplerine" gibi ifadeler doğrudan "Opet Müşterileri" olarak normalize edilmelidir.
    - 🚨 **İŞ BİRLİĞİ KAMPANYALARI**: "DeFacto ve Opet iş birliği", "Çek Kazan" gibi üçüncü taraf kampanyalarında, katılım Opet sitesi üzerinden duyuruluyorsa "Opet Müşterileri" mutlaka eklenmelidir.
- PARTICIPATION (participation):
    - Opet sitesindeki "Hemen Katıl", "Şifre Al", "Kodu Kullan" gibi adımları özetle.
    - "Opet Mobil uygulamasını indirin", "Opet Pay ile ödeyin" gibi talimatları mutlaka ekle.
- CONDITIONS: 
    - Akaryakıt harici harcamalar (örn: market, araç yıkama) veya belirli ürün grupları (Parex, Karcher) için geçerliyse belirt.
    - Puan kullanım tarihleri ve geçerli istasyon kısıtlamalarını ekle.
""",
    'türk telekom': """
TÜRK TELEKOM SPECIFIC RULES:
- ELIGIBLE CARDS / CUSTOMER SEGMENTS (cards):
    - 🚨 **TEMİZ KART GRUPLARI**: "Selfy", "Prime", "Türk Telekom Prime", "Türk Telekom Mobil müşterileri", "Türk Telekom Evde İnternet müşterileri" gibi ifadeleri doğrudan kart/müşteri grubu olarak ekle.
    - 🚨 **SELFY / PRIME KART VURGUSU**: Eğer kampanya Selfy sayfasında veya Prime sayfasında yayınlanıyorsa, 'cards' alanına mutlaka "Selfy" veya "Prime" (hangisi geçerliyse) kart adını ekle.
- PARTICIPATION (participation):
    - SMS: Look for keyword + short number "6262". Format: "[KEYWORD] yazıp 6262'ye SMS gönderin."
    - App: "Türk Telekom Online İşlemler" or "Türk Telekom Mobil".
""",
    'ziraat-katilim': """
ZİRAAT KATILIM SPECIFIC RULES:
- TERMINOLOGY: The currency used is generally "Katılım Bankkart Lira" or direct TL discounts.
- ELIGIBLE CARDS (CRITICAL):
    - 🚨 **TEMİZLEME KURALLARI (BANKA İSMİ TEKRARI YASAĞI - ÇOK ÖNEMLİ)**: 
        - Ziraat Katılım metinlerinde geçen uzun kart isimlerini **BİREBİR KOPYALAMA**. Kesinlikle temizleyerek yaz.
        - Kart isimlerinin başında yer alan "Ziraat Katılım" ifadesini SİL.
        - "Ziraat Katılım Bireysel Bankkart kredi kartı" yazıyorsa -> **Bireysel Katılım Bankkart** yaz.
        - "Ziraat Katılım Bankkart (Gold)" -> **Katılım Bankkart Gold** yaz.
        - "Ziraat Katılım Bankkart (Platinum)" -> **Katılım Bankkart Platinum** yaz.
        - "Ziraat Katılım Bankkart Ticari" -> **Katılım Bankkart Ticari** yaz.
        - Metinde sadece "Bankkart" geçiyorsa -> **Katılım Bankkart** yaz.
        - "Ek kartlar" ibaresini aynen koru.
    - 🚨 **BOŞ BIRAKMA YASAĞI**: Gece taramalarında bazen geçerli kart kısmı eksik kalıyor. Eğer metinde doğrudan bir kart adı geçmiyorsa veya emin olamadıysan, `cards` listesini ASLA BOŞ BIRAKMA. Kampanya genel ise varsayılan olarak en azından "Katılım Bankkart" yaz.
- 🚨 **FOOTER GÜRÜLTÜSÜ YASAĞI (ULTRA CRITICAL)**:
    - Metnin sonunda yer alan "Kıymetli Madenler Sorumlu Tedarik Zinciri", "Sürdürülebilir Finans Çerçevemiz", "Zamanaşımına Uğrayacak Olan Hesaplar", "SPK Duyuruları", "CİMERe Başvuru", "Satılık Menkuller" gibi banka kurumsal footer linklerine ait metinleri ASLA dikkate alma. Kampanya koşulları bu metinlerden önce biter.
- PARTICIPATION (katilim_sekli):
    - Genellikle "Katılım Mobil" uygulaması veya "SMS" üzerinden katılım sağlanır. "Katılım Mobil" uygulamasındaki "Kampanyalar" menüsünü belirt.
""",
    'ziraat-dinamik': """
ZİRAAT DİNAMİK SPECIFIC RULES:
- TERMINOLOGY: The currency used is "Bankkart Lira" or direct TL discounts.
- ELIGIBLE CARDS (CRITICAL):
    - 🚨 **TEMİZLEME KURALLARI (BANKA İSMİ TEKRARI YASAĞI - ÇOK ÖNEMLİ)**: 
        - Ziraat Dinamik metinlerinde geçen uzun kart isimlerini **BİREBİR KOPYALAMA**. Kesinlikle temizleyerek yaz.
        - Kart isimlerinin başında yer alan "Ziraat Dinamik" veya "Ziraat" ifadesini SİL.
        - 🚨 **MÜŞTERİ GRUBU KURALI**: Eğer kampanya koşullarında "kampanyadan yalnızca Ziraat Dinamik Mobil üzerinden..." gibi bir uygulama şartı geçiyorsa ve geçerli kartlar olarak metinde hiçbir kart grubu veya segment belirtilmemişse, `cards` listesine sadece **Ziraat Dinamik Müşterileri** yaz. ANCAK metinde açıkça "bireysel kartlar", "ticari kartlar", "dinamik kart" vb. ifadeler GEÇİYORSA, bunları ASLA "Ziraat Dinamik Müşterileri" olarak gruplama; "Bireysel Dinamik Bankkart", "Ticari Dinamik Bankkart" gibi sadeleştir.
        - 🚨 **BANKKART KURALI**: Eğer geçerli kartlar arasında "Bankkart" ibaresi geçiyorsa, bunu kesinlikle düz "Bankkart" olarak DEĞİL, **Dinamik Bankkart** olarak yaz.
        - "Dijital Kredi Kartı" -> **Dijital Kredi Kartı** olarak koru.
        - "Ek kartlar", "Sanal kartlar" ibarelerini aynen koru.
    - 🚨 **BOŞ BIRAKMA YASAĞI**: Eğer metinde doğrudan bir kart adı geçmiyorsa veya emin olamadıysan, `cards` listesini ASLA BOŞ BIRAKMA. Varsayılan olarak en azından "Dinamik Bankkart" veya "Ziraat Dinamik Müşterileri" yaz.
- 🚨 **FOOTER GÜRÜLTÜSÜ YASAĞI (ULTRA CRITICAL)**:
    - Ziraat Katılım ile aynı altyapıyı kullandığı için metnin sonundaki "Kıymetli Madenler Sorumlu Tedarik Zinciri", "SPK Duyuruları", "CİMERe Başvuru", "Satılık Menkuller" gibi gürültüleri tamamen yok say ve ASLA kampanya koşullarına ekleme.
- PARTICIPATION (katilim_sekli):
    - Genellikle "Ziraat Dinamik Mobil" veya "Ziraat Mobil" üzerinden katılım sağlanır.
""",
    'vakif-katilim': """
VAKIF KATILIM (VKART) SPECIFIC RULES:
- TERMINOLOGY: Direct TL discounts or percentage discounts.
- ELIGIBLE CARDS (CRITICAL):
    - 🚨 **TEMİZLEME KURALLARI**: 
        - "Vakıf Katılım Bireysel Kredi Kartı", "Bireysel Vakıf Katılım Kredi Kartı", "Vakıf Katılım Kredi Kartı" -> **VKart Bireysel** olarak standartlaştır.
        - "Vakıf Katılım Banka Kartı" -> **VKart Banka Kartı** olarak al.
        - "TROY logolu kredi kartı", "VKart TROY" -> **VKart TROY** olarak al.
        - "Mastercard logolu Vakıf Katılım Kredi Kartı", "Bireysel Mastercard logolu kredi kartları", "VKart Mastercard" -> **VKart Mastercard** olarak al.
        - "Ek kartlar", "Sanal kartlar" ibarelerini aynen koru.
- 🚨 **FOOTER GÜRÜLTÜSÜ YASAĞI (ULTRA CRITICAL)**:
    - Vakıf Katılım kampanya metinlerinin sonunda her zaman "Tümünü Göster", "İlginizi Çekebilecek Kampanyalar", "Çerezleri Özelleştirin", "Reddet", "Kabul Ediyorum", "Tüm Kampanyalar" gibi web sitesi bileşenleri yer alır. Bu metinler kampanya detaylarına AİT DEĞİLDİR ve koşullara (conditions) veya açıklamaya (description) ASLA dahil edilmemelidir.
- PARTICIPATION (katilim_sekli):
    - Genellikle "Vakıf Katılım Mobil Şube" veya internet şubesi kullanılır.
""",
    'tom bank': """
TOM BANK SPECIFIC RULES:
- TERMINOLOGY: "Hadi Puan" or "Nakit İade". TOM Bank is a digital wallet/bank application.
- ELIGIBLE CARDS (CRITICAL):
    - 🚨 **TEMİZLEME KURALLARI**: 
        - Kampanyaya dahil olan kartları şu standart tiplerle belirle: "Hadi Kredi Kartı", "Hadi Black Kredi Kartı", "Hadi Hesap Kartı", "Hadi Veresiye".
        - "Hadi Black", "Hadi Gold" segmentleri veya "Hadi Kart" ifadelerini olduğu gibi koru.
        - Gereksiz uzun "TOM Bank A.Ş. Hadi Kredi Kartı" gibi metinleri -> **Hadi Kredi Kartı** olarak kısalt.
        - Boş bırakma durumunda kampanya herkes için geçerliyse "Hadi Kart" yaz.
- CUSTOMER TARGET (MÜŞTERİ KİTLESİ): 
    - "Hadi Plus" üyelerine veya "A101 Plus" üyelerine özel bir kampanya ise (örn: A101 indirimleri), bunu 'description' veya 'conditions' içerisinde KESİNLİKLE vurgula.
- 🚨 **FOOTER GÜRÜLTÜSÜ YASAĞI (ULTRA CRITICAL)**:
    - Sayfa altındaki "Hadi Keşfet", "Biz Kimiz", "Hadi Kariyer", "Ortaklık Yapısı", "Hadi Kazan", "Hadi Hesap", "Hadi Yatırım İşlemleri", "Hisse Senedi ve Halka Arz", "Yatırım Fonu", "Hadi Kartlarım", "Hadi Krediler", "Veresiye Kredi" gibi genel menü başlıklarını ve açıklamalarını ASLA kampanyaya dahil etme.
- PARTICIPATION (katilim_sekli):
    - Genellikle "Hadi Uygulaması" üzerinden işlem yapılır.
""",
    'ahl pay': """
AHL PAY SPECIFIC RULES:
- TERMINOLOGY: "Nakit İade" or "İndirim" or "Hediye".
- ELIGIBLE CARDS (CRITICAL):
    - 🚨 **TEMİZLEME KURALLARI**:
        - "AHL Card", "AHL Pay Card", "AHL Pay TROY", "AHL Pay Visa" gibi isimleri standartlaştır.
        - "AHL Card" veya "AHL Pay Kart" ifadelerini olduğu gibi koru.
        - Yanlış veya uzun: "AHL Pay Elektronik Para A.Ş. AHL Card" -> **AHL Card**
        - Boş bırakma durumunda kampanya herkes için geçerliyse "AHL Card" yaz.
- CUSTOMER TARGET (MÜŞTERİ KİTLESİ): 
    - İhtiyaç Finansmanı, Araç Finansmanı, Konut Finansmanı gibi kampanyalarda veya "İlk defa yatırım yapanlar" gibi özel bir müşteri kitlesi belirtilmişse, bunu kampanya koşullarında ve açıklamalarında mutlaka vurgula.
- 🚨 **FOOTER GÜRÜLTÜSÜ YASAĞI (ULTRA CRITICAL)**:
    - Sayfa altındaki "AHL Pay Başvuru", "Hakkımızda", "Kurumsal Yönetim" gibi genel menü başlıklarını ASLA kampanyaya dahil etme.
- PARTICIPATION (katilim_sekli):
    - Genellikle "AHL Pay Mobil Uygulaması" üzerinden işlem yapılır.
""",
    'anadolubank': """
ANADOLUBANK SPECIFIC RULES:
- ELIGIBLE CARDS: 
    - 🚨 **TEMİZLEME KURALLARI (CRITICAL)**: Kart isimlerini çıkarırken, başına fazladan banka adını ekleme.
    - Anadolubank metinlerinde sıklıkla belirli bir kart adı değil "Anadolubank müşterileri" ibaresi geçer. Eğer kampanya metninde sadece "Anadolubank müşterileri" diyorsa, eligible_cards alanına doğrudan **"Anadolubank Müşterileri"** yaz.
    - Eğer spesifik olarak uzun karmaşık kart isimleri (örn: "Silver logolu Anadolubank Mastercard kredi kartı", "Anadolubank Mastercard logolu ön ödemeli kartlar") varsa, bunları ŞU 5 STANDART GRUBA İNDİRGE:
        1. "Anadolubank Kart"
        2. "Anadolubank Banka Kartı"
        3. "Anadolubank Troy Kart"
        4. "Anadolubank Ticari Kart"
        5. "Anadolubank Silver Mastercard"
    - TROY logolu kartları kesinlikle ayrı bir madde olarak "Anadolubank Troy Kart" şeklinde yaz.
    - "Positive Card" gibi dış marka kartları varsa aynen bırak.
- CUSTOMER TARGET (MÜŞTERİ KİTLESİ): 
    - Metinde geçen "Anadolubank müşterileri" ifadesi aslında hedef kitleyi belirler, bunu hem eligible_cards hem de açıklama içerisinde kullanabilirsin.
    - "Özel Bankacılık Müşterileri", "Perakende Müşteriler" veya "KOBİ" gibi daha dar bir kitleye hitap eden kampanyalarda bu segmentleri açıklamalarda ve koşullarda kesinlikle vurgula.
"""
}
