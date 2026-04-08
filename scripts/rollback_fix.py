import os
import sys
import json
from typing import Optional

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign
from sqlalchemy import text

def rollback_campaign(campaign_id: int):
    print(f"🔄 Rollback başlatılıyor: Kampanya ID {campaign_id}")
    db = SessionLocal()
    
    # En son NIGHTLY_AUTOFIX logunu bul
    query = text("""
        SELECT old_value FROM campaign_audit_log 
        WHERE campaign_id = :cid AND audit_type = 'NIGHTLY_AUTOFIX' 
        ORDER BY created_at DESC LIMIT 1
    """)
    result = db.execute(query, {"cid": campaign_id}).fetchone()
    
    if not result or not result[0]:
        print("❌ HATA: Kampanyaya ait bir AutoFix geri alma noktası (snapshot) bulunamadı.")
        db.close()
        return

    old_state = json.loads(result[0])
    
    c = db.query(Campaign).get(campaign_id)
    if not c:
        print("❌ HATA: Kampanya bulunamadı.")
        db.close()
        return

    # Değerleri eskiye döndür
    c.title = old_state.get('title')
    c.description = old_state.get('description')
    c.reward_text = old_state.get('reward_text')
    c.reward_value = float(old_state['reward_value']) if old_state.get('reward_value') else None
    c.reward_type = old_state.get('reward_type')
    c.eligible_cards = old_state.get('eligible_cards')
    c.participation = old_state.get('participation')
    c.conditions = old_state.get('conditions')
    
    db.commit()
    print(f"✅ BAŞARILI! Kampanya #{campaign_id} başarıyla eski ayarlarına ({old_state.get('title')}) döndürüldü.")
    db.close()

if __name__ == "__main__":
    if len(sys.sys.argv) < 2:
        print("Kullanım: python3 scripts/rollback_fix.py <KAMPANYA_ID>")
        sys.exit(1)
        
    try:
        cid = int(sys.argv[1])
        rollback_campaign(cid)
    except ValueError:
        print("Lütfen geçerli bir Kampanya ID girin.")
