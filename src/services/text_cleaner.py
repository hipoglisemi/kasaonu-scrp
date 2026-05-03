import re
from bs4 import BeautifulSoup

def clean_campaign_text(raw_text: str, og_title: str = None, title: str = None) -> str:
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
            
            # 1. Global Tag Removal (Kökten ayıklama)
            for element in soup(["script", "style", "nav", "footer", "header", "noscript", "meta", "iframe", "svg", "link"]):
                element.decompose()
            
            # 2. Specific Noise Selectors (Reklam ve Yan Alanlar)
            noise_selectors = [
                # Common Noise
                '.other-campaigns', '.featured-campaigns', '.similar-campaigns', 
                '.campaign-recommendations', 'section.news-carousel', 
                '#related-campaigns', '.campaignDetail-others', '.campaign-recommendations-box',
                '.footer-bottom', '.social-links', '.navigation-wrapper', '.cookie-banner',
                '.top-menu', '.sidebar', '.ad-panel', '.social-share',
                '.slider-container', '.camp-slider', '.camp-slider-container', '.swiper-container',
                
                # Bank Specifics (Research based)
                '#headerUp', '#headerDown', '#headerMain', '#headerSrc', '#headerLoginPanelNew', # TEB
                '.Header-navigation-top', '.Header-navigation-main', '.Header-navigation-bottom', # QNB
                '.online-islemler', '.Header-navigation-mobil', # QNB
                '.headerContent', '.logoBox', '.verisign', '.push', # Akbank
                '.header-v2', '.footer-v2', '.nav-v2', '.sidebar-v2', # Garanti
                '.top-nav', '.left-menu', '.breadcrumb', # Generic
                '.modal-default', '.icon-close', # Modals
                '#documentBody > header', '#documentBody > footer' # Structural
            ]
            for selector in noise_selectors:
                for element in soup.select(selector):
                    element.decompose()
            
            # 3. Content Targeting
            # Use space instead of newline to prevent "ladder text" (Vakifbank issue)
            raw_text = soup.get_text(separator="\n", strip=True)
            
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
        "gizlilik politikası"
    ]

    final_text = '\n'.join(cleaned_lines)
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
        # Only trip if it's deep in the text (don't accidentally cut main content if mentioned early)
        if marker_pos != -1 and marker_pos > 800:
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
    # Markdown listesi (- veya *) olabileceği için başa [\s\-_•*]* ekliyoruz.
    HARD_CUT_MARKERS = [
        r"(?i)ilginizi çekebilecek (diğer )?kampanyalar",
        r"(?i)ilginizi\s+çekebilir",
        r"(?i)benzer kampanyalar",
        r"(?i)benzer fırsatlar",
        r"(?i)diğer kampanyalara göz atın",
        r"(?i)sizin için seçtiklerimiz",
        r"(?i)öne çıkan ayrıcalıklar",
        r"(?i)(paylaş|yazdır)$",
        r"(?i)kampanyayı (durdurma|değiştirme|değişiklik yapma).*(hakkını saklı tutar|hakkına sahiptir)",
        r"(?i)kampanya (koşullarında|şartlarında) (değişiklik yapma|durdurma).*(hakkını saklı tutar|hakkına sahiptir)",
        r"(?i)akbank t\.a\.ş\. kampanyayı durdurma",
        r"(?i)miles&smiles dünyası ayrıcalıklarınız",
        r"(?i)mıl programı mıl kazanımı",
        r"(?i)©\s*copyright",
        r"(?i)tüm hakları saklıdır",
    ]
    
    # 1. First evaluate hard cuts (no minimum percentage threshold required)
    for marker in HARD_CUT_MARKERS:
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

    # ── Step 4: Header Sniper (og_title / title) ─────────────
    # This is the "Secret Sauce" from legacy. If the title is found deep in the text,
    # it means there was a massive navigation menu before it. CHOP IT.
    
    # 🛡️ Sub-Step 4.1: Yapı Kredi Specific Markers (Fallback/Legacy Safety)
    yapi_header_markers = ["world nedir?", "worldcard kredi kartı başvurusu", "world'e özel hizmetler"]
    final_lower = final_text.lower()
    for marker in yapi_header_markers:
        m_pos = final_lower.find(marker)
        if 0 <= m_pos < 1000:
            restart_pos = final_lower.find("ana sayfa", m_pos)
            if restart_pos != -1 and restart_pos < 2500:
                final_text = final_text[restart_pos:].strip()
                break

    # 🎯 Sub-Step 4.2: Universal Sniper (Dynamic)
    headers_to_check = [h for h in [og_title, title] if h and h.strip()]
    for header in headers_to_check:
        h_clean = header.strip()
        h_pos = final_text.find(h_clean)
        if h_pos > 50: # Only trim if there's significant noise before it
            # If the header is too far down, it's definitely noise above
            final_text = final_text[h_pos:].strip()
            break # Found the most reliable marker

    return final_text
