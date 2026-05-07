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
                           "kartlarıyla", "sahipleri", "müşterileri"}

    def _normalize(self, text: str) -> str:
        if not text: return ""
        # Use the same robust normalization as the negation filter
        from src.services.negation_filter import normalize_text
        return normalize_text(text)

    def validate(self, cards: List[str], raw_text: str, bank_key: str) -> List[str]:
        """
        Main entry point for card validation.
        """
        if not raw_text:
            return cards

        raw_text_lower = raw_text.lower()
        text_normalized = self._normalize(raw_text_lower)
        validated = []

        for card in cards:
            if not card or not card.strip():
                continue
            
            card_norm = self._normalize(card)

            # 1. EXCLUSION / PASSTHROUGH
            # Check if card matches any exclusion term (normalized)
            is_excluded = any(self._normalize(excl) == card_norm for excl in CARD_EXCLUSION_TERMS)
            
            # 🚨 EXTRA STRIKT: "lira" is NEVER a card name in any bank, it's always a reward.
            if "lira" in card_norm or is_excluded:
                continue
            if card_norm in CARD_PASSTHROUGH_TERMS:
                validated.append(card)
                continue

            # 2. TRAP GUARDS (Privacy, POS, App)
            if self._is_in_trap_context(card_norm, text_normalized, bank_key):
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

        # 5. SNIPER RECOVERY (If cards are missing or incomplete)
        validated = self._run_sniper(validated, raw_text, text_normalized, bank_key)

        return list(dict.fromkeys(validated)) # Remove duplicates while preserving order

    def _is_in_trap_context(self, card_norm: str, text_normalized: str, bank_key: Optional[str] = None) -> bool:
        # Privacy/KVKK
        privacy_keywords = ["toplanacaktir", "islenecektir", "aydinlatma metni", "kisisel veri", "veri sorumlusu"]
        # POS/Infra
        infra_keywords = ["pos", "posu", "pos'u", "sistemi", "uye isyeri", "uyeisyeri", "pos sistemi"]
        # App/Channel
        app_keywords = ["mobil", "uygulama", "uygulamasi", "uygulamasindan", "internet sube", "web sitesi", "online", "subesi"]
        # Service/Channel Traps
        service_keywords = ["hatti", "kanali", "hizmeti", "portal", "platformu", "numarasi", "adresi"]
        
        # 🛡️ FIX: If the full card name is not in the text, look for its core words
        # This prevents the trap guard from rejecting cards found by the Sniper
        search_term = card_norm
        if card_norm not in text_normalized:
            core_words = [w for w in card_norm.split() if len(w) > 2 and w not in self.stop_words]
            if not core_words: return False
            # Look for the most specific core word
            search_term = core_words[-1]

        # Use strict word boundaries for search_term, excluding URL patterns
        # 🛡️ FIX: Separate fixed-width lookbehinds for Python re compatibility
        pattern = rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(search_term)}(?![a-z0-9]|\.[a-z])"
        occurrences = [m.start() for m in re.finditer(pattern, text_normalized)]
        if not occurrences:
            return False
            
        any_valid_mention = False
        for idx in occurrences:
            window = text_normalized[idx:idx+200]
            short_window = text_normalized[idx:idx+40]

            # 🛡️ IMMEDIATE SERVICE TRAP: If 'hattı', 'kanalı' etc. is right next to the name, it's a trap.
            if any(k in short_window for k in service_keywords):
                continue

            # 🛡️ REFINEMENT: If the card is in a sentence that explicitly says it's included, it's NOT a trap.
            if any(k in window for k in ["dahil", "gecerli", "faydalan", "indirim", "firsat", "kazan"]):
                any_valid_mention = True
                break

            # Check if this specific occurrence is a trap
            is_this_trap = any(k in window for k in privacy_keywords + infra_keywords + app_keywords + service_keywords)
            
            # Additional bank-specific traps
            if bank_key == "ziraat" and "prestij" in card_norm:
                if "katlanan bankkart lira" in window or "sunulan katlanan" in window:
                    is_this_trap = True
            
            if not is_this_trap:
                any_valid_mention = True
                break
        
        return not any_valid_mention

    def _match_core_words(self, card_norm: str, text_normalized: str, raw_text: str, bank_key: str) -> bool:
        core_words = [w for w in card_norm.split() if len(w) > 2 and w not in self.stop_words]
        if not core_words: return False
        
        # 🛡️ FIX: Use whole word matching with regex to avoid partial matches (e.g. 'plus' matching 'milplus')
        # Also avoid URL patterns (e.g. milplus.com.tr)
        matched = 0
        for w in core_words:
            # 🛡️ FIX: Separate fixed-width lookbehinds for Python re compatibility
            pattern = rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(w)}(?![a-z0-9]|\.[a-z])"
            if re.search(pattern, text_normalized):
                matched += 1
        
        # 🛡️ Threshold check: for 1-2 core words, we need 100% match. For 3+, 60%.
        if len(core_words) <= 2:
            threshold = len(core_words)
        else:
            threshold = max(2, int(len(core_words) * 0.6))
        
        if matched >= threshold:
            # Check negation on the first matched core word
            first_match_pattern = rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(w)}(?![a-z0-9]|\.[a-z])"
            first_match = next((w for w in core_words if re.search(first_match_pattern, text_normalized)), card_norm)
            is_generic = first_match in ["world", "paraf", "maximum", "bonus", "axess", "bankkart"]
            negated = check_string_negation(first_match, raw_text, bank_key, is_generic_brand=is_generic)
            if not negated:
                return True
        
        # 🛡️ Special Case: 1/2 match is okay if the missing word is the bank name itself
        if len(core_words) == 2 and matched == 1:
            # Check for missing word using the robust pattern
            pattern = rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(core_words[0])}(?![a-z0-9]|\.[a-z])"
            pattern2 = rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(core_words[1])}(?![a-z0-9]|\.[a-z])"
            
            missing_word = None
            if not re.search(pattern, text_normalized):
                missing_word = core_words[0]
            elif not re.search(pattern2, text_normalized):
                missing_word = core_words[1]
                
            if missing_word and (bank_key in missing_word or "bank" in missing_word):
                # Use the word that IS in the text for negation check
                found_word = core_words[1] if missing_word == core_words[0] else core_words[0]
                found_pattern = rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(found_word)}(?![a-z0-9]|\.[a-z])"
                if not check_string_negation(found_word, raw_text, bank_key):
                    return True

        return False

    def _run_sniper(self, validated: List[str], raw_text: str, text_normalized: str, bank_key: str) -> List[str]:
        if not bank_key or bank_key not in self.bank_card_keywords:
            return validated

        bank_keywords = self.bank_card_keywords[bank_key]
        validated_norm = {self._normalize(c) for c in validated}

        for kc in bank_keywords:
            kc_norm = self._normalize(kc)
            
            # 🛡️ FLEXIBLE MATCH: Use _match_core_words instead of strict 'in' check
            # This allows matching 'VakıfBank Platinum' when the text only says 'Platinum'
            if self._match_core_words(kc_norm, text_normalized, raw_text, bank_key) and kc_norm not in validated_norm:
                # 🛡️ TRAP GUARD in Sniper: Don't snipe cards that are in trap contexts
                if self._is_in_trap_context(kc_norm, text_normalized, bank_key):
                    continue
                
                # 🛡️ VODAFONE REDUNDANCY GUARD: Don't add general 'müşterileri/kullanıcıları' if specific segments are present
                if bank_key == "vodafone" and kc_norm in ["vodafone musterileri", "vodafone kullanicilari"]:
                    # Specific segments are those that contain 'vodafone' but are NOT the generic ones
                    generic_ones = ["vodafone", "vodafone müşterileri", "vodafone kullanıcıları"]
                    has_specific = any("vodafone" in v.lower() and v.lower() not in generic_ones for v in validated)
                    if has_specific:
                        continue
                    
                is_generic = kc_norm in ["world", "paraf", "maximum", "bonus", "axess", "bankkart"]
                
                # 🛡️ Negation Check (CRITICAL)
                # If the card is negated anywhere in the text (sentence or header), NEVER snipe it.
                if check_string_negation(kc, raw_text, bank_key, is_generic_brand=is_generic):
                    continue
                # Upgrade Logic: If "Bonus" is there but "Garanti BBVA Bonus" is found, replace it
                # 🛡️ GARANTI PROTECTION: Don't upgrade/replace generic 'Bonus' with specific 'Money Bonus' etc.
                # 🛡️ Overlap Protection (REFINED for Akbank/Axess)
                # 🛡️ Overlap Protection
                is_overlap = False
                upgraded = False
                for i, v in enumerate(validated):
                    v_norm = self._normalize(v)
                    
                    # 🛡️ Overlap check: Direct substring OR Bank-specific alias logic
                    is_direct_overlap = (v_norm in kc_norm or kc_norm in v_norm) and v_norm != kc_norm
                    b_key_norm = bank_key.lower().replace('ş', 's').replace('ı', 'i').replace('ğ', 'g')
                    is_seker_alias = (b_key_norm == "sekerbank" and "seker" in v_norm and "bonus" in v_norm and "bonus" in kc_norm)
                    
                    if is_direct_overlap or is_seker_alias:
                        
                        # [AKBANK EXCEPTION]: Axess and Bank'O Card Axess are different products
                        if bank_key == "akbank" and "axess" in v_norm and "axess" in kc_norm:
                            if "bank'o" in v_norm or "bank'o" in kc_norm:
                                continue # Keep both Axess and Bank'O Card Axess

                        # [HALKBANK EXCEPTION]: Paraf and Parafly can coexist
                        if bank_key == "halkbank" and v_norm == "paraf" and kc_norm == "parafly":
                            continue
                        if bank_key == "halkbank" and v_norm == "parafly" and kc_norm == "paraf":
                            continue
                        
                        # [ZIRAAT EXCEPTION]: Bankkart base and variants are distinct
                        if bank_key == "ziraat":
                            continue 
                        
                        is_overlap = True
                        # Only upgrade if it's a direct branding upgrade (e.g. Bonus -> Garanti BBVA Bonus)
                        # but NOT if it's a different product (e.g. Bonus -> Money Bonus)
                        is_brand_upgrade = False
                        
                        if bank_key == "garanti":
                            # Only allow upgrade if both have the same product core but one has the bank name
                            v_is_classic = v_norm == "bonus"
                            kc_is_classic = kc_norm == "bonus"
                            v_is_brand_classic = "garanti bbva bonus" in v_norm
                            kc_is_brand_classic = "garanti bbva bonus" in kc_norm
                            
                            if (v_is_classic and kc_is_brand_classic) or (v_is_brand_classic and kc_is_classic):
                                is_brand_upgrade = True
                            elif "money" in v_norm and "money" in kc_norm:
                                is_brand_upgrade = True
                            elif "flexi" in v_norm and "flexi" in kc_norm:
                                is_brand_upgrade = True
                        else:
                            # For other banks, keep the length-based upgrade if one is a subset
                            is_brand_upgrade = True

                        if is_brand_upgrade and len(kc_norm) > len(v_norm):
                            logger.info(f"Card Sniper: Upgrading generic '{v}' to specific '{kc}'")
                            validated[i] = kc
                            upgraded = True
                            break
                
                if not is_overlap and not upgraded:
                    validated.append(kc)

        # 🎯 FINAL SORT: Strictly follow the order in the core campaign text.
        # We look for the main inclusion list (usually starts after "Kampanyaya...")
        main_content = text_normalized
        inclusion_start = text_normalized.find("kampanyaya")
        if inclusion_start != -1:
            main_content = text_normalized[inclusion_start:]

        def get_pos(card_name):
            c_norm = self._normalize(card_name)
            # Find the position of the card in the normalized text
            # This ensures we follow the document's natural order perfectly.
            pos = text_normalized.find(c_norm)
            return pos if pos != -1 else 99999
            
        validated.sort(key=get_pos)

        return validated
