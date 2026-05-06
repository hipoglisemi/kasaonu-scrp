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
    s = s.replace('â', 'a').replace('î', 'i').replace('û', 'u')
    s = s.replace('worlcard', 'worldcard')
    # Standardize apostrophes
    s = s.replace('’', "'").replace('‘', "'")
    return s.strip()

NEGATION_KEYWORDS = [
    'dahil değil', 'dahil degil', 'dahil değildir', 'dâhil değil', 'dâhil degil', 'dâhil değildir','dahil degildir',
    'dahil olmadığını', 'dahil olmadigini', 'dâhil olmadığını', 'dâhil olmadigini',
    'geçerli değildir', 'gecerli degildir', 'geçerli degildir',
    'geçerli değil', 'gecerli degil',
    'geçerli olmadığını', 'gecerli olmadigini',
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
    full_text = normalize_text(full_text)
    if target_norm not in full_text:
        return False
    
    # Common suffixes/prefixes that change the card type
    modifiers = r"(?i)(?:debit|business|esnaf|kobi|genc|genç|free|flexi|ticari|bank['’\s]*o['’\s]*card|bank['’\s]*o['’\s]*|para|fly|free|eko|eco|platinum|crystal|adios|play|altin|altın|gold|premium|money|gift|paracard|garantione|amex|american express|troy|shop&fly|miles&smiles|ucretsiz|ücretsiz|basak|başak|prestij)"
    
    # Use regex for whole word match, but allow common Turkish suffixes
    # We allow: lar, ler, li, lu, lü, lı, nin, nın, in, un, ün, a, e, yla, yle etc.
    turkish_suffixes = r"(?:lar|ler|lı|li|lu|lü|lar|ler|n|ın|in|un|ün|a|e|ya|ye|yı|yi|yu|yü|da|de|dan|den|yla|yle)?"
    pattern = rf"(?<![a-z0-9]){re.escape(target_norm)}{turkish_suffixes}(?![a-z0-9])"
        
    has_positive_mention = False
    has_negative_mention = False
    
    for match in re.finditer(pattern, full_text):
        if is_generic_brand:
            filler = r"(?:\s+(?:bbva|kredi|kartları|kart|logolu|lira|pos))*?\s+"
            point_activity = r"(?:kullanim|harcama|yukleme|kazanim|aktarim|puan|lira|biriktir|cekme|pos)"
            
            # Check prefix (e.g. "Axess Bonus")
            prefix = full_text[max(0, match.start()-20):match.start()]
            if re.search(rf"{modifiers}{filler}$", prefix):
                continue
            
            # Check suffix (e.g. "Bonus Genç", "Bonus Puan")
            suffix = full_text[match.end():match.end()+30]
            if re.search(rf"^{filler}(?:{modifiers}|{point_activity})", suffix):
                continue

        start_search = max(0, match.start() - 150)
        end_search = min(len(full_text), match.end() + 300)
        window = full_text[start_search:end_search]
        
        # 🧪 EVALUATE THIS SPECIFIC OCCURRENCE
        is_this_negated = False
        sentence_has_positive = False
        
        # Find sentence for this occurrence (respecting dots, semicolons and colons)
        rel_pos = match.start() - start_search
        
        # Search for any boundary characters: . ; :
        boundaries = [window.rfind(".", 0, rel_pos), window.rfind(";", 0, rel_pos), window.rfind(":", 0, rel_pos)]
        sent_start = max(0, max(boundaries) + 1)
        
        # Search forward for boundaries
        f_boundaries = [window.find(".", rel_pos + len(target_norm)), 
                        window.find(";", rel_pos + len(target_norm)),
                        window.find(":", rel_pos + len(target_norm))]
        # Filter out -1s
        f_boundaries = [b for b in f_boundaries if b != -1]
        sent_end = min(f_boundaries) if f_boundaries else len(window)
        
        sentence = window[sent_start:sent_end]
        
        # 🛡️ POSITIVE CHECK (Ensuring it's not a negated positive like 'dahil değildir')
        positive_stoppers = r"(?i)(?:^|\s|,)(?:gecerli|faydalanabilir|faydalanabilecektir|yararlanabilir|dahildir|gecerlidir)(?![ \s]*degil)(?:$|\s|,|;|:|\.)"
        # Special check for 'dahil' to ensure it's not followed by 'değil/değildir/olmadığını'
        # normalized sentence will have 'dahil' and 'olmadigini'
        if re.search(r"(?i)(?:^|\s|,)dahil(?![\s]*(?:degil|olmadigini|olmadigi))", sentence):
            sentence_has_positive = True
            has_positive_mention = True
        
        if re.search(positive_stoppers, sentence):
            sentence_has_positive = True
            has_positive_mention = True
            
        if not sentence_has_positive:
            for neg in NEGATION_KEYWORDS:
                neg_norm = normalize_text(neg)
                # 🎯 FIX v2: Search in SENTENCE first, then fall back to window.
                # This prevents cross-sentence false matches.
                if neg_norm in sentence:
                    neg_pos_in_sentence = sentence.find(neg_norm)
                    card_pos_in_sentence = rel_pos - sent_start
                    if neg_pos_in_sentence < card_pos_in_sentence:
                        part_between = sentence[neg_pos_in_sentence+len(neg_norm):card_pos_in_sentence]
                    else:
                        part_between = sentence[card_pos_in_sentence+len(target_norm):neg_pos_in_sentence]
                    
                    has_pos_mid = re.search(positive_stoppers, part_between)
                    if not has_pos_mid:
                        is_this_negated = True
                        break
                elif neg_norm in window:
                    # Fallback: negation keyword in wider window but not in same sentence
                    pos_of_neg = window.find(neg_norm)
                    card_pos_in_window = rel_pos
                    
                    if pos_of_neg < card_pos_in_window:
                        part_between = window[pos_of_neg+len(neg_norm):card_pos_in_window]
                    else:
                        part_between = window[card_pos_in_window+len(target_norm):pos_of_neg]
                    
                    has_boundary = re.search(rf"[\.!\?•;][ \s\n]*|\n\s*[-*•]\s*", part_between)
                    has_pos_mid = re.search(positive_stoppers, part_between)
                    is_very_close = len(part_between) < 80
                    
                    # 🎯 FIX: If there is a boundary (sentence end), we MUST respect it.
                    # is_very_close should only help if there is NO clear boundary.
                    if not has_boundary and not has_pos_mid:
                        is_this_negated = True
                        break
        
        if is_this_negated:
            has_negative_mention = True
        else:
            # If any mention is explicitly positive or just a neutral mention with no negation nearby,
            # we consider the card potentially valid.
            has_positive_mention = True

    # 🛡️ FINAL DECISION (v3):
    # - If we have an explicit NEGATIVE mention, we are very skeptical.
    # - A 'Neutral' mention (no negation but no positive keyword) should NOT override a negation.
    # - Only an explicit POSITIVE keyword (dahildir, gecerlidir) in the SAME sentence/context
    #   might potentially override it, but to be safe, if there's ANY confirmed negation
    #   in the text for this card, we exclude it from the main cards list.
    
    if has_negative_mention:
        # Safety first: If it's negated anywhere, it shouldn't be in the main list.
        # It can still be mentioned in conditions by the AI.
        return True
        
    return False

def filter_excluded_cards(cards, text, bank_name=None):
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
        is_generic = card_clean in ["world", "paraf", "maximum", "bonus", "axess", "bankkart"]
        
        # 1. Try full name match
        if check_string_negation(card_clean, text_normalized, is_generic_brand=is_generic):
            is_excluded = True
            
        # 2. Bank-name fallback: ONLY if the full card name is NOT in the text at all.
        #    If Step 1 found the card and said "not negated", trust that result.
        card_found_in_text = card_clean in text_normalized
        if not is_excluded and not is_generic and not card_found_in_text:
            bank_names = ["albaraka", "anadolubank", "vakifbank", "denizbank", "akbank", "is bankasi", "isbank", "garanti", "yapi kredi", "qnb", "finansbank", "teb", "kuveyt turk", "turkiye finans", "ziraat", "bankkart"]
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
