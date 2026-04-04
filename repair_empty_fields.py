import os
import sys
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime

# Ensure src in path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.database import SessionLocal
from src.models import Campaign, Card, Bank
from src.services.ai_parser import AIParser

def repair_empty_fields(min_clean_text=1000, max_conditions=200):
    print("🚀 Starting Repair for Empty Fields (22 Target Campaigns)...")
    db = SessionLocal()
    parser = AIParser()
    
    try:
        # Find active campaigns where clean_text is present but conditions is suspiciously short or empty
        candidates = db.query(Campaign).filter(
            Campaign.is_active == True,
            func.length(Campaign.clean_text) >= min_clean_text,
            (Campaign.conditions == None) | (func.length(Campaign.conditions) < max_conditions)
        ).all()

        print(f"🔍 Found {len(candidates)} candidates for repair.\n")

        for c in candidates:
            print(f"🔄 Repairing [{c.id}] {c.title[:50]}...")
            print(f"   - Current clean_text length: {len(c.clean_text)}")
            
            # Re-parse using existing clean_text with FORCE=True to skip cache
            # We use force=True because we just updated the AI prompt
            ai_data = parser.parse_campaign_data(
                raw_text=c.clean_text,
                title=c.title,
                force=True, # Force new AI call
                campaign_id=c.id
            )
            
            if ai_data:
                # Update fields
                c.reward_text = ai_data.get('reward_text')
                c.reward_value = ai_data.get('reward_value')
                c.reward_type = ai_data.get('reward_type')
                
                # Combine conditions
                conds = ai_data.get('conditions', [])
                part = ai_data.get('participation')
                if part and part != "Otomatik katılım":
                    conds.insert(0, f"KATILIM: {part}")
                c.conditions = "\n".join(conds)
                
                # Update participation if field exists in your actual model (in some versions it's only in conditions)
                # For now, we trust the combined conditions above
                
                c.eligible_cards = ", ".join(ai_data.get('cards', []))
                c.updated_at = datetime.utcnow()
                
                db.commit()
                print(f"   ✅ REPAIRED! New conditions length: {len(c.conditions) if c.conditions else 0}")
            else:
                print(f"   ❌ AI failed to parse for campaign {c.id}")
            
            print("-" * 40)

    except Exception as e:
        print(f"❌ Error during repair: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    repair_empty_fields()
