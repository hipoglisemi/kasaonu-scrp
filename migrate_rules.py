import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Add current dir to path for imports
sys.path.append(os.getcwd())
from src.models import PointBlankRule
from brand_sector_diagnostic import MATCH_RULES

load_dotenv()

# Sector mapping for slugs
SECTOR_MAP = {
    "Market & Gıda": "market-gida",
    "Akaryakıt": "akaryakit",
    "Giyim & Aksesuar": "giyim-aksesuar",
    "Restoran & Kafe": "restoran-kafe",
    "Elektronik": "elektronik",
    "Mobilya & Dekorasyon": "mobilya-dekorasyon",
    "Kozmetik & Sağlık": "kozmetik-saglik",
    "E-Ticaret": "e-ticaret",
    "Ulaşım": "ulasim",
    "Dijital Platform": "dijital-platform",
    "Dijital Platform & Oyun": "dijital-platform",
    "Kültür & Sanat": "kultur-sanat",
    "Spor, Kültür & Eğlence": "kultur-sanat",
    "Eğitim": "egitim",
    "Sigorta": "sigorta",
    "Otomotiv": "otomotiv",
    "Fatura & Telekomünikasyon": "fatura-telekomunikasyon",
    "Turizm & Konaklama": "turizm-konaklama",
    "Turizm, Konaklama & Seyahat": "turizm-konaklama",
    "Anne, Bebek & Oyuncak": "anne-bebek-oyuncak",
    "Finans & Yatırım": "finans-yatirim",
    "Diğer": "diger"
}

def migrate_rules():
    engine = create_engine(os.getenv('DATABASE_URL'))
    Session = sessionmaker(bind=engine)
    session = Session()

    print(f"Migrating {len(MATCH_RULES)} rules from diagnostic script to DB...")
    
    count = 0
    skipped = 0
    
    try:
        for keyword, data in MATCH_RULES.items():
            # Check if exists
            existing = session.query(PointBlankRule).filter(PointBlankRule.keyword == keyword).first()
            if existing:
                skipped += 1
                continue
                
            sector_name = data["sector"]
            sector_slug = SECTOR_MAP.get(sector_name, "diger")
            
            rule = PointBlankRule(
                keyword=keyword,
                brand_name=data["brand"],
                sector_slug=sector_slug,
                is_verified=True # Hardcoded ones are already verified
            )
            session.add(rule)
            count += 1
            
        session.commit()
        print(f"✅ Migration complete. Added: {count}, Skipped: {skipped}")
    except Exception as e:
        session.rollback()
        print(f"❌ Migration failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    migrate_rules()
