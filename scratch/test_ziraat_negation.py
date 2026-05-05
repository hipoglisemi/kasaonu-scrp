import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.negation_filter import check_string_negation

def test_ziraat_logic():
    # Ziraat'in gerçek cümlesi
    sentence = "Kampanyaya Bankkart, Bankkart Genç ve Bankkart Prestij kartları ile yapılan işlemler dahildir."
    
    cards_to_check = ["Bankkart", "Bankkart Genç", "Bankkart Prestij"]
    
    print(f"📝 Test Edilen Cümle: {sentence}")
    for card in cards_to_check:
        is_negated = check_string_negation(sentence, card)
        print(f"❓ '{card}' elendi mi (negatif mi)? {is_negated}")

if __name__ == "__main__":
    test_ziraat_logic()
