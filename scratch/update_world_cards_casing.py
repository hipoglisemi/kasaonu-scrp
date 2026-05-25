import re
import sys
from src.database import get_db
from src.models import Campaign

def clean_and_format_card(card: str) -> str:
    brands_to_title = {
        "yapi kredi": "Yapı Kredi", "yapı kredi": "Yapı Kredi",
        "worldcard": "Worldcard", "world card": "Worldcard",
        "vakifbank": "Vakıfbank", "vakıfbank": "Vakıfbank",
        "albaraka": "Albaraka", "anadolubank": "Anadolubank",
        "opet": "Opet", "fenerbahce": "Fenerbahçe", "fenerbahçe": "Fenerbahçe",
        "troy": "TROY", "mastercard": "Mastercard", "visa": "Visa",
        "axess": "Axess", "wings": "Wings", "free": "Free",
        "paraf": "Paraf", "parafly": "Parafly", "bankkart": "Bankkart",
        "tlcard": "TLcard", "tl card": "TLcard"
    }
    card_clean = card.strip()
    for lower_brand, proper_brand in brands_to_title.items():
        card_clean = re.sub(rf"(?i)\b{re.escape(lower_brand)}\b", proper_brand, card_clean)
        
    if not card_clean:
        return ""
        
    # Turkish-aware capitalization of first letter of the card item
    first_char = card_clean[0]
    if first_char == 'ı':
        first_char = 'I'
    elif first_char == 'i':
        first_char = 'İ'
    else:
        first_char = first_char.upper()
        
    return first_char + card_clean[1:]

def format_eligible_cards_string(cards_str: str) -> str:
    if not cards_str or cards_str.strip() in ["", "-", "None"]:
        return cards_str
        
    # Split by comma
    parts = cards_str.split(",")
    formatted_parts = []
    for p in parts:
        formatted = clean_and_format_card(p)
        if formatted:
            formatted_parts.append(formatted)
            
    return ", ".join(formatted_parts)

def main():
    db = next(get_db())
    campaigns = db.query(Campaign).filter(
        Campaign.tracking_url.like('%worldcard.com.tr%'),
        Campaign.is_active == True
    ).all()
    
    print(f"Loaded {len(campaigns)} active YKB World campaigns.")
    updated_count = 0
    
    for camp in campaigns:
        old_val = camp.eligible_cards
        if not old_val:
            continue
            
        new_val = format_eligible_cards_string(old_val)
        if old_val != new_val:
            print(f"Updating Campaign #{camp.id}:")
            print(f"  Old: {old_val}")
            print(f"  New: {new_val}")
            camp.eligible_cards = new_val
            updated_count += 1
            
    if updated_count > 0:
        db.commit()
        print(f"\nSuccessfully capitalized and updated {updated_count} campaign cards in the database!")
    else:
        print("\nAll campaign cards are already perfectly capitalized and formatted.")

if __name__ == "__main__":
    main()
