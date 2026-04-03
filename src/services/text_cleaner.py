import re

def clean_campaign_text(raw_text: str) -> str:
    """
    Simple text cleaner to remove boilerplate banking legal terms.
    Works sentence-by-sentence to avoid deleting useful content
    that happens to be on the same line as boilerplate.
    """
    if not raw_text:
        return ""

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
        r"ilginizi çekebilir",
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
    
    final_text = '\n'.join(cleaned_lines)
    text_lower = final_text.lower()
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

    return final_text
