import re
import unicodedata

def tr_lower(text):
    if not text:
        return ""
    # Robust Turkish lowercasing
    tr_map = {ord('I'): 'ı', ord('İ'): 'i', ord('Ş'): 'ş', ord('Ğ'): 'ğ',
              ord('Ç'): 'ç', ord('Ö'): 'ö', ord('Ü'): 'ü'}
    return text.translate(tr_map).lower()

def normalize_text(s):
    # Normalize unicode to handle combined characters like i + dot
    s = unicodedata.normalize('NFKC', s)
    s = tr_lower(s)
    # Further normalize specific chars
    s = s.replace('ı', 'i').replace('ş', 's').replace('ğ', 'g')
    s = s.replace('ü', 'u').replace('ö', 'o').replace('ç', 'c')
    s = s.replace('worlcard', 'worldcard')
    return s.strip()

NEGATION_KEYWORDS = [
    'dahil değil', 'dahil degil', 'dahil değildir', 'dâhil değil', 'dâhil degil', 'dâhil değildir','dahil degildir',
    'geçerli değildir', 'gecerli degildir', 'geçerli degildir',
    'geçerli değil', 'gecerli degil',
    'hariçtir', 'harictir', 'hariç', 'haric',
    'kapsam dışıdır', 'kapsam disidir', 'kapsam dışı', 'kapsam disi',
    'kapsamında değildir', 'kapsaminda degildir', 'kapsamında değil', 'kapsaminda degil',
    'yararlanamaz', 'yararlanamayacaktır', 'puan kazanamaz', 'katılamaz', 'faydalanamaz', 'faydalanamayacaktır', 'geçersizdir', 'gecersizdir',
    'değerlendirilmeyecektir', 'degerlendirilmeyecektir', 'dahil edilmeyecektir', 'dâhil edilmeyecektir',
    'dışında', 'disinda', 'dışındaki', 'disindaki', 'geçerli olmayacaktır', 'gecerli olmayacaktir'
]

def check_string_negation(target_str, full_text, bank_key=None, is_generic_brand=False):
    """
    Helper to check negation for a specific string (can be a card name or brand)
    """
    if not target_str or not full_text:
        return False
        
    target_norm = normalize_text(target_str)
    if target_norm not in full_text:
        return False
    
    # Common suffixes/prefixes that change the card type
    modifiers = r"(?:debit|business|esnaf|kobi|genc|genç|free|flexi|ticari|para|fly|free|eko|eco|platinum|crystal|adios|play|altin|altın|gold|premium|money|gift|paracard|garantione|amex|american express|troy|shop&fly|miles&smiles)"
    
    # Use regex for whole word match
    if is_generic_brand:
        pattern = rf"(?<![a-z0-9]){re.escape(target_norm)}(?![a-z0-9])"
    else:
        pattern = rf"(?<![a-z0-9]){re.escape(target_norm)}(?![a-z0-9])"
        
    has_positive_mention = False
    has_negative_mention = False
    
    for match in re.finditer(pattern, full_text):
        # 🛡️ Generic Brand Protection: Check if this match is a specific variant
        context_around = full_text[max(0, match.start()-30):match.end()+30]
        if is_generic_brand:
            filler = r"(?:\s+(?:bbva|kredi|kartları|kart|logolu))*?\s+"
            if re.search(rf"{modifiers}{filler}{target_norm}|{target_norm}{filler}{modifiers}", context_around):
                continue
                
            point_activity = r"(?:kullanim|harcama|yukleme|kazanim|aktarim|puan|biriktir|cekme)"
            if re.search(rf"{target_norm}\s+(?:{point_activity}|{filler}{point_activity})", context_around):
                continue

        start_search = max(0, match.start() - 150)
        end_search = min(len(full_text), match.end() + 300)
        window = full_text[start_search:end_search]
        
        # 🧪 EVALUATE THIS SPECIFIC OCCURRENCE
        is_this_negated = False
        sentence_has_positive = False
        
        # Find sentence for this occurrence
        rel_pos = match.start() - start_search
        sent_start = max(0, window.rfind(".", 0, rel_pos) + 1)
        sent_end = window.find(".", rel_pos + len(target_norm))
        if sent_end == -1: sent_end = len(window)
        sentence = window[sent_start:sent_end]
        
        # 🛡️ POSITIVE CHECK (Ensuring it's not a negated positive like 'dahil değildir')
        positive_stoppers = r"(?i)(?:^|\s|,)(?:gecerli|faydalanabilir|faydalanabilecektir|yararlanabilir|dahildir|gecerlidir)(?![ \s]*degil)(?:$|\s|,|;|:|\.)"
        # Special check for 'dahil' to ensure it's not followed by 'değil/değildir'
        if re.search(r"(?i)(?:^|\s|,)dahil(?![\s]*degil)", sentence):
             sentence_has_positive = True
             has_positive_mention = True
        
        if re.search(positive_stoppers, sentence):
            sentence_has_positive = True
            has_positive_mention = True
            
        if not sentence_has_positive:
            for neg in NEGATION_KEYWORDS:
                neg_norm = normalize_text(neg)
                if neg_norm in window:
                    pos_of_neg = window.find(neg_norm)
                    card_pos_in_window = window.find(target_norm)
                    
                    if pos_of_neg < card_pos_in_window:
                        part_between = window[pos_of_neg+len(neg_norm):card_pos_in_window]
                    else:
                        part_between = window[card_pos_in_window+len(target_norm):pos_of_neg]
                    
                    # Boundary check
                    has_boundary = re.search(rf"[\.\!\?•\;:][ \s\n]*|\n\s*[-*•]\s*", part_between)
                    has_pos_mid = re.search(positive_stoppers, part_between)
                    
                    if not (has_boundary or has_pos_mid):
                        is_this_negated = True
                        break
        
        if is_this_negated:
            has_negative_mention = True
        else:
            # If any mention is explicitly positive or just a neutral mention with no negation nearby,
            # we consider the card potentially valid.
            has_positive_mention = True

    # 🛡️ FINAL DECISION:
    # If we have ANY positive/neutral mention, trust it over negative ones
    if has_positive_mention:
        return False
    return has_negative_mention

def filter_excluded_cards(cards, text):
    """
    Main entry point for filtering a list of cards based on negative context.
    """
    if not cards or not text:
        return cards
        
    text_normalized = normalize_text(text)
    filtered_cards = []
    
    for card in cards:
        card_clean = normalize_text(card)
        if not card_clean or card_clean == "-":
            filtered_cards.append(card)
            continue
            
        is_excluded = False
        is_generic = card_clean in ["world", "paraf", "maximum", "bonus", "axess"]
        
        # 1. Try full name match
        if check_string_negation(card_clean, text_normalized, is_generic_brand=is_generic):
            is_excluded = True
            
        # 2. If not found or not excluded, try bank-only match for multi-word bank cards
        if not is_excluded and not is_generic:
            bank_names = ["albaraka", "anadolubank", "vakifbank", "denizbank", "akbank", "is bankasi", "isbank", "garanti", "yapi kredi", "qnb", "finansbank", "teb", "kuveyt turk", "turkiye finans"]
            for bank in bank_names:
                if bank in card_clean and len(card_clean.split()) > 1:
                    if check_string_negation(bank, text_normalized, is_generic_brand=True):
                        is_excluded = True
                        break
        
        if not is_excluded:
            filtered_cards.append(card)
        else:
            print(f"   🛡️ Universal Filter: Removed excluded card '{card}'")
            
    return filtered_cards
