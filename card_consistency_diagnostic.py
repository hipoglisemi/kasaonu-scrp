import os
import sys
import re
from typing import List, Set

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.models import Campaign, Bank, Card
from src.database import get_db_session

# Common card keywords to look for
CARD_KEYWORDS = {
    "Axess", "Wings", "Free", "Bank'O Card", "Akbank Kart",
    "Bonus", "Miles & Smiles", "Shop & Fly", "American Express", "Amex", "Bonus Flexi", "Bonus Genç", "Paracard",
    "Maximum", "Maximiles", "Privia", "Bankamatik Kartı",
    "World", "Worldcard", "Crystal", "Adios", "Taksitçi", "Play", "Bank Kart",
    "Paraf", "Parafly", "Halkcard",
    "Bankkart", "Ziraat", "Bankkart Genç",
    "DenizBonus", "DenizBank Black", "Net Kart", "Afili Bonus",
    "CardFinans", "QNB Finansbank", "Miles&Smiles QNB", "Enpara",
    "TEB Bonus", "CEPTETEB",
    "Sağlam Kart", "Miles & Smiles Kuveyt Türk",
    "Happy Card", "Âlâ Kart",
    "TROY", "Business", "Ticari", "Şirket", "Kurumsal", "Esnaf", "KOBİ",
    "Platinum", "Gold", "Black", "Elite", "Premier", "Privé"
}

def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    replacements = {
        'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = re.sub(r'[^a-z0-9 ]', ' ', text)
    return " ".join(text.split())

def is_in_exclusion_context(text: str, pos: int) -> bool:
    """Checks if the card name at 'pos' is preceded by exclusion keywords."""
    window = text[max(0, pos-100):pos].lower()
    exclusion_keywords = ["dahil degildir", "harictir", "gecerli degildir", "kapsam disidir", "haricinde", "haric"]
    for kw in exclusion_keywords:
        if kw in window:
            return True
    return False

def is_in_footer_jumble(text: str, pos: int) -> bool:
    """Checks if the word is part of a long list of card names (likely a site footer/menu)."""
    # Look for dense sequences of card-like words in a 200-char window
    window = text[max(0, pos-100):min(len(text), pos+100)].lower()
    # Remove common punctuation to avoid splitting
    window = re.sub(r'[^a-z0-9 ]', ' ', window)
    words = set(window.split())
    card_keywords = {"axess", "wings", "free", "bonus", "maximum", "world", "paraf", "bankkart", "troy", "ticari", "platinum"}
    count = len(words.intersection(card_keywords))
    return count >= 5 # 5+ different card types in a small window is likely a menu

def find_missing_cards():
    print("🔍 Starting Comprehensive Card Consistency Diagnostic...")
    
    mismatches = []
    bank_stats = {} # {bank_name: {"total": 0, "mismatched": 0}}
    
    with get_db_session() as db:
        campaigns = db.query(Campaign).join(Card).join(Bank).filter(
            Campaign.is_active == True
        ).all()
        
        print(f"📊 Scanning {len(campaigns)} active campaigns across all banks...")
        
        for c in campaigns:
            bank_name = c.card.bank.name if c.card and c.card.bank else "Unknown"
            if bank_name not in bank_stats:
                bank_stats[bank_name] = {"total": 0, "mismatched": 0}
            bank_stats[bank_name]["total"] += 1

            raw_clean_text = (c.clean_text or "").lower()
            clean_text_norm = normalize(raw_clean_text)
            
            if not clean_text_norm:
                raw_clean_text = (normalize((c.description or "") + " " + (c.conditions or "")))
                clean_text_norm = raw_clean_text
            
            eligible_cards_str = normalize(c.eligible_cards or "")
            
            suspected_missing = []
            for kw in CARD_KEYWORDS:
                kw_norm = normalize(kw)
                matches = list(re.finditer(r'\b' + re.escape(kw_norm) + r'\b', clean_text_norm))
                for match in matches:
                    pos = match.start()
                    if any(kw_norm in card for card in eligible_cards_str.split()): continue
                    if is_in_exclusion_context(clean_text_norm, pos): continue
                    if is_in_footer_jumble(clean_text_norm, pos): continue
                    suspected_missing.append(kw)
                    break
            
            if suspected_missing:
                bank_stats[bank_name]["mismatched"] += 1
                mismatches.append({
                    "id": c.id,
                    "title": c.title,
                    "bank": bank_name,
                    "extracted": c.eligible_cards,
                    "suspected_missing": sorted(list(set(suspected_missing)))
                })

    print("\n--- BANK-WISE STATISTICS ---")
    print(f"{'Bank Name':<25} | {'Total':<10} | {'Mismatched':<12} | {'Error Rate':<10}")
    print("-" * 65)
    for bank, stats in sorted(bank_stats.items(), key=lambda x: x[1]["mismatched"], reverse=True):
        rate = (stats["mismatched"] / stats["total"] * 100) if stats["total"] > 0 else 0
        print(f"{bank:<25} | {stats['total']:<10} | {stats['mismatched']:<12} | {rate:>9.1f}%")

    print(f"\n✅ Total Mismatches Found: {len(mismatches)}")

    # Sort by bank more logically
    mismatches.sort(key=lambda x: (x["bank"], x["id"]))

    print(f"\n✅ Diagnostic Complete. Found {len(mismatches)} campaigns with potential card mismatches.")
    
    if mismatches:
        print("\n--- DETAILED REPORT ---")
        for m in mismatches[:50]: # Show first 50
            print(f"[{m['id']}] {m['title']} ({m['bank']})")
            print(f"   Extracted: {m['extracted']}")
            print(f"   Suspected Missing Keywords in Clean Text: {m['suspected_missing']}")
            print("-" * 50)
        
        if len(mismatches) > 50:
            print(f"... and {len(mismatches) - 50} more.")

if __name__ == "__main__":
    find_missing_cards()
