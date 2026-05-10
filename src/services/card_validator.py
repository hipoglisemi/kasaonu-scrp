import re
import logging
from typing import List, Set, Dict, Any, Optional
from src.services.negation_filter import check_string_negation

logger = logging.getLogger(__name__)

# Constants moved from parser for better focus
CARD_EXCLUSION_TERMS = {
    "kart puani", "kart puanı", "worldpuan", "maxipuan", "chip-para", "chip para",
    "parafpara", "bankkart lira", "puan", "odul", "ödül", "hediye", "bankkartlira"
}

CARD_PASSTHROUGH_TERMS = {
    "sanal kart", "ek kart", "sanal", "ek", "sanal kartlar", "ek kartlar",
    "turkcell musterileri", "vodafone musterileri", "türk telekom musterileri",
    "bireysel musteriler", "ticari kartlar", "tum kartlar", "tum musteriler"
}

class CardValidator:
    def __init__(self, bank_card_keywords: Dict[str, List[str]]):
        self.bank_card_keywords = bank_card_keywords
        self.stop_words = {"ve", "ile", "için", "&", "and", "the", "logolu", "özellikli",
                           "temassız", "bireysel", "ticari", "ödemeli", "kartları", "kartlarla",
                           "kartlarıyla", "sahipleri", "müşterileri", "karti", "kart", "bankasi", "banka", "kredi"}

    def _normalize(self, text: str) -> str:
        if not text: return ""
        from src.services.negation_filter import normalize_text
        return normalize_text(text)

    def validate(self, cards: List[str], raw_text: str, bank_key: str) -> List[str]:
        if not raw_text:
            return cards

        text_normalized = self._normalize(raw_text)
        validated = []

        for card in cards:
            if not card or not card.strip():
                continue
            
            card_norm = self._normalize(card)

            # 1. EXCLUSION / PASSTHROUGH
            is_excluded = any(self._normalize(excl) == card_norm for excl in CARD_EXCLUSION_TERMS)
            if "lira" in card_norm or is_excluded:
                continue
            if card_norm in CARD_PASSTHROUGH_TERMS:
                validated.append(card)
                continue

            # 2. TRAP GUARDS
            # 🚨 RELAXED FOR TEB: TEB texts are very messy and often mix card names with app/web keywords.
            if bank_key.lower() != "teb" and self._is_in_trap_context(card_norm, text_normalized, bank_key):
                continue

            # 3. DIRECT MATCH & NEGATION
            if card_norm in text_normalized:
                is_generic = card_norm in ["world", "paraf", "maximum", "bonus", "axess", "bankkart"]
                if not check_string_negation(card, raw_text, bank_key, is_generic_brand=is_generic):
                    validated.append(card)
                continue

            # 4. CORE WORD MATCHING
            if self._match_core_words(card_norm, text_normalized, raw_text, bank_key):
                validated.append(card)

        # 5. SNIPER RECOVERY
        validated = self._run_sniper(validated, raw_text, text_normalized, bank_key)

        # 6. FINAL DEDUPLICATION: Remove subsets
        final_validated = []
        # Sort by core word count (desc) then string length (desc)
        validated.sort(key=lambda x: (len({w for w in self._normalize(x).split() if len(w) > 2 and w not in self.stop_words}), len(x)), reverse=True)
        
        for v in validated:
            v_norm = self._normalize(v)
            v_core = {w for w in v_norm.split() if len(w) > 2 and w not in self.stop_words}
            if not v_core:
                 if v_norm in text_normalized:
                     final_validated.append(v)
                 continue

            is_subset = False
            power_brands = {"maximum", "maximiles", "bonus", "world", "paraf", "axess", "wings", "bankkart"}
            for f in final_validated:
                f_norm = self._normalize(f)
                f_core = {w for w in f_norm.split() if len(w) > 2 and w not in self.stop_words}
                if v_core.issubset(f_core):
                    if len(v_core) == 1 and list(v_core)[0] in power_brands:
                        continue
                    is_subset = True
                    break
            if not is_subset:
                final_validated.append(v)

        def get_pos(card_name):
            c_norm = self._normalize(card_name)
            pos = text_normalized.find(c_norm)
            return pos if pos != -1 else 99999
            
        final_validated.sort(key=get_pos)
        return list(dict.fromkeys(final_validated))

    def _is_in_trap_context(self, card_norm: str, text_normalized: str, bank_key: Optional[str] = None) -> bool:
        privacy_keywords = ["toplanacaktir", "islenecektir", "aydinlatma metni", "kisisel veri", "veri sorumlusu", 
                            "hakkini sakli tutar", "sakli tutar", "degisiklik yapma", "durdurma hakki"]
        infra_keywords = ["pos", "posu", "pos'u", "sistemi", "uye isyeri", "uyeisyeri", "pos sistemi"]
        app_keywords = ["mobil", "uygulama", "uygulamasi", "uygulamasindan", "internet sube", "web sitesi", "online", "subesi"]
        service_keywords = ["hatti", "kanali", "hizmeti", "portal", "platformu", "numarasi", "adresi"]
        
        search_term = card_norm
        if card_norm not in text_normalized:
            core_words = [w for w in card_norm.split() if len(w) > 2 and w not in self.stop_words]
            if not core_words: return False
            search_term = core_words[-1]

        pattern = rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(search_term)}(?![a-z0-9]|\.[a-z])"
        occurrences = [m.start() for m in re.finditer(pattern, text_normalized)]
        if not occurrences:
            return False
            
        any_valid_mention = False
        for idx in occurrences:
            window = text_normalized[idx:idx+200]
            short_window = text_normalized[idx:idx+40]
            if any(k in short_window for k in service_keywords):
                continue
            if any(k in window for k in ["dahil", "gecerli", "faydalan", "indirim", "firsat", "kazan"]):
                any_valid_mention = True
                break
            is_this_trap = any(k in window for k in privacy_keywords + infra_keywords + app_keywords + service_keywords)
            if not is_this_trap:
                any_valid_mention = True
                break
        return not any_valid_mention

    def _match_core_words(self, card_norm: str, text_normalized: str, raw_text: str, bank_key: str) -> bool:
        core_words = [w for w in card_norm.split() if len(w) > 2 and w not in self.stop_words]
        if not core_words: return False
        
        matched = 0
        for w in core_words:
            pattern = rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(w)}(?![a-z0-9]|\.[a-z])"
            if re.search(pattern, text_normalized):
                matched += 1
        
        if len(core_words) <= 3:
            threshold = len(core_words)
        else:
            threshold = max(3, int(len(core_words) * 0.75))
            
        # 🛡️ RELAXED THRESHOLD FOR 2-WORD CARDS
        # If it has 2 words and at least one matches, we check if it's a 'Power Word' for this bank
        power_words = {"maximum", "maximiles", "privia", "bankamatik", "bonus", "axess", "wings", "world", "paraf", "bankkart"}
        if len(core_words) == 2 and matched == 1:
            matched_word = next((w for w in core_words if re.search(rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(w)}(?![a-z0-9]|\.[a-z])", text_normalized)), "")
            if matched_word in power_words:
                matched = threshold # Force pass
        
        if matched >= threshold:
            # 🛡️ BANK NAME GUARD
            bank_words = {w for w in self._normalize(bank_key).split() if len(w) > 2}
            matched_words = {w for w in core_words if re.search(rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(w)}(?![a-z0-9]|\.[a-z])", text_normalized)}
            
            if matched_words.issubset(bank_words) and len(matched_words) < len(core_words):
                return False

            first_match = next((w for w in core_words if re.search(rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(w)}(?![a-z0-9]|\.[a-z])", text_normalized)), card_norm)
            is_generic = first_match in ["world", "paraf", "maximum", "bonus", "axess", "bankkart"]
            if not check_string_negation(first_match, raw_text, bank_key, is_generic_brand=is_generic):
                return True
        
        if len(core_words) == 2 and matched == 1:
            missing_word = None
            if not re.search(rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(core_words[0])}(?![a-z0-9]|\.[a-z])", text_normalized):
                missing_word = core_words[0]
            elif not re.search(rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(core_words[1])}(?![a-z0-9]|\.[a-z])", text_normalized):
                missing_word = core_words[1]
                
            if missing_word and (bank_key in missing_word or "bank" in missing_word):
                found_word = core_words[1] if missing_word == core_words[0] else core_words[0]
                if not check_string_negation(found_word, raw_text, bank_key):
                    return True
        return False

    def _run_sniper(self, validated: List[str], raw_text: str, text_normalized: str, bank_key: str) -> List[str]:
        if not bank_key or bank_key not in self.bank_card_keywords:
            return validated

        bank_keywords = self.bank_card_keywords[bank_key]
        validated_norm = {self._normalize(c) for c in validated}

        # 🚨 BANK-SPECIFIC SNIPER TOGGLE
        if bank_key.lower() == "teb":
            return validated

        for kc in bank_keywords:
            kc_norm = self._normalize(kc)
            if self._match_core_words(kc_norm, text_normalized, raw_text, bank_key) and kc_norm not in validated_norm:
                if self._is_in_trap_context(kc_norm, text_normalized, bank_key):
                    continue
                is_generic = kc_norm in ["world", "paraf", "maximum", "bonus", "axess", "bankkart"]
                if check_string_negation(kc, raw_text, bank_key, is_generic_brand=is_generic):
                    continue
                
                is_overlap = False
                upgraded = False
                for i, v in enumerate(validated):
                    v_norm = self._normalize(v)
                    kc_core = {w for w in kc_norm.split() if len(w) > 2 and w not in self.stop_words}
                    v_core = {w for w in v_norm.split() if len(w) > 2 and w not in self.stop_words}
                    is_direct_overlap = (v_norm in kc_norm or kc_norm in v_norm) and v_norm != kc_norm
                    is_core_overlap = (kc_core.issubset(v_core) or v_core.issubset(kc_core)) and kc_core != v_core
                    
                    if is_direct_overlap or is_core_overlap:
                        is_overlap = True
                        if len(kc_core) > len(v_core):
                            validated[i] = kc
                            upgraded = True
                            break
                
                if not is_overlap and not upgraded:
                    validated.append(kc)
        return validated
