def normalize_brand_name(name: str) -> str:
    """
    Standardizes brand names (Sync with frontend metadataService)
    Ported from kasaonu-scrp/src/services/geminiParser.ts
    """
    if not name:
        return ""

    # 1. Remove common domain extensions and noise suffixes
    initial_clean = name
    replacements = [
        (r"\.com\.tr|\.com|\.net|\.org", ""),
        (r"\s+notebook$|\s+market$|\s+marketleri$|[\s-]online$|[\s-]türkiye$|[\s-]turkiye$", "")
    ]
    
    import re
    for pattern, repl in replacements:
        initial_clean = re.sub(pattern, repl, initial_clean, flags=re.IGNORECASE).strip()

    # 2. Specialized Merges (Canonical Mapping)
    lower = initial_clean.lower()

    # Amazon Group
    if "amazon" in lower: return "Amazon"

    # Migros Group
    if "migros" in lower or lower == "sanal market": return "Migros"

    # Getir Group
    if lower.startswith("getir"): return "Getir"

    # Yemeksepeti Group
    if "yemeksepeti" in lower or lower == "banabi": return "Yemeksepeti"

    # Carrefour Group
    if "carrefoursa" in lower or "carrefour" in lower: return "CarrefourSA"

    # Netflix
    if "netflix" in lower: return "Netflix"

    # Disney
    if "disney" in lower: return "Disney+"

    # Other common ones
    if lower == "monsternotebook": return "Monster"
    if lower == "mediamarkt": return "Media Markt"
    if lower in ["trendyolmilla", "trendyol man"]: return "Trendyol"
    if lower == "hepsiburada": return "Hepsiburada"
    if lower == "n11": return "n11"
    if "boyner" in lower: return "Boyner"
    if "beymen" in lower: return "Beymen"
    if "teknosa" in lower: return "Teknosa"
    if "vatan bilgisayar" in lower: return "Vatan Bilgisayar"
    if "şok market" in lower or lower == "cepte şok": return "Şok"
    if "a101" in lower: return "A101"
    if "bim" in lower: return "BİM"

    # 3. Title Case with Turkish support
    words = initial_clean.split(' ')
    capitalized_words = []
    
    # Helper for Turkish capitalization
    def turkish_capitalize(s):
        if not s: return ""
        if len(s) == 0: return ""
        
        # Handle special Turkish characters for the first letter
        first_char = s[0]
        if first_char == 'i': first_char = 'İ'
        elif first_char == 'ı': first_char = 'I'
        else: first_char = first_char.upper()
        
        # Handle rest of the string
        rest = s[1:].lower().replace('İ', 'i').replace('I', 'ı')
        return first_char + rest

    return ' '.join([turkish_capitalize(w) for w in words]).strip()

def cleanup_brands(brand_input):
    """
    Normalizes a list or string of brands.
    """
    brands = []
    
    if isinstance(brand_input, list):
        brands = [str(b) for b in brand_input]
    elif isinstance(brand_input, str):
        cleaned = brand_input.replace('[', '').replace(']', '').replace('"', '').strip()
        if ',' in cleaned:
            brands = [b.strip() for b in cleaned.split(',')]
        elif cleaned:
            brands = [cleaned]
            
    if not brands:
        return []

    # Forbidden terms (generic words to ignore as brands)
    forbidden_terms = [
        'yapı kredi', 'yapı', 'world', 'worldcard', 'worldpuan', 'puan', 'taksit', 'indirim',
        'kampanya', 'fırsat', 'troy', 'visa', 'mastercard', 'express', 'bonus', 'maximum',
        'axess', 'bankkart', 'paraf', 'card', 'kredi kartı', 'nakit', 'chippin', 'adios', 'play',
        'wings', 'free', 'wings card', 'black', 'mil', 'chip-para', 'puan', 'tl', 'ödeme', 'alisveris', 'alişveriş',
        'juzdan', 'jüzdan', 'bonusflaş', 'bonusflas', 'ayrıcalık', 'avantaj', 'pos', 'üye işyeri', 'üye iş yerleri',
        'mobilya', 'sigorta', 'nalburiye', 'kozmetik', 'akaryakıt', 'giyim', 'aksesuar', 'elektronik', 'market', 'gıda',
        'restoran', 'kafe', 'e-ticaret', 'ulaşım', 'turizm', 'konaklama', 'otomotiv', 'kamu', 'eğitim',
        'genel', 'yok', 'null', 'happy'
    ]
    
    final_brands = []
    seen = set()
    
    for b in brands:
        lower = b.strip().lower()
        if not lower or len(lower) <= 1:
            continue
            
        # Check against forbidden terms
        is_forbidden = False
        for term in forbidden_terms:
            if lower == term or lower.startswith(term + ' '):
                is_forbidden = True
                break
        
        if is_forbidden:
            continue
            
        normalized = normalize_brand_name(b)
        if normalized and normalized not in seen:
            final_brands.append(normalized)
            seen.add(normalized)
            
    return final_brands
