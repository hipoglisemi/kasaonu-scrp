import re
import logging
from typing import List, Set, Dict, Any, Optional
from src.services.negation_filter import check_string_negation, MODIFIER_LIST

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
                           "temassız", "ödemeli", "kartları", "kartlarla",
                           "kartlarıyla", "sahipleri", "müşterileri", "karti", "kart", "bankasi"}

    def _normalize(self, text: str) -> str:
        if not text: return ""
        from src.services.negation_filter import normalize_text
        return normalize_text(text)

    def validate(self, cards: List[str], raw_text: str, bank_key: str, excluded_cards: Optional[List[str]] = None) -> List[str]:
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
                
            # Allow target customer segment strings to pass through directly
            is_customer_segment = any(x in card_norm for x in ["musteri", "kullanici", "uye", "olanlar", "akbankli"])
            if card_norm in CARD_PASSTHROUGH_TERMS or is_customer_segment:
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
        validated = self._run_sniper(validated, raw_text, text_normalized, bank_key, excluded_cards)

        # 6. FINAL DEDUPLICATION: Remove subsets
        final_validated = []
        # Sort by core word count (desc) then string length (desc)
        validated.sort(key=lambda x: (len({w for w in self._normalize(x).split() if len(w) > 2 and w not in self.stop_words}), len(x)), reverse=True)
        
        for v in validated:
            v_norm = self._normalize(v)
            
            # 1. Passthrough bypass: Never deduplicate these key categories
            if v_norm in CARD_PASSTHROUGH_TERMS:
                final_validated.append(v)
                continue
                
            v_core = {w for w in v_norm.split() if len(w) > 2 and w not in self.stop_words}
            if not v_core:
                 if v_norm in text_normalized:
                     final_validated.append(v)
                 continue

            is_subset = False
            power_brands = {"maximum", "maximiles", "bonus", "world", "paraf", "parafly", "axess", "wings", "bankkart"}
            for f in final_validated:
                f_norm = self._normalize(f)
                f_core = {w for w in f_norm.split() if len(w) > 2 and w not in self.stop_words}
                if v_core.issubset(f_core):
                    # 2. Both explicitly present in text bypass: Keep distinct cards listed separately by name
                    if v_norm in text_normalized and f_norm in text_normalized:
                        continue
                    if "troy" in v_norm:
                        continue
                    if len(v_core) == 1 and list(v_core)[0] in power_brands:
                        continue
                    is_subset = True
                    break
            if not is_subset:
                final_validated.append(v)

        # 7. TROY FILTERING: If any card in the list contains "troy", remove generic parent brands
        # to prevent users from assuming Visa/Mastercard versions are also eligible.
        # Targeted parent brand filtering: only remove parent brand if its specific TROY counterpart is listed.
        has_troy = any("troy" in self._normalize(v) for v in final_validated)
        if has_troy:
            parent_brands_with_troy = set()
            for v in final_validated:
                v_norm = self._normalize(v)
                if "troy" in v_norm:
                    generic_brands = {"paraf", "bonus", "world", "maximum", "axess", "bankkart", "maximiles", "wings"}
                    for gb in generic_brands:
                        if gb in v_norm:
                            parent_brands_with_troy.add(gb)
            final_validated = [v for v in final_validated if self._normalize(v) not in parent_brands_with_troy]

        # 7.1 MASTERCARD FILTERING: If any card in the list contains "mastercard", remove generic parent brands
        # to prevent users from assuming Visa/Troy versions are also eligible.
        # Targeted parent brand filtering: only remove parent brand if its specific Mastercard counterpart is listed.
        has_mastercard = any("mastercard" in self._normalize(v) for v in final_validated)
        if has_mastercard:
            parent_brands_with_mc = set()
            for v in final_validated:
                v_norm = self._normalize(v)
                if "mastercard" in v_norm:
                    generic_brands = {"paraf", "bonus", "world", "maximum", "axess", "bankkart", "maximiles", "wings"}
                    for gb in generic_brands:
                        if gb in v_norm:
                            parent_brands_with_mc.add(gb)
            # Also remove generic bank brands if they are present alongside network-specific ones
            if any("bireysel" in self._normalize(v) and "mastercard" in self._normalize(v) for v in final_validated):
                parent_brands_with_mc.add("world")
                parent_brands_with_mc.add("paraf")
                parent_brands_with_mc.add("bonus")
                parent_brands_with_mc.add("maximum")
                parent_brands_with_mc.add("axess")
                parent_brands_with_mc.add("bankkart")
            final_validated = [v for v in final_validated if self._normalize(v) not in parent_brands_with_mc]

        # 8. NETWORK SPECIFICITY FILTERING: If the list contains both a network-specific card
        # (e.g., containing "mastercard", "troy", "visa", "amex") and a generic non-network card
        # whose words are a subset of the network-specific one, remove the generic card.
        network_keywords = {"mastercard", "troy", "visa", "amex"}
        bank_words = set(self._normalize(bank_key).split())
        to_remove = set()
        for i, card_a in enumerate(final_validated):
            a_norm = self._normalize(card_a)
            a_words = set(a_norm.split())
            a_networks = a_words.intersection(network_keywords)
            if not a_networks:
                continue
            
            for card_b in final_validated:
                if card_a == card_b:
                    continue
                b_norm = self._normalize(card_b)
                b_words = set(b_norm.split())
                if not b_words.intersection(network_keywords):
                    a_clean = {w for w in a_words if w not in self.stop_words and w not in network_keywords and w not in bank_words}
                    b_clean = {w for w in b_words if w not in self.stop_words and w not in network_keywords and w not in bank_words}
                    if b_clean and b_clean.issubset(a_clean):
                        to_remove.add(card_b)
                    elif not b_clean and b_norm in a_norm:
                        to_remove.add(card_b)

        if to_remove:
            final_validated = [v for v in final_validated if v not in to_remove]

        # 8.1 NETWORK PREFIX DISTRIBUTION: If a campaign is network-restricted (Mastercard, TROY, Visa),
        # distribute the network prefix to generic bank card names (e.g., TLcard, kredi kartı) to maintain precision.
        network_prefixes = {
            "mastercard": "Mastercard logolu",
            "troy": "TROY logolu",
            "visa": "Visa logolu"
        }
        
        active_prefix = None
        for net, prefix in network_prefixes.items():
            if any(prefix.lower() in self._normalize(v) for v in final_validated):
                active_prefix = prefix
                break
                
        if active_prefix:
            generic_targets = {
                "bireysel kredi kartlari", "bireysel kredi karti",
                "banka kartlari", "banka karti", "bireysel banka kartlari",
                "tlcard", "tl card", "bireysel tlcard", "bireysel tlcardlar",
                "bireysel tlcard'lar", "kredi kartlari", "kredi karti",
                "on odemeli kartlar", "on odemeli kart",
                "crystal", "crystal kart", "metal crystal", "metal crystal kart",
                "adios", "adios card", "adios premium", "play", "play card"
            }
            
            distributed = []
            for c in final_validated:
                c_norm = self._normalize(c)
                is_target = c_norm in generic_targets
                has_any_prefix = any(p.lower() in c_norm for p in network_prefixes.values())
                
                if is_target and not has_any_prefix:
                    prefix_added = f"{active_prefix} {c}"
                    distributed.append(prefix_added)
                else:
                    distributed.append(c)
            final_validated = distributed

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
            window = text_normalized[max(0, idx - 150):min(len(text_normalized), idx + 250)]
            short_window = text_normalized[idx:idx+40]
            
            if any(re.search(rf"\b{re.escape(k)}\b", short_window) for k in service_keywords):
                continue
            
            # Robust suffix-friendly positive keywords check (Turkish agglutinative support)
            positive_kws = ["dahil", "gecerli", "faydalan", "indirim", "firsat", "kazan", "puan", "taksit", "hediye", "kampanya", "alisveris", "odul", "worldpuan"]
            if any(k in window for k in positive_kws):
                any_valid_mention = True
                break
                
            is_this_trap = any(re.search(rf"\b{re.escape(k)}\b", window) for k in privacy_keywords + infra_keywords + app_keywords + service_keywords)
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
        
        # Ziraat Fix: "Bankkart" kelimesi geçince "Bankkart Business/Başak/Genç" kartlarının zorla
        # eklenmesini engellemek için, Ziraat bankasında bankkart kelimesini power_word olmaktan çıkarıyoruz.
        if bank_key.lower() == "ziraat":
            power_words.discard("bankkart")
            
        # Denizbank Fix: Metinde sadece "bonus" geçince normalizer "denizbonus" kelimesini "deniz bonus" 
        # olarak böldüğü için "bonus" gücüyle zorla listeye ekleniyordu. 
        if bank_key.lower() == "denizbank":
            power_words.discard("bonus")

        if len(core_words) == 2 and matched == 1:
            matched_word = next((w for w in core_words if re.search(rf"(?<![a-z0-9])(?<![a-z]\.){re.escape(w)}(?![a-z0-9]|\.[a-z])", text_normalized)), "")
            if matched_word in power_words:
                missing_word = next((w for w in core_words if w != matched_word), "")
                specific_modifiers = set(MODIFIER_LIST).union({"milplus", "prime"})
                if missing_word not in specific_modifiers:
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

    def _run_sniper(self, validated: List[str], raw_text: str, text_normalized: str, bank_key: str, excluded_cards: Optional[List[str]] = None) -> List[str]:
        if not bank_key or bank_key not in self.bank_card_keywords:
            return validated

        if excluded_cards is None:
            excluded_cards = []
        excluded_norm = {self._normalize(c) for c in excluded_cards}

        bank_keywords = self.bank_card_keywords[bank_key]
        validated_norm = {self._normalize(c) for c in validated}

        # 🚨 BANK-SPECIFIC SNIPER TOGGLE
        if bank_key.lower() == "teb":
            return validated

        # 🎯 YAPI KREDİ: "world" SNIPER GUARD
        # "World Mobil", "Worldpuan", "World POS" ibarelerinin kart olarak eklenmesini engelle.
        # Eğer listede sadece Crystal/adios/Play gibi niş kartlar varsa "world" ekleme.
        yapi_kredi_niche_cards = {"crystal", "adios", "play", "metal crystal"}
        
        for kc in bank_keywords:
            kc_norm = self._normalize(kc)

            # 🛡️ YAPI KREDİ WORLD GUARD: "world" sniper'ı,
            # sadece niş kart (Crystal/adios/Play) kampanyalarında "World Mobil/Worldpuan" gibi
            # gürültü ibarelerinin kart olarak eklenmesini engeller.
            if bank_key.lower() == "yapı kredi" and kc_norm == "world":
                generic_modifiers = {"ek kartlar", "ek kart", "sanal kartlar", "sanal kart", "ek", "sanal"}
                non_niche_validated = [
                    v for v in validated
                    if not any(n in self._normalize(v) for n in yapi_kredi_niche_cards)
                    and self._normalize(v) not in generic_modifiers
                ]
                import re as _re_w
                _txt_n = self._normalize(raw_text)
                # Metinde sadece gürültü ibareleri (worldpuan, world mobil vb.) mi var?
                _has_noise = bool(_re_w.search(
                    r"world\s*(?:mobil|pay|puan|pos|uye|uyesi|isyeri|uyg)",
                    _txt_n
                ))
                # Metinde gerçek kart referansı var mı? (worldcard, worldla, worlddan vb.)
                _has_real_card = bool(_re_w.search(
                    r"(?<![a-z0-9])world(?:card|kart|la|le|dan|den|a\b|e\b|i\b|u\b)(?![a-z0-9])",
                    _txt_n
                ))
                if not non_niche_validated and _has_noise and not _has_real_card:
                    continue  # Sadece niş kart var, world sadece gürültüde geçiyor — ekleme

            # 🛡️ EXCLUDED CARDS SHIELD: If AI explicitly excluded this card, NEVER snipe it
            is_shielded = False
            for excl in excluded_norm:
                if kc_norm in excl or excl in kc_norm:
                    is_shielded = True
                    break
            if is_shielded:
                continue

            if self._match_core_words(kc_norm, text_normalized, raw_text, bank_key) and kc_norm not in validated_norm:
                if self._is_in_trap_context(kc_norm, text_normalized, bank_key):
                    continue
                is_generic = kc_norm in ["world", "paraf", "maximum", "bonus", "axess", "bankkart"]
                if check_string_negation(kc, raw_text, bank_key, is_generic_brand=is_generic):
                    continue
                
                # 🛡️ SNIPER NEGATION CONTEXT GUARD: Skip if keyword ONLY appears near negation markers.
                # e.g. "Platinum, Kampüs kart... dahil değildir" should not add Platinum/Kampüs.
                _neg_markers = ["dahil degil", "gecerli degil", "harictir", "haric", "kapsam disi", "gecersiz"]
                def _only_in_negation(kw_norm, txt_norm):
                    import re as _re
                    for m in _re.finditer(rf'(?<![a-z0-9]){_re.escape(kw_norm)}(?![a-z0-9])', txt_norm):
                        window = txt_norm[max(0, m.start()-250):m.end()+250]
                        if not any(neg in window for neg in _neg_markers):
                            return False
                    return True
                if _only_in_negation(kc_norm, text_normalized):
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
