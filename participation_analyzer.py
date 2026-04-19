from sqlalchemy import text
from src.database import SessionLocal
import re
from collections import Counter

def analyze():
    db = SessionLocal()
    try:
        # Fetch clean_text and participation fields from recently processed campaigns
        campaigns = db.execute(text("SELECT id, clean_text, participation FROM \"campaigns\" WHERE clean_text IS NOT NULL LIMIT 2000")).fetchall()
        
        participation_keywords = [
            "adımında", "seçerek", "okutarak", "kasada", "şifre", 
            "göndererek", "gişeden", "linke tıklayarak", "okutunuz",
            "başvur", "uygulamasından", "menüsünden"
        ]
        
        found_phrases = []
        
        for c in campaigns:
            c_id = c[0]
            text_content = c[1].lower() if c[1] else ""
            participation = c[2].lower() if c[2] else ""
            
            # If participation is empty or missing, let's see what we missed in the text
            if not participation or len(participation) < 5 or participation == "-":
                # split into sentences
                sentences = [s.strip() for s in re.split(r'[.!?]', text_content) if len(s.strip()) > 10]
                for s in sentences:
                    for kw in participation_keywords:
                        if kw in s and ("kampanya" in s or "indirim" in s or "puan" in s or "taksit" in s):
                            # Avoid generic condition phrases
                            if "tarihleri arasında" not in s and "geçerlidir" not in s and "dahildir" not in s and "hariçtir" not in s:
                                found_phrases.append(s)
                                break # only count sentence once
                                
        # Identify the most common phrase structures
        print("--- UNCAUGHT PARTICIPATION PHRASES IN DATABASE ---")
        for phrase in list(set(found_phrases))[:20]:
             print(f"- {phrase}")

        print(f"\nTotal possible uncaught participation sentences found: {len(list(set(found_phrases)))}")
    finally:
        db.close()

if __name__ == "__main__":
    analyze()
