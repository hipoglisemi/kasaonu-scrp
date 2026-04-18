import re
from bs4 import BeautifulSoup

def clean_campaign_text(raw_text: str, og_title: str = None) -> str:
    """
    Simple text cleaner to remove boilerplate banking legal terms.
    Works sentence-by-sentence to avoid deleting useful content
    that happens to be on the same line as boilerplate.
    
    og_title: If provided (from <meta og:title>), used to trim SPA header
              navigation noise by finding the real campaign title in the text.
    """
    if not raw_text:
        return ""

    # If the text contains HTML tags, extract clean text first
    if "<" in raw_text and ">" in raw_text:
        try:
            soup = BeautifulSoup(raw_text, "html.parser")
            for element in soup(["script", "style", "nav", "noscript", "header", "footer"]):
                element.decompose()
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

    # Split text into sentences and filter
    lines = raw_text.split('\n')
    cleaned_lines = []
    for line in lines:
        trimmed = line.strip()
        if not trimmed: continue
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

    # ── Boilerplate Sniper (Truncate at noise sections) ──
    noise_markers = [
        r"çerez aydınlatma metni",
        r"zorunlu çerezler",
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
        r"kişisel verilerin işlenmesi aydınlatma metni",
        r"bireysel müşteri aydınlatma metni",
        r"veri sorumlusu sıfatıyla",
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
        r"retreat kampanyası\s+restoran kampanyası",
        # Türk Telekom footer / masonry
        r"bi\s+dünya\s+fırsat\s+şimdi\s+koçtaş",
        r"tümü\s*\(\d+\)\s*eğitim\s*\(\d+\)",
        r"ilk bakışta türk telekom",
        # Akbank HEMEN İNDİR footer
        r"hemen\s+indir\s+veya\s+app\s+store",
        r"jüzdan.*ı\s+indir",
        # Generic cross-campaign / sidebar navigation
        r"prev\s+next\s+\w+\s+servis",
        r"detaylı\s+bilgi\s+prev\s+next",
        r"ilginizi çekebilecek diğer kampanyalar",
        r"benzer fırsatları kaçırmayın",
        r"diğer kampanyalara göz atın",
        # Vodafone/Turkcell footer
        r"vodafone\s+yanımda.*indir",
        r"turkcell\s+dijital\s+operatör",
        r"444 0 333 shop&fly kolay seyahat hattı",
        r"çeşitli markalardaki dilediğiniz ayrıcalığı keşfedin",
        r"popüler aramalar",
        r"bize ulaşın sosyal medya",
        r"incelemek için tıklayın",
        r"hemen giriş yapın",
        r"daha fazla kampanya",
        r"giriş yaptıktan sonra",
        r"kampanya detayına geri dön",
        r"ödeme kanallarını göster",
        # Nays footer patterns
        r"çok nays şeyler paylaşıyoruz",
        r"neler yapabilirisin, nasıl kazanırsın",
        r"nays dünyasını keşfet",
        r"altın al/sat biriktir",
        r"sevdiklerini nays'a davet et",
    ]
    
    final_text = '\n'.join(cleaned_lines)
    # Tüm Türkçe karakterleri eksiksiz olarak küçük harfe çevirme garantisi veren harita
    tr_map = {ord('I'): 'ı', ord('İ'): 'i', ord('Ş'): 'ş', ord('Ğ'): 'ğ', ord('Ç'): 'ç', ord('Ö'): 'ö', ord('Ü'): 'ü'}
    text_lower = final_text.translate(tr_map).lower()
    earliest_noise_idx = len(final_text)
    
    # Minimum position guard: ignore noise markers in the first 300 chars
    # or first 15% of text — they're likely navigation menu items, not footer.
    min_noise_pos = max(300, int(len(final_text) * 0.15))
    
    for marker in noise_markers:
        for match in re.finditer(marker, text_lower):
            if match.start() >= min_noise_pos and match.start() < earliest_noise_idx:
                earliest_noise_idx = match.start()
    
    if earliest_noise_idx < len(final_text):
        final_text = final_text[:earliest_noise_idx].strip()

    # ── Yapı Kredi Header Cleaning ──
    # worldcard.com.tr pages have nav menus before campaign content
    yapi_header_markers = ["world nedir?", "worldcard kredi kartı başvurusu", "world'e özel hizmetler"]
    final_lower = final_text.lower()
    for marker in yapi_header_markers:
        m_pos = final_lower.find(marker)
        if 0 <= m_pos < 1000:
            restart_pos = final_lower.find("ana sayfa", m_pos)
            if restart_pos != -1 and restart_pos < 2500:
                final_text = final_text[restart_pos:].strip()
                break

    # ── og:title Header Sniper ──
    # For SPA sites (e.g. Opet), the rendered text starts with nav menu noise.
    # If the real campaign title (from <meta og:title>) is found in the text,
    # trim everything before it so only campaign content reaches the AI.
    if og_title and og_title.strip():
        og_pos = final_text.find(og_title.strip())
        if og_pos > 50:  # Only trim if there's actual noise before it
            final_text = final_text[og_pos:].strip()

    return final_text
