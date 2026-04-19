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
    if "<" in raw_text and ">" in raw_text:
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
            
            # 3. Content Targeting (If we have specific containers, focus but don't limit)
            # We don't want to over-truncate, so we just return the full cleaned body
            raw_text = soup.get_text(separator="\n", strip=True)
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
    ]

    # ── Step 2: Line-Level Navigation Filter ──────────────────
    # Ported from legacy parser to handle plain text gürültüsü
    NAV_PATTERNS = re.compile(
        r'^(ana sayfa|şubeler|iletişim|bize ulaşın|hakkımızda|kvkk|gizlilik|'
        r'çerez|copyright|tüm hakları|instagram|twitter|facebook|linkedin|'
        r'youtube|bizi takip|site haritası|kariyer|başvuru|indir|download|'
        r'yardım ve destek|kampanyalarımız|fırsatlarımız|kurumsal|bireysel|'
        r'şube ve atm|anında şifre|internete özel|hemen indir)$',
        re.IGNORECASE
    )

    lines = raw_text.split('\n')
    cleaned_lines = []
    seen = set()

    for line in lines:
        trimmed = line.strip()
        if not trimmed: continue

        # Filter out short navigation-only lines
        if len(trimmed) < 40:
            if NAV_PATTERNS.match(trimmed.lower()) or len(trimmed) < 5:
                continue
        
        # Deduplication to save tokens
        if trimmed in seen: continue
        seen.add(trimmed)

        sentences = re.split(r'(?<=\.)\s+', trimmed)
        clean_sentences = []
        for sentence in sentences:
            s = sentence.strip()
            if not s: continue
            is_junk = any(re.search(p, s, re.IGNORECASE) for p in junk_patterns)
            if not is_junk:
                clean_sentences.append(s)
        
        if clean_sentences:
            cleaned_lines.append(' '.join(clean_sentences))

    # ── Step 3: Noise Snipping & Filtering (Footer/Sidebar) ──────
    # Instead of blindly cutting at keywords like 'indir', we now distinguish 
    # between 'incidental noise lines' (filter them) and 'footer markers' (cut after them).
    
    noise_markers = [
        r"çerez aydınlatma metni", r"zorunlu çerezler", r"daha fazla bilgi için",
        r"benzer (kampanyalar|fırsatlar)", r"diğer (kampanyalar|fırsatlar)",
        r"ilginizi çekebilecek kampanyalar", r"ilginizi çekebilir", r"sizin için seçtiklerimiz",
        r"popüler markalar", r"bizi takip edin", r"site haritası", r"tüm hakları saklıdır",
        r"copyright", r"en çok tercih edilen kredi kartlarını keşfedin",
        r"fırsatlardan hemen yararlanın", r"seveni, kullananı, bedavası en bol",
        r"başvurunuzu hemen yapın", r"deniz bonus.*en çok tercih edilen",
        r"axess mobil.*hemen indir", r"app store ile indir", r"google play ile indir",
        r"mesajınız gönderildi", r"ana sayfaya dön", r"merak ettikleriniz",
        r"sıkça sorulan sorular", r"başvurum nerede", r"kart şifresi al",
        r"faiz ve ücretler", r"hesap özeti açıklamaları",
        r"kişisel verilerin işlenmesi aydınlatma metni",
        r"bireysel müşteri aydınlatma metni", r"veri sorumlusu sıfatıyla",
        r"e-?mail toplama ve gönderim", r"kampanyayı paylaş", r"maximum mobil.*indir",
        r"bonusflaş.*indirmek için", r"bonusflaş.*ı indirin",
        r"cüzdan\s+kampanyalar\s+ödemeler\s+kartlar", r"qr kod okuyucu",
        r"sosyal medya\s+her hakkı", r"her hakkı.*\.a\.ş", r"çerez politikası\s+bize ulaşın",
        r"bize ulaşın\s+sosyal medya", r"biten kampanyalar",
        r"şekerbank\s+troy\s+thy\s+kampanyası", r"kampanyası\s+\w+\s+kampanyası\s+\w+\s+kampanyası",
        r"retreat kampanyası\s+restoran kampanyası", r"bi\s+dünya\s+fırsat\s+şimdi\s+koçtaş",
        r"tümü\s*\(\d+\)\s*eğitim\s*\(\d+\)", r"ilk bakışta türk telekom",
        r"hemen\s+indir\s+veya\s+app\s+store", r"jüzdan.*ı\s+indir",
        r"prev\s+next\s+\w+\s+servis", r"detaylı\s+bilgi\s+prev\s+next",
        r"ilginizi çekebilecek diğer kampanyalar", r"benzer fırsatları kaçırmayın",
        r"diğer kampanyalara göz atın", r"vodafone\s+yanımda.*indir",
        r"turkcell\s+dijital\s+operatör", r"444 0 333 shop&fly kolay seyahat hattı",
        r"çeşitli markalardaki dilediğiniz ayrıcalığı keşfedin", r"popüler aramalar",
        r"bize ulaşın sosyal medya", r"incelemek için tıklayın", r"hemen giriş yapın",
        r"daha fazla kampanya", r"giriş yaptıktan sonra", r"kampanya detayına geri dön",
        r"ödeme kanallarını göster", r"çok nays şeyler paylaşıyoruz",
        r"neler yapabilirisin, nasıl kazanırsın", r"nays dünyasını keşfet",
        r"altın al/sat biriktir", r"sevdiklerini nays'a davet et",
    ]

    # 🛑 THE SANDWICH END (Yasal Limit): 
    # If we find the final legal disclaimer, we chop EVERYTHING after it 
    # as high-confidence boilerplate.
    LEGAL_END_PATTERNS = [
        r"kampanyayı durdurma ve/veya kampanya koşullarını değiştirme hakkına sahiptir",
        r"kampanyayı durdurma veya kampanya koşullarını değiştirme hakkını saklı tutar",
        r"kampanya koşullarında değişiklik yapma hakkını saklı tutar",
        r"kampanyayı durdurma veya kampanya koşullarını değiştirme hakkına sahiptir",
        r"banka .* kampanyayı dilediği zaman durdurma",
        r"tüm hakları saklıdır"
    ]

    final_text = '\n'.join(cleaned_lines)
    tr_map = {ord('I'): 'ı', ord('İ'): 'i', ord('Ş'): 'ş', ord('Ğ'): 'ğ', ord('Ç'): 'ç', ord('Ö'): 'ö', ord('Ü'): 'ü'}
    text_lower = final_text.translate(tr_map).lower()
    
    # 🎯 Find the high-confidence LEGAL LIMIT first
    legal_limit_idx = len(final_text)
    for p in LEGAL_END_PATTERNS:
        match = re.search(p, text_lower)
        if match:
            # We add some slack to keep the full sentence
            legal_limit_idx = min(legal_limit_idx, match.end() + 10)
    
    # Prune everything after the legal limit
    if legal_limit_idx < len(final_text):
        final_text = final_text[:legal_limit_idx].strip()
        text_lower = final_text.translate(tr_map).lower()

    # 🎯 Then do NOISE SNIPPING but with a much higher threshold or specific filtering
    # For now, we only snip if the noise marker is very close to the end (Footer).
    min_cut_pos = max(len(final_text) * 0.8, 1500) # Only CUT if it's in the last 20%
    earliest_noise_idx = len(final_text)
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
