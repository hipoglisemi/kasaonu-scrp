import os
import sys
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database import get_db_session
from src.models import Campaign
from src.utils.gemini_client import generate_with_rotation

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MarketingUpgrader")

TARGET_IDS = [17008, 17009, 17011, 17012, 17013, 17018, 17019, 17020, 17021, 17022, 17023, 17024, 17028, 17030, 17032]
MODEL = "gemini-2.5-flash"

MARKETING_PROMPT_TEMPLATE = """
Sen uzman bir pazarlama metni yazarıısın. Aşağıdaki kampanya detaylarını kullanarak kullanıcıyı heyecanlandıracak, enerjik ve samimi bir "Pazarlama Özeti" (Marketing Text) oluştur.

KAMPANYA BİLGİLERİ:
Başlık: {title}
Açıklama: {description}
Detay Koşullar: {conditions}

KURALLAR:
1. **DİL**: Tamamı TÜRKÇE olmalı.
2. **TARZ**: Enerjik, samimi, kullanıcıyı teşvik edici ve davetkar ol. 
3. **EMOJİ**: Cümlelerin arasına ve sonuna mutlaka uygun emojiler ekle (🎉, 🚀, 💳, 🛒, ⛽ gibi).
4. **UZUNLUK**: Mutlaka 2-3 cümle olmalı (en az 150, en fazla 300 karakter).
5. **İÇERİK**: SomUT rakamları (100 TL Puan, %15 İndirim vb.) mutlaka vurgula. Jenerik geçiştirme yapma.
6. **YASAK**: "Banka", "Katılım için SMS gönderin" gibi teknik detaylara girme, sadece avantaja odaklan.

Örnek (ID 16986): 
"Adımlarınız artık kazanca dönüşüyor! 🏃 CEPTETEB mobil uygulamasından kodunuzu alın, WalkersApp'te 2500 Walkers Puan'ın sahibi olun. 🚀 Sağlıklı yaşamın keyfini çıkarırken puanlarınızı dilediğinizce harcayın, bu fırsatı sakın kaçırmayın! 🎉"

Sadece PAZARLAMA METNİNİ yaz, başka açıklama ekleme.
"""

def upgrade_marketing_texts():
    with get_db_session() as db:
        campaigns = db.query(Campaign).filter(Campaign.id.in_(TARGET_IDS)).all()
        logger.info(f"🚀 Starting upgrade for {len(campaigns)} campaigns...")
        
        for c in campaigns:
            logger.info(f"🔄 Processing ID {c.id}: {c.title[:40]}...")
            
            prompt = MARKETING_PROMPT_TEMPLATE.format(
                title=c.title,
                description=c.description or "",
                conditions=c.conditions or ""
            )
            
            try:
                # Use robust rotation-aware generator
                new_text = generate_with_rotation(prompt, model=MODEL)
                
                # Cleanup if AI adds quotes
                if new_text.startswith('"') and new_text.endswith('"'):
                    new_text = new_text[1:-1].strip()
                
                if new_text:
                    c.ai_marketing_text = new_text
                    c.updated_at = datetime.utcnow()
                    logger.info(f"   ✅ Done: {new_text[:60]}...")
                else:
                    logger.warning(f"   ⚠️ Empty response from AI for ID {c.id}")
                
                # Jitter/Sleep to avoid 503
                import time
                time.sleep(2)
                    
            except Exception as e:
                logger.error(f"   ❌ Error for ID {c.id}: {e}")
        
        db.commit()
        logger.info("🏁 All tasks completed and committed to DB.")

if __name__ == "__main__":
    upgrade_marketing_texts()
