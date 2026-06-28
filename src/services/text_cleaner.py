import re
from typing import Optional
from bs4 import BeautifulSoup

def clean_campaign_text(raw_text: str, og_title: Optional[str] = None, title: Optional[str] = None) -> str:
    """
    Centralized text cleaner to remove boilerplate banking legal terms and navigation noise.
    
    og_title/title: Used to trim SPA header/navigation noise by finding the real 
                   campaign title in the text and chopping everything above it.
    """
    if not raw_text:
        return ""

    # ── Step 1: HTML DOM Cleanup (Autofix Standard) ──────────
    # Sadece GERÇEK html yapıları varsa BeautifulSoup kullan (Trafilatura markdown'ını bozma)
    is_html = bool(re.search(r'<(html|div|p|body|table|section|article|span|li|ul|ol)', raw_text, re.IGNORECASE))
    
    if is_html:
        try:
            soup = BeautifulSoup(raw_text, "html.parser")
            
            page_title = ""
            if soup.title:
                page_title = " ".join(soup.title.get_text().split()).strip()
            
            # 1. Global Tag Removal (Kökten ayıklama)
            for element in soup(["script", "style", "nav", "footer", "header", "noscript", "meta", "iframe", "svg", "link", "aside", "title"]):
                element.decompose()
            
            # 2a. Keyword-based structural noise decomposer (class/id matching)
            def is_noise_tag(tag):
                if tag.name not in ["div", "section", "ul", "li", "span"]: return False
                tag_classes = tag.get("class") or []
                tag_id = tag.get("id") or ""
                keywords = ["footer", "header", "menu", "nav", "sidebar", "breadcrumb", "cookie", "cookie-consent", "modal", "popup", "sitemap", "quick-links"]
                
                safe_classes = ["sub-header", "page-header", "campaign-header", "content-header", "section-header", "card-header"]
                
                for kw in keywords:
                    if kw in tag_id: return True
                    for c in tag_classes:
                        c_lower = str(c).lower()
                        if kw in c_lower:
                            if any(safe in c_lower for safe in safe_classes):
                                continue
                            return True
                return False

            for tag in soup.find_all(is_noise_tag):
                try:
                    tag.decompose()
                except Exception:
                    pass

            # 2b. Bank-specific CSS selectors (TEB, QNB, Akbank, Garanti etc.)
            bank_noise_selectors = [
                # Common noise
                '.other-campaigns', '.featured-campaigns', '.similar-campaigns',
                '.campaign-recommendations', 'section.news-carousel',
                '#related-campaigns', '.campaignDetail-others', '.campaign-recommendations-box',
                '.footer-bottom', '.social-links', '.navigation-wrapper', '.cookie-banner',
                '.top-menu', '.sidebar', '.ad-panel', '.social-share',
                '.slider-container', '.camp-slider', '.camp-slider-container', '.swiper-container',
                # TEB
                '#header', '#footer', '#headerUp', '#headerDown', '#headerMain', '#headerSrc', '#headerLoginPanelNew',
                '#footerBant', '#footerQuickMenu', '#socialFooter', '#fDown', '#fDownLinks',
                '[id^="lblBanner2618"]', '[id^="lblBanner2697"]', '[id^="lblBanner2624"]', '[id^="lblBanner2626"]', '[id^="lblBanner2627"]',
                '.kutuArama', '.subMenuDiv', '.subMenuHolder', '.sizinIcinMenu', '.htMenu', '.firmaSec', '.fDownLinks',
                # QNB
                '.Header-navigation-top', '.Header-navigation-main', '.Header-navigation-bottom',
                '.online-islemler', '.Header-navigation-mobil',
                # Akbank
                '.headerContent', '.logoBox', '.verisign', '.push',
                '.campaignOtherCampaigns', '.footer-banner', '.listing-box',
                # Yapı Kredi
                '.credit-card-apply', '.credit-card-wrap', '.credit-card-text', '.world-mobil-box', '.home-modal', '.modal-qr-box',
                # Garanti
                '.header-v2', '.footer-v2', '.nav-v2', '.sidebar-v2',
                # Generic
                '.top-nav', '.left-menu', '.breadcrumb',
                '.modal-default', '.icon-close',
                '#documentBody > header', '#documentBody > footer',
                # TOM Bank Hadi
                '.hadi-footer', '[class*="Footer"]', '[class*="Header"]', '.links-container', '.navigation',
                # AHL Pay (Bootstrap-based navbar + footer)
                'header.navbar', 'header.navbar-expand-lg', '.navbar.fixed-top',
                'footer.footer', 'footer.bg-secondary', '#navbarNav',
                '.footer.bg-secondary', '.footer.py-5',
                # Emlak Katılım
                '.o-header', '.o-footer', '.c-breadcrumb', '.o-page__sidebar'
            ]
            for selector in bank_noise_selectors:
                for element in soup.select(selector):
                    try:
                        element.decompose()
                    except Exception:
                        pass

            # 2c. Boilerplate text blocks (Yapı Kredi sitemap links vb.)
            boilerplate_keywords = [
                "world nedir", "worldcard kredi karti basvurusu", "kvkk aydinlatma metni",
                "cerez politikasi", "kredi karti uyelik sozlesmesi", "faiz ve ucretler",
                "ek kart sifre belirleme", "dijital kart guvenli alisveris", "bkm express",
                "masterpass", "visa tek tikla ode", "arac kiralama", "kayip/calinti guvencesi",
                "alisveris guvencesi", "seyahat ve guvence"
            ]
            for tag in soup.find_all(["p", "span", "a", "li"]):
                text = tag.get_text().strip()
                if not text or len(text) > 150: # Only delete if it's a short boilerplate link/text
                    continue
                txt_norm = "".join(c for c in text.lower() if c.isalnum() or c.isspace())
                if any(kw in txt_norm for kw in boilerplate_keywords):
                    try:
                        tag.decompose()
                    except Exception:
                        pass
            
            raw_text = soup.get_text(separator="\n", strip=True)
            if page_title:
                raw_text = f"Sayfa Başlığı: {page_title}\n\n" + raw_text
            
            # --- INTELLIGENT FLATTENING (The fix for fragmented text) ---
            # 1. Remove excessive spaces
            raw_text = re.sub(r'[ \t]+', ' ', raw_text)
            
            # 2. Convert "merdiven" structure back to meaningful sentences.
            # We preserve newlines only for bullet points or numbered lists.
            # Otherwise, we join lines to form proper paragraphs.
            lines = raw_text.split('\n')
            flattened = []
            current_p = ""
            
            for line in lines:
                l = line.strip()
                if not l: continue
                
                # If it's a bullet point or a new section header, start a new line
                if re.match(r'^[\s\-_•*]*[A-ZÇĞİÖŞÜ0-9]', l) and len(l) > 1:
                    if current_p: flattened.append(current_p)
                    current_p = l
                else:
                    if current_p: current_p += " " + l
                    else: current_p = l
            
            if current_p: flattened.append(current_p)
            raw_text = "\n".join(flattened)

        except Exception:
            pass

    # Patterns that identify PURELY boilerplate sentences.
    # IMPORTANT: Only match sentences that are exclusively legal/technical boilerplate.
    # Do NOT add bank names — they appear in participation instructions too.
    junk_patterns = [
        r"operatörlerin kendi tarifeleri",
        r"taksitlendirme süresi bireysel",
        r"bankamızın kampanyayı durdurma hakkı",
        r"kampanya koşullarına uygun olmayan işlemler",
        r"harcama itirazı durumunda",
        r"taksit kısıtı bulunan ürün grupları",
        r"ödüller nakde çevrilemez",
        r"yasal mevzuat gereği",
        r"kullanılmayan puanlar geri alınacaktır",
        r"iptal edilen işlemlerde.*iade edilmez",
        r"zamanaşımına uğrayan hesap",
        r"yatırımcı ilişkileri",
        r"ürün ve hizmet ücretleri",
        r"hakkımızda",
        r"\| \s+ ürdün",
        r"\| \s+ mısır",
        r"\| \s+ tunus",
        r"\| \s+ bahreyn",
        r"\| \s+ türkiye",
        r"\| \s+ güney afrika",
        r"\| \s+ cezayir",
        r"\| \s+ suriye",
        r"\| \s+ pakistan",
        r"\| \s+ libya",
        r"\| \s+ irak",
        r"\| \s+ sudan",
        r"\| \s+ lübnan",
        r"albaraka grubu b\.s\.c\.",
        r"şube ve atm'ler",
        r"anında şifre",
        r"en \| ar",
        r"juzdan'ı indir",
        r"Setur Servis Turistik A\.Ş\. web sitesine yönlendiriliyorsunuz",
        r"Shop&Fly Kolay Seyahat Hattı ile iletişime geçmeniz gerekmektedir",
        r"\d+ Mart \d+ tarihi itibariyle HES Kodu ve PCR Uygulaması zorunluluğu kaldırılmıştır",
        r"Hisse Senedi VIOP Halka Arz Yatırım Fonu",
        r"Altın Hesabı Gümüş Hesabı Platin Hesabı Paladyum Hesabı",
        r"Fatura Ödemeleri Ödeme İste Şans Oyunu Ödemeleri",
        r"EFT - FAST - Havale Güvenli Ödeme",
        r"Kripto Platform Ödemeleri Yurt Dışı Para Transferi",
        r"Vade Faiz Oranı Aylık Ödeme Toplam Geri Ödeme",
        r"Vadeli Hesap Hesaplama Aracı",
        r"İnternet Bankacılığı Ara",
        # TOM Bank Hadi Boilerplate Footer
        r"hadi keşfet", r"biz kimiz\?", r"hadi nedir\?", r"hadi kariyer",
        r"ortaklık yapısı", r"kurumsal yönetim", r"hadi kazan", r"hadi gold",
        r"hadi hesap", r"hadi vadeli \(katılma\) hesabı", r"mega günlük hesap",
        r"altın biriktiren hesap", r"gümüş hesabı", r"hadi yatırım işlemleri",
        r"yatırım hesap açılışı", r"hisse senedi ve halka arz işlemleri",
        r"yatırım fonu işlemleri", r"hadi yatırım sözleşme ve fomları",
        r"hadi kartlarım", r"hadi kredi kartı", r"hadi banka kartı",
        r"hadi sanal kart", r"hadi black kredi kartı", r"hadi krediler",
        r"veresiye kredi", r"taksitli kredi", r"mağazadan alışveriş kredisi",
        r"tom bank black", r"hizmetlerimiz", r"hadi kredi kartı ayrıcalıkları",
        r"tom bank özel bankacılık", r"özel bankacılık hizmetlerimiz",
        r"özel bankacılık segmentlerimiz", r"özel bankacılık iletişim",
        r"önerilen aramalar", r"hadi fırsatları nelerdir\?",
        r"hadi’de nasıl hesap oluşturulur\?", r"ücretler ve limitler için tıklayınız\.",
        # AHL Pay Boilerplate Footer
        r"ahl pay başvuru", r"temsilciliklerimiz", r"logolarımız", r"ücretler ve limitler - bireysel",
        r"ücretler - kurumsal", r"yasal bilgiler", r"sözleşmeler", r"formlar", r"sertifikalar",
        r"sıkça sorulan sorular", r"benimfaturam", r"fiziki altın & gümüş", r"kıymetli maden",
        r"para gönder", r"para yatır", r"para iste", r"fatura öde", r"oyun & dijital kod",
        r"bağış", r"kurumsal kart & hesap", r"foody card", r"androidpos", r"altınpos",
        r"ceppos", r"sanal pos", r"yazar kasa pos", r"finansal özgürlüğünü şimdi keşfet\!",
        r"Bizi Takip Edin Sosyal Medya",
        r"Tüm Hakları Saklıdır",
        r"Hepsiburada Alışveriş Kredisi",
        r"Migros Alışveriş Kredisi",
        r"Hızlı Limit Kartlar ON Kredisi",
        r"tr Ayrıcalıklar Fırsatlar Tanıyın Destek Kartlarımız",
        r"Mevduat Krediler Kartlar Yatırım Sigorta Altın",
        r"Giriş Yap Üye Ol Bireysel Kurumsal",
        r"İnternet Bankacılığı Ara",
        r"Sigorta Araç Sigortaları Kasko Sigortası",
        r"Zorunlu Trafik Sigortası Konut Sigortaları",
        r"Zorunlu Deprem Sigortası - DASK",
        r"Tamamlayıcı Sağlık Sigortası \(TSS\)",
        r"Yurt Dışı Seyahat Sağlık Sigortası",
        r"Tehlikeli Hastalıklar Sigortası",
        r"Pembe Kurdele Hayat Sigortası",
        r"Cep Telefonu Sigortası",
        r"al/sat\s+biriktir\s+otomatik\s+para",
        r"paribu.ya\s+para\s+gönder",
        r"faturasız\s+hatta.*tl\s+yükl",
        r"prev\s+next\s+\w+\s+servis",
        r"detaylı\s+bilgi\s+prev\s+next",
    ]

    # ── Step 2: Line-Level Navigation Filter ──────────────────
    # Devre dışı bırakıldı - AI artık gürültüyü kendisi temizliyor.
    lines = raw_text.split('\n')
    cleaned_lines = []
    for line in lines:
        trimmed = line.strip()
        if trimmed:
            cleaned_lines.append(trimmed)

    # ── Step 3: Noise Snipping & Filtering (Footer/Sidebar) ──────
    # Devre dışı bırakıldı - Önemli detayların silinmesini engelliyoruz.
    noise_markers = []

    # 🛑 THE SANDWICH END (Yasal Limit): 
    # Devre dışı bırakıldı çünkü önemli detaylar (Express Card vb.) yasal uyarıların dibinde olabiliyor.
    LEGAL_END_PATTERNS = []

    # 🛑 BOILERPLATE CHOP (KVKK/Cookie Policy etc.)
    BOILERPLATE_CHOP_MARKERS = [
        "çerez politikası", "cookie policy", "aydınlatma metni", 
        "kişisel verilerin korunması", "legal caution", "yasal bilgilendirme",
        "gizlilik politikası", "çerez kullanımı"
    ]

    final_text = '\n'.join(cleaned_lines)

    title_to_find = og_title or title
    if title_to_find:
        title_lower = title_to_find.lower()
        generic_indicators = [
            "opet mobil", "opet kampanya", "mobil uygulama", "genel kampanya",
            "bankkart kampanya", "maximum fırsat", "kart kampanyası", "ayrıcalıklar",
            "fırsatlar", "ahl pay", "ahlpay", "nays'ın kazandıran", "kart kampanyaları"
        ]
        if any(ind in title_lower for ind in generic_indicators) or len(title_to_find) < 6:
            title_to_find = None

    if title_to_find and len(title_to_find) > 5:
        words = title_to_find.split()
        first_few_words = " ".join(words[:3]) if len(words) >= 3 else title_to_find
        matches = list(re.finditer(re.escape(first_few_words), final_text, re.IGNORECASE))
        if matches:
            target_match = matches[0]
            
            # Find the earliest noise index BEFORE doing the chop to prevent jumping over it
            pre_chop_noise_idx = len(final_text)
            text_lower_pre = final_text.translate({ord('I'): 'ı', ord('İ'): 'i', ord('Ş'): 'ş', ord('Ğ'): 'ğ', ord('Ç'): 'ç', ord('Ö'): 'ö', ord('Ü'): 'ü'}).lower()
            
            for marker in [r"(?i)geçmiş kampanyalarımız", r"(?i)geçmiş kampanyalar", r"(?i)diğer kampanyalarımız", r"(?i)ilgili kampanyalar", r"(?i)benzer kampanyalar"]:
                for match in re.finditer(marker, text_lower_pre, re.MULTILINE):
                    if match.start() >= 100 and match.start() < pre_chop_noise_idx:
                        pre_chop_noise_idx = match.start()

            if 0 < target_match.start() < 4000:
                final_text = final_text[target_match.start():].strip()
            
    # 🛡️ Nays Specific Noise Cleaner
    # Naysapp has a list of links/noise in their pages (e.g. prev, next, paribu, istanbulkart, binbin, hop, martı, öde, para gönder, para iste, nays kart).
    if "nays" in (og_title or "").lower() or "nays" in (title or "").lower() or "nays" in final_text.lower():
        nays_markers = [
            "prev",
            "next",
            "paribu",
            "istanbulkart",
            "istanbul kart",
            "binbin",
            "hop",
            "martı",
            "para gönder",
            "para iste",
        ]
        nays_lines = final_text.split('\n')
        nays_cleaned_lines = []
        for line in nays_lines:
            line_lower = line.lower()
            if any(marker in line_lower for marker in nays_markers) and len(line.strip()) < 100:
                continue
            nays_cleaned_lines.append(line)
        final_text = '\n'.join(nays_cleaned_lines)

    # 🛡️ Yapı Kredi Specific Markers (Fallback/Legacy Safety)
    yapi_header_markers = ["world nedir?", "worldcard kredi kartı başvurusu", "world'e özel hizmetler"]
    final_lower = final_text.lower()
    for marker in yapi_header_markers:
        m_pos = final_lower.find(marker)
        if 0 <= m_pos < 1000:
            restart_pos = final_lower.find("ana sayfa", m_pos)
            if restart_pos != -1 and restart_pos < 2500:
                final_text = final_text[restart_pos:].strip()
                break

    # 🛡️ Crystal / Adios / Play Navigasyon Bloğu Temizleyici
    # Bu siteler sol nav menüsünü sayfa metnine dahil ediyor.
    # Nav başlığı kampanya metninin SONUNDA görünür — bu noktadan itibaren kes.
    niche_nav_chop_markers = [
        # Crystal nav blocks
        "Crystal Kart İle Kazanmanın En Kolay Yolu",
        "Crystal Dünyası Crystal Nedir",
        "Ara Crystal Dünyası",
        "Crystal Nedir? Crystal Kredi Kartı Başvurusu",
        "Yurt İçi Anlaşmalı Otel Restoran İndirimleri",
        "Crystal Ek Kart Varlığa Bağlı Crystal Ayrıcalıkları",
        # Adios nav blocks
        "Adios Kart İle Kazanmanın En Kolay Yolu",
        "Ara Adios Dünyası Adios Nedir",
        "Adios Dünyası Adios Nedir",
        "Adios Nedir? Adios Ayrıcalıkları",
        "Adios Nedir? Adios Kredi Kartı Başvuru",
        "Kampanyalar: Adios Card ile Kazançlı",
        # Play nav blocks
        "Play Kart İle Kazanmanın En Kolay Yolu",
        "Play Nedir? Play Kredi Kartı Başvuru",
        "Play Kredi Kartı Başvuru Puan Puan Kazanma",
        "Kampanyalar: Yapı Kredi Play Kampanyaları",
        "Yapı Kredi Play Kampanyaları - G",
    ]
    # Türkçe büyük harf → küçük harf (Python'un İ→i̇ hatasını önler)
    def _tr_lower(s):
        return (s
            .replace("İ", "i").replace("I", "ı")
            .replace("Ş", "ş").replace("Ğ", "ğ")
            .replace("Ç", "ç").replace("Ö", "ö").replace("Ü", "ü")
            .lower()
            .replace("'", "").replace("'", "")
        )

    for marker in niche_nav_chop_markers:
        match = re.search(re.escape(marker), final_text, re.IGNORECASE)
        if match and match.start() > 500: # Only chop if it's after the main content (not in the header)
            final_text = final_text[:match.start()].strip()
            break

    tr_map = {ord('I'): 'ı', ord('İ'): 'i', ord('Ş'): 'ş', ord('Ğ'): 'ğ', ord('Ç'): 'ç', ord('Ö'): 'ö', ord('Ü'): 'ü'}
    text_lower = final_text.translate(tr_map).lower()
    
    # 🎯 Find the high-confidence LEGAL LIMIT first
    legal_limit_idx = len(final_text)
    for p in LEGAL_END_PATTERNS:
        match = re.search(p, text_lower)
        if match:
            legal_limit_idx = min(legal_limit_idx, match.end() + 10)
    
    # 🎯 Apply high-confidence boilerplate chopping
    for marker in BOILERPLATE_CHOP_MARKERS:
        marker_pos = text_lower.find(marker)
        # Only trip if it is deep in the text (to avoid menu/utility link matches)
        min_safe_pos = max(1500, int(len(text_lower) * 0.45))
        if marker_pos != -1 and marker_pos > min_safe_pos:
            legal_limit_idx = min(legal_limit_idx, marker_pos)
            break
    
    # Prune everything after the legal limit
    if legal_limit_idx < len(final_text):
        final_text = final_text[:legal_limit_idx].strip()
        text_lower = final_text.translate(tr_map).lower()

    # 🎯 Then do NOISE SNIPPING but with a much higher threshold or specific filtering
    # For now, we only snip if the noise marker is very close to the end (Footer).
    min_cut_pos = max(len(final_text) * 0.8, 1500) # Only CUT if it's in the last 20%
    earliest_noise_idx = len(final_text)
    
    # 🛑 HARD CUTS: Metni kökten kesen işaretçiler. 
    # Bunları satır başı/sonu sınırlı yapıyoruz ki cümle içinde geçince metni doğramasın.
    HARD_CUT_MARKERS = [
        r"(?i)^\s*ilgili kampanyalar\s*$",
        r"(?i)^\s*ilginizi çekebilecek (diğer )?kampanyalar\s*$",
        r"(?i)^\s*ilginizi\s+çekebilir\s*$",
        r"(?i)^\s*benzer kampanyalar\s*$",
        r"(?i)^\s*benzer fırsatlar\s*$",
        r"(?i)^\s*ayın kampanyaları\s*$",
        r"(?i)^\s*on'un\s+(kazandıran\s+)?dünyas",
        r"(?i)^\s*diğer\s+on\s+(fırsat|kampanya)",
        r"(?i)^\s*on\s+kredi\s+kartı\s+ayrıcalıkları",
        r"(?i)^\s*diğer kampanyalara göz atın\s*$",
        r"(?i)^\s*sizin için seçtiklerimiz\s*$",
        r"(?i)^\s*öne çıkan ayrıcalıklar\s*$",
        r"(?i)(paylaş|yazdır)$",
        # ⚠️ Yasal hak saklı tutma uyarıları cümle ortasında geçebildiği için HARD_CUT_MARKERS'tan kaldırıldı.
        # Bunları temizlemeyi tamamen Gemini/Yapay zekaya bırakıyoruz.
        r"(?i)miles&smiles dünyası ayrıcalıklarınız",
        r"(?i)mıl programı mıl kazanımı",
        r"(?i)©\s*copyright",
        r"(?i)^\s*tüm hakları saklıdır\s*$",
        # 🛑 İş Bankası Arşiv Gürültüsü
        r"(?i)^\s*geçmiş kampanyalarımız\s*$",
        r"(?i)^\s*geçmiş kampanyalar\s*$",
        r"(?i)^\s*diğer kampanyalarımız\s*$",
        # 🛑 Yapı Kredi Footer Gürültüsü
        r"(?i)^\s*finansal çözümler\s*$",
        r"(?i)^\s*banka ve kredi kartları\s*$",
        r"(?i)^\s*sık ziyaret edilenler\s*$",
        r"(?i)^\s*faydalı sayfalar\s*$",
        r"(?i)^\s*diğer yapı kredi kartları\s*$",
        r"(?i)^\s*öne çıkan kampanyalar\s*$",
        r"(?i)^\s*diğer kampanyalar\s*$",
    ]
    
    is_pep = False
    if title and "pep" in title.lower():
        is_pep = True
    elif og_title and "pep" in og_title.lower():
        is_pep = True
    elif "peple.com.tr" in raw_text.lower() or "pep kart" in raw_text.lower() or "pep ödül" in raw_text.lower():
        is_pep = True

    # 1. First evaluate hard cuts (no minimum percentage threshold required)
    for marker in HARD_CUT_MARKERS:
        if is_pep and ("kampanyayı (durdurma" in marker or "kampanya (koşullarını" in marker):
            continue
        for match in re.finditer(marker, text_lower, re.MULTILINE):
            # Only apply if it's not literally the first sentence of the page (safeguard)
            if match.start() >= 300 and match.start() < earliest_noise_idx: 
                earliest_noise_idx = match.start()
                
    # 2. Then evaluate standard soft noise markers
    for marker in noise_markers:
        for match in re.finditer(marker, text_lower):
            if match.start() >= min_cut_pos and match.start() < earliest_noise_idx:
                earliest_noise_idx = match.start()
    
    if earliest_noise_idx < len(final_text):
        final_text = final_text[:earliest_noise_idx].strip()


    # 🎯 Sub-Step 4.3: Aggressive Cookie Header Removal
    # If the text starts with cookie notification boilerplate, strip it.
    cookie_header_patterns = [
        r"(?i)^çerez kullanımı\s+aydınlatma metni",
        r"(?i)^aydınlatma metni\s+dünya katılım",
        r"(?i)^çerez kullanımı\s+aydınlatma metni\s+dünya katılım",
    ]
    for cp in cookie_header_patterns:
        if re.search(cp, final_text[:200]):
            # Find the first real line after the boilerplate
            # boilerplate usually ends with "kapat" or "kabul et" or just a newline
            final_text = re.sub(cp, "", final_text, count=1).strip()
    
    return final_text
