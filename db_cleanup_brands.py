import os
import re
import logging
import json
from src.database import get_db_session
from src.models import Campaign, Brand, CampaignBrand

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

BLOCKLIST_CANDIDATES = ["Mercedescard"] 
NOISE_MARKERS = [
    r"ilginizi çekebilecek diğer kampanyalar", 
    r"benzer fırsatlar", 
    r"benzer kampanyalar", 
    r"diğer kampanyalar", 
    r"sizin için seçtiklerimiz"
]

PARTIAL_EXCLUSION_WORDS = ["belirli", "seçili", "bazı", "haricindeki", "dışındaki", "markalı", "kategorisindeki"]

def tr_lower(text):
    """Turkish-aware lowering of strings."""
    if not text: return ""
    return text.replace('İ', 'i').replace('I', 'ı').lower()

def clean_ws(t):
    """Normalize all whitespaces."""
    return re.sub(r"\s+", " ", t).strip()

def strip_symbols(t):
    """Ignore symbols like ® or ™."""
    return re.sub(r"[^a-z0-9ıişğüç ]", " ", t)

def scan_all_campaigns_v4_8():
    logger.info("--- 🔍 V4.8 FINAL PRECISION SCAN STARTED ---")
    
    negation_keywords = ["dahil değildir", "hariçtir", "geçerli değildir", "kapsam dışıdır", "dahil edilmeyecektir", "sayılmamaktadır", "taksitlendirilmemektedir"]
    positive_keywords = ["geçerlidir", "dahildir", "geçerli olacaktır"]
    
    scan_report = []
    
    with get_db_session() as db:
        all_campaigns = db.query(Campaign).all()
        logger.info(f"Scanning {len(all_campaigns)} campaigns...")
        
        detected_count = 0
        
        for c in all_campaigns:
            if not c.brands: continue
            
            raw_text = (c.clean_text or c.description or "")
            cond_text = (c.conditions or "")
            full_context = raw_text + "\n" + cond_text
            
            # NORMALIZATION (V4.8 Logic)
            full_context_lower = clean_ws(tr_lower(full_context))
            title_plain = strip_symbols(tr_lower(c.title or ""))
            
            to_remove_negation = []
            to_remove_noise = []
            
            for cb in c.brands:
                brand_name = cb.brand.name
                brand_norm = tr_lower(brand_name)
                brand_plain = strip_symbols(brand_norm)
                
                # --- 1. TITLE & BLOCKLIST GUARD (V4.8: Symbol-Insensitive) ---
                if brand_plain in title_plain or brand_norm in title_plain: continue 
                
                if brand_name in BLOCKLIST_CANDIDATES or brand_norm == "mercedescard":
                    to_remove_noise.append(brand_name)
                    continue

                # --- 2. ILLUSION (RECLAM) CHECK ---
                is_illusion = False
                for marker_pat in NOISE_MARKERS:
                    match = re.search(marker_pat, full_context_lower, re.IGNORECASE)
                    if match:
                        marker_pos = match.start()
                        brand_pat = rf"(?i)\b{re.escape(brand_norm)}\b"
                        found_before = re.search(brand_pat, full_context_lower[:marker_pos])
                        found_after = re.search(brand_pat, full_context_lower[marker_pos:])
                        
                        if found_after and not found_before and brand_norm not in title_plain:
                            is_illusion = True
                            break
                
                if is_illusion:
                    to_remove_noise.append(brand_name)
                    continue

                # --- 3. DISTANCE-BASED EXCLUSION CHECK (V4.7 Logic) ---
                has_exclusion_context = False
                is_explicitly_valid = False
                
                # Brand indices
                brand_indices = [m.start() for m in re.finditer(rf"(?i)\b{re.escape(brand_norm)}\b", full_context_lower)]
                # Negation and positive indices
                neg_indices = [m.start() for neg in negation_keywords for m in re.finditer(re.escape(neg), full_context_lower)]
                pos_indices = [m.start() for pos in positive_keywords for m in re.finditer(re.escape(pos), full_context_lower)]

                for b_idx in brand_indices:
                    # Inclusion check (Window 100)
                    if any(abs(b_idx - p_idx) < 100 for p_idx in pos_indices):
                        is_explicitly_valid = True
                        break
                    
                    # Exclusion check (Window 150)
                    for n_idx in neg_indices:
                        if abs(b_idx - n_idx) < 150:
                            start = min(b_idx, n_idx)
                            end = max(b_idx, n_idx) + len(brand_norm) + 20
                            snippet = full_context_lower[start:end]
                            if any(p in snippet for p in PARTIAL_EXCLUSION_WORDS): continue
                            has_exclusion_context = True
                            break
                    if has_exclusion_context: break
                
                if has_exclusion_context and not is_explicitly_valid:
                    to_remove_negation.append(brand_name)

            if to_remove_negation or to_remove_noise:
                detected_count += 1
                scan_report.append({
                    "id": c.id,
                    "title": c.title,
                    "bank": c.card.bank.name if c.card and c.card.bank else "Banka",
                    "removals_negation": to_remove_negation,
                    "removals_noise": to_remove_noise
                })
        
        # Save MD
        with open("brand_tag_report.md", "w", encoding="utf-8") as f:
            f.write("# 🔍 Kartavantaj Marka Denetim Raporu (V4.7 Final)\n\n")
            f.write(f"**Durum:** Temizlendi | **Bulunan Hata:** {detected_count}\n\n")
            f.write("| Kampanya ID | Banka | Başlık | Hatalı Markalar | Neden |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- |\n")
            for item in scan_report:
                brands = ", ".join(item["removals_negation"] + item["removals_noise"])
                reason = "Kısıtlamalı Marka" if item["removals_negation"] else "İllüzyon / Gürültü"
                f.write(f"| **{item['id']}** | {item['bank']} | {item['title']} | `{brands}` | {reason} |\n")
                
        logger.info(f"V4.7 Complete. Issues found: {detected_count}")

if __name__ == "__main__":
    scan_all_campaigns_v4_8()
