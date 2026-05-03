import re
import logging
from typing import List, Set, Dict, Any, Optional
from src.services.negation_filter import check_string_negation

logger = logging.getLogger(__name__)

# Constants moved from parser for better focus
CARD_EXCLUSION_TERMS = {
    "kart puani", "kart puanı", "worldpuan", "maxipuan", "chip-para", "chip para",
    "parafpara", "bankkart lira", "puan", "odul", "ödül", "hediye"
}

CARD_PASSTHROUGH_TERMS = {
    "sanal kart", "ek kart", "sanal", "ek", "sanal kartlar", "ek kartlar"
}

class CardValidator:
    def __init__(self, bank_card_keywords: Dict[str, List[str]]):
        self.bank_card_keywords = bank_card_keywords
        self.stop_words = {"ve", "ile", "için", "&", "and", "the", "logolu", "özellikli",
                           "temassız", "bireysel", "ticari", "ödemeli", "kartları", "kartlarla",
                           "kartlarıyla", "sahipleri", "müşterileri"}

    def _normalize(self, text: str) -> str:
        if not text: return ""
        text = text.lower()
        # Replace Turkish chars for matching
        replacements = {
            'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c'
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        return re.sub(r'[^a-z0-9\s]', ' ', text).strip()

    def validate(self, cards: List[str], raw_text: str, bank_key: str) -> List[str]:
        """
        Main entry point for card validation.
        """
        if not raw_text or not cards:
            return cards

        raw_text_lower = raw_text.lower()
        text_normalized = self._normalize(raw_text_lower)
        validated = []

        for card in cards:
            if not card or not card.strip():
                continue
            
            card_norm = self._normalize(card)

            # 1. EXCLUSION / PASSTHROUGH
            if card_norm in CARD_EXCLUSION_TERMS:
                continue
            if card_norm in CARD_PASSTHROUGH_TERMS:
                validated.append(card)
                continue

            # 2. TRAP GUARDS (Privacy, POS, App)
            if self._is_in_trap_context(card_norm, text_normalized):
                continue

            # 3. DIRECT MATCH & NEGATION
            if card_norm in text_normalized:
                if not check_string_negation(card, raw_text, bank_key):
                    validated.append(card)
                continue

            # 4. CORE WORD MATCHING
            if self._match_core_words(card_norm, text_normalized, raw_text, bank_key):
                validated.append(card)

        # 5. SNIPER RECOVERY (If cards are missing or incomplete)
        validated = self._run_sniper(validated, raw_text, text_normalized, bank_key)

        return list(dict.fromkeys(validated)) # Remove duplicates while preserving order

    def _is_in_trap_context(self, card_norm: str, text_normalized: str) -> bool:
        # Privacy/KVKK
        privacy_keywords = ["toplanacaktir", "islenecektir", "aydinlatma metni", "kisisel veri", "veri sorumlusu"]
        # POS/Infra
        infra_keywords = ["pos", "posu", "pos'u", "sistemi", "uye isyeri", "uyeisyeri", "pos sistemi"]
        # App/Channel
        app_keywords = ["mobil", "uygulama", "uygulamasi", "uygulamasindan", "internet sube", "web sitesi", "online", "subesi"]

        card_idx = text_normalized.find(card_norm)
        if card_idx != -1:
            window = text_normalized[card_idx:card_idx+200]
            if any(k in window for k in privacy_keywords + infra_keywords + app_keywords):
                # Exception: specific cards like 'Opet Worldcard'
                if len(card_norm.split()) < 2:
                    return True
        return False

    def _match_core_words(self, card_norm: str, text_normalized: str, raw_text: str, bank_key: str) -> bool:
        core_words = [w for w in card_norm.split() if len(w) > 2 and w not in self.stop_words]
        if not core_words: return False
        
        matched = sum(1 for w in core_words if w in text_normalized)
        threshold = max(1, int(len(core_words) * 0.6))
        
        if matched >= threshold:
            # Check negation on the first matched core word
            first_match = next((w for w in core_words if w in text_normalized), card_norm)
            if not check_string_negation(first_match, raw_text, bank_key):
                return True
        return False

    def _run_sniper(self, validated: List[str], raw_text: str, text_normalized: str, bank_key: str) -> List[str]:
        if not bank_key or bank_key not in self.bank_card_keywords:
            return validated

        bank_keywords = self.bank_card_keywords[bank_key]
        validated_norm = {self._normalize(c) for c in validated}

        for kc in bank_keywords:
            kc_norm = self._normalize(kc)
            
            if kc_norm in text_normalized and kc_norm not in validated_norm:
                is_generic = kc_norm in ["world", "paraf", "maximum", "bonus", "axess"]
                
                # 🛡️ AKBANK PROTECTION: Navigation/Footer links often contain 'wings', 'free', 'ticari'.
                # If AI didn't find it, and it's a generic bank keyword, don't auto-add it 
                # unless it appears in the raw text with a specific "kart" or "card" suffix 
                # OR it's found in the title.
                if bank_key == "akbank" and kc_norm in ["wings", "free", "ticari", "bank'o card"]:
                    title_norm = self._normalize(raw_text.split('\n')[0])
                    is_in_title = kc_norm in title_norm
                    has_card_suffix = re.search(rf"{kc_norm}\s+(?:kart|card|kredi|ticari)", text_normalized)
                    
                    if not (is_in_title or has_card_suffix):
                        logger.debug(f"Card Sniper: Rejected Akbank keyword '{kc}' - likely navigation noise.")
                        continue

                # 🛡️ Negation Check
                if check_string_negation(kc, text_normalized, bank_key, is_generic_brand=is_generic):
                    continue
                # Upgrade Logic: If "Bonus" is there but "Garanti BBVA Bonus" is found, replace it
                # 🛡️ GARANTI PROTECTION: Don't upgrade/replace generic 'Bonus' with specific 'Money Bonus' etc.
                is_overlap = False
                upgraded = False
                for i, v in enumerate(validated):
                    v_norm = self._normalize(v)
                    if (v_norm in kc_norm or kc_norm in v_norm) and v_norm != kc_norm:
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
                            # Add other product lines if needed...
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

        return validated
