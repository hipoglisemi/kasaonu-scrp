from sqlalchemy import text
from src.database import SessionLocal
import re
from collections import Counter

def analyze():
    db = SessionLocal()
    try:
        campaigns = db.execute(text("SELECT id, clean_text FROM \"campaigns\" WHERE clean_text IS NOT NULL")).fetchall()
        
        # We are looking for any action-oriented keywords that indicate participation
        action_keywords = [
            "tıklayarak", "katıl butonuna", "sms gönder", "göndererek", "okutarak",
            "okutunuz", "başvur", "şifre", "gişeden", "müşteri hizmetleri", "çağrı merkezi",
            "kasada", "sepet", "ödeme adımında", "internet şube", "mobil uygulama"
        ]
        
        found_phrases = []
        
        for c in campaigns:
            text_content = c[1].lower() if c[1] else ""
            sentences = [s.strip() for s in re.split(r'[.!?]', text_content) if len(s.strip()) > 10]
            
            for s in sentences:
                s_clean = re.sub(r'\s+', ' ', s)
                if any(kw in s_clean for kw in action_keywords):
                    # Filter out purely informational or standard conditional sentences
                    if "tarihleri arasında" in s_clean or "kazanılan" in s_clean or "geçerlidir" in s_clean or "dahildir" in s_clean or "hariçtir" in s_clean:
                        continue
                    if "iptal" in s_clean or "iade" in s_clean or "iade edilmesi" in s_clean:
                        continue
                        
                    found_phrases.append(s_clean)
                                
        # Group similar sentences to find the main variations
        variation_counts = Counter()
        
        for phrase in found_phrases:
            # Create a simplified signature of the sentence to group similar ones
            words = [w for w in phrase.split() if len(w) > 3]
            signature = " ".join(words[:5]) # just use the first few meaningful words as a group key
            variation_counts[phrase] += 1
            
        print("--- TÜM KATILIM ŞEKLİ VARYASYONLARI (SIKLIK SIRASINA GÖRE) ---")
        for phrase, count in variation_counts.most_common(50):
            if count > 2: # Show phrases that appear multiple times
                print(f"[{count} defa] - {phrase}")

    finally:
        db.close()

if __name__ == "__main__":
    analyze()
