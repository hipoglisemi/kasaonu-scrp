import json
import re
from src.utils.gemini_client import generate_with_rotation

def normalize_card_name(name: str) -> str:
    if not name:
        return ""
    # Lowercase and convert Turkish characters
    name = name.lower().strip()
    replacements = {
        "ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c",
        "â": "a", "î": "i", "û": "u"
    }
    for k, v in replacements.items():
        name = name.replace(k, v)
    # Remove extra spaces, non-alphanumeric chars
    name = re.sub(r'[^a-z0-9]', '', name)
    return name

def extract_cards_via_ai(text: str, bank_name: str):
    """
    Extracts eligible credit/debit card names from a campaign text and bank name using Gemini with key rotation.
    Returns: (list_of_cards, card_section_raw_text)
    """
    prompt = f"""
Sana bir banka kampanyası metni ve bu kampanyanın ait olduğu bankanın adı verilecek.
Bu metinden, kampanyaya DAHİL olan (yani puan, mil, indirim, taksit vb. ödül kazanan) KARTLARI tespit et.

Banka: {bank_name}
Metin:
{text}

Lütfen kampanyaya dahil olan kartları şu JSON formatında geri döndür:
{{
  "cards": ["Kart A", "Kart B"],
  "card_section": "Kampanyaya dahil olan kartların geçtiği paragrafın veya listenin tam metni"
}}

Önemli Kurallar:
- Sadece gerçekten kampanyaya dahil olan kart türlerini (kredi kartı, banka kartı, ticari kart vb.) ekle.
- "tüm bireysel kredi kartları", "tüm bankamatik kartları" gibi ifadeler varsa bunları doğrudan liste elemanı olarak ekle.
- Sadece geçerli JSON çıktısı ver. Markdown formatı (```json) kullanabilirsin.
"""
    try:
        response_text = generate_with_rotation(prompt, model="gemini-3.5-flash-lite")
        # Clean potential markdown fences
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        else:
            response_text = response_text.strip()
            
        data = json.loads(response_text)
        cards = data.get("cards") or []
        card_section = data.get("card_section") or ""
        return cards, card_section
    except Exception as e:
        print(f"   ⚠️ [Card Auditor AI] Extraction failed: {e}")
        return [], ""
